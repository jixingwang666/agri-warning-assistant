import sys
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware


CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))
sys.path.insert(0, str(CURRENT_DIR.parent / "data_collection"))

from config import LOGIN_PASSWORD, LOGIN_USER  # noqa: E402
from db import initialize_schema  # noqa: E402
from dedup import deduplicate_news  # noqa: E402
from importers import import_news  # noqa: E402
from keyword_query import build_search_queries, parse_manual_keywords  # noqa: E402
from news_crawler import NewsCrawler  # noqa: E402
from pipeline import rebuild_from_demo_data  # noqa: E402
from queries import (  # noqa: E402
    category_chart,
    get_news,
    hotwords_chart,
    list_news,
    list_prices,
    list_warnings,
    overview_stats,
    price_trend,
)
from repository import insert_news, insert_warnings  # noqa: E402
from search_engines import build_engine_chain  # noqa: E402
from sources import (  # noqa: E402
    MAX_QUERIES,
    NEWS_SOURCES,
    SEARCH_DELAY,
    SEARCH_ENGINE,
    SEARCH_ENGINE_FALLBACKS,
    SEARCH_LIMIT_PER_QUERY,
)

sys.path.insert(0, str(CURRENT_DIR.parent / "text_analysis"))
sys.path.insert(0, str(CURRENT_DIR.parent / "risk_warning"))

from analyzer import analyze_news_batch  # noqa: E402
from price_monitor import build_price_change_map  # noqa: E402
from warning_generator import generate_warnings  # noqa: E402


app = FastAPI(title="面向本地农业的新闻舆情与风险预警助手")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(payload: dict):
    username = str(payload.get("username", ""))
    password = str(payload.get("password", ""))
    if username == LOGIN_USER and password == LOGIN_PASSWORD:
        return {"message": "login success", "username": username}
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@app.post("/api/db/init")
def init_db():
    initialize_schema()
    return {"message": "MySQL schema initialized"}


@app.post("/api/pipeline/rebuild")
def rebuild_pipeline():
    result = rebuild_from_demo_data(clear_first=True)
    return {"message": "demo data rebuilt", "result": result}


@app.post("/api/crawl/update")
def crawl_update(limit_per_source: int = 5):
    crawler = NewsCrawler(timeout=12)
    result = crawler.crawl_sources(NEWS_SOURCES, limit_per_source=limit_per_source)
    return _ingest_news_items(result.items, errors=result.errors, message="crawl finished")


@app.post("/api/crawl/search")
def crawl_search(limit_per_query: int = 5, keywords: str = ""):
    """关键词反向爬取：关键词 → 搜索引擎 → 抓正文 → 分析 → 预警 → 入库。

    keywords 为空时用内置词表自动生成查询；否则用用户传入的关键词。
    """
    if keywords.strip():
        queries = parse_manual_keywords(keywords)
    else:
        queries = build_search_queries(max_queries=MAX_QUERIES)

    engine = build_engine_chain(
        SEARCH_ENGINE, SEARCH_ENGINE_FALLBACKS, timeout=12, delay=SEARCH_DELAY
    )
    crawler = NewsCrawler(timeout=12)
    result = crawler.crawl_by_queries(
        queries, engine, limit_per_query=limit_per_query or SEARCH_LIMIT_PER_QUERY
    )
    return _ingest_news_items(
        result.items, errors=result.errors, message="search crawl finished"
    )


def _ingest_news_items(
    items: list[dict], errors: list | None = None, message: str = "crawl finished"
) -> dict:
    """采集后的公共下游管线：去重 → 分析 → 价格 → 预警 → 入库。

    被列表页采集(/api/crawl/update)和关键词反向爬取(/api/crawl/search)共用。
    """
    news = deduplicate_news(items)
    analyzed_news = analyze_news_batch(news)

    news_rows = []
    raw_by_url = {item.get("url", ""): item for item in news}
    for item in analyzed_news:
        raw = raw_by_url.get(item.get("url", ""), {})
        news_rows.append(
            {
                "title": item.get("title", ""),
                "content": raw.get("content", ""),
                "source": item.get("source", ""),
                "publish_time": item.get("publish_time", ""),
                "url": item.get("url", ""),
                "region": item.get("region", ""),
                "category": item.get("category", ""),
                "summary": item.get("summary", ""),
                "keywords": item.get("keywords", ""),
            }
        )

    current_prices = list_prices()
    price_changes = build_price_change_map(
        [
            {
                "product_name": row.get("product_name", ""),
                "price": float(row.get("price", 0) or 0),
                "unit": row.get("unit", ""),
                "region": row.get("region", ""),
                "date": row.get("date", ""),
                "source": row.get("source", ""),
            }
            for row in current_prices
        ]
    )
    warnings = generate_warnings(analyzed_news, price_changes)

    inserted_news = insert_news(news_rows)
    inserted_warnings = insert_warnings(warnings)
    return {
        "message": message,
        "crawled": len(news),
        "news_saved": inserted_news,
        "warnings_saved": inserted_warnings,
        "errors": errors or [],
    }


@app.get("/api/news")
def api_list_news(keyword: str = "", category: str = "", region: str = "", limit: int = 20, offset: int = 0):
    return list_news(keyword=keyword, category=category, region=region, limit=limit, offset=offset)


@app.get("/api/news/{news_id}")
def api_get_news(news_id: int):
    item = get_news(news_id)
    if not item:
        raise HTTPException(status_code=404, detail="news not found")
    return item


@app.get("/api/warnings")
def api_list_warnings(risk_level: str = "", region: str = "", product: str = "", limit: int = 20):
    return list_warnings(risk_level=risk_level, region=region, product=product, limit=limit)


@app.get("/api/prices")
def api_list_prices(product_name: str = "", region: str = ""):
    return list_prices(product_name=product_name, region=region)


@app.get("/api/stats/overview")
def api_overview_stats():
    return overview_stats()


@app.get("/api/charts/category")
def api_category_chart():
    return category_chart()


@app.get("/api/charts/price-trend")
def api_price_trend(product_name: str = ""):
    return price_trend(product_name=product_name)


@app.get("/api/charts/hotwords")
def api_hotwords_chart(limit: int = 20):
    return hotwords_chart(limit=limit)


@app.post("/api/import/news")
async def import_news_file(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="only csv/xlsx/xls files are supported")

    temp_dir = CURRENT_DIR / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"upload_news{suffix}"
    temp_file.write_bytes(await file.read())
    rows = import_news(temp_file)
    return {"message": "file parsed", "rows": len(rows), "sample": rows[:3]}
