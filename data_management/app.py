import json
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware


CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))
sys.path.insert(0, str(CURRENT_DIR.parent / "data_collection"))

from config import LOGIN_PASSWORD, LOGIN_USER  # noqa: E402
from db import get_connection, initialize_schema  # noqa: E402
from dedup import deduplicate_news  # noqa: E402
from evidence_collector import collect_evidence_for_news  # noqa: E402
from henan_scope import HENAN_CITIES  # noqa: E402
from importers import import_news, import_prices  # noqa: E402
from keyword_query import build_search_queries, parse_manual_keywords  # noqa: E402
from news_crawler import NewsCrawler  # noqa: E402
from pipeline import rebuild_from_demo_data  # noqa: E402
from queries import (  # noqa: E402
    category_chart,
    get_warning,
    get_news,
    hotwords_chart,
    list_news,
    list_prices,
    list_warnings,
    overview_stats,
    price_trend,
)
from repository import fetch_all, insert_news, insert_prices, insert_warnings, prune_news, prune_prices  # noqa: E402
from search_engines import build_engine_chain  # noqa: E402
from sources import (  # noqa: E402
    EVIDENCE_NEWS_SOURCES,
    MAX_QUERIES,
    NEWS_SOURCES,
    PRICE_SOURCES,
    PRIMARY_NEWS_SOURCES,
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


NEWS_LIMIT = 50
PRICE_LIMIT = 200


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
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", "")).strip()
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


def _unique_url(url: str, batch_id: str, index: int, source: str) -> str:
    if not url:
        return f"demo://{source}/{batch_id}/{index}"

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query["demo_batch"] = batch_id
    query["demo_index"] = str(index)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def _attach_batch_urls(news: list[dict], batch_id: str, source: str) -> list[dict]:
    result = []
    for index, item in enumerate(news, start=1):
        row = dict(item)
        row["url"] = _unique_url(row.get("url", ""), batch_id, index, source)
        result.append(row)
    return result


def _normalized_title(title: str) -> str:
    return " ".join(str(title or "").split())


def _existing_news_titles() -> set[str]:
    rows = fetch_all("SELECT title FROM news")
    return {_normalized_title(row.get("title", "")) for row in rows if row.get("title")}


def _take_unseen_news(news: list[dict], total_limit: int) -> list[dict]:
    existing_titles = _existing_news_titles()
    seen_titles = set()
    result = []

    for item in news:
        title = _normalized_title(item.get("title", ""))
        if not title or title in existing_titles or title in seen_titles:
            continue
        seen_titles.add(title)
        result.append(item)
        if len(result) >= total_limit:
            break

    return result


def _to_news_rows(raw_news: list[dict], analyzed_news: list[dict]) -> list[dict]:
    news_rows = []
    raw_by_url = {item.get("url", ""): item for item in raw_news}
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
    return news_rows


def _current_price_changes() -> dict:
    current_prices = list_prices()
    return build_price_change_map(
        [
            {
                "product_name": row.get("product_name", ""),
                "price": float(row.get("price", 0) or 0),
                "unit": row.get("unit", ""),
                "region": row.get("region", ""),
                "province": row.get("province", ""),
                "city": row.get("city", ""),
                "market_name": row.get("market_name", ""),
                "source_level": row.get("source_level", ""),
                "date": row.get("date", ""),
                "source": row.get("source", ""),
                "source_url": row.get("source_url", ""),
            }
            for row in current_prices
        ]
    )


def _rebuild_warnings_from_existing_news() -> dict:
    news_rows = fetch_all("SELECT * FROM news ORDER BY id")
    warnings = generate_warnings(news_rows, _current_price_changes(), use_llm=False)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM warnings")
    inserted = insert_warnings(warnings)
    return {
        "news_rows": len(news_rows),
        "warnings": warnings,
        "warnings_saved": inserted,
    }


def _extract_date_label(value: str) -> str:
    text = str(value or "").strip()
    for separator in (" ", "T"):
        if separator in text:
            text = text.split(separator, 1)[0]
    if len(text) >= 10 and text[4] in "-/" and text[7] in "-/":
        return text[:10].replace("/", "-")
    return datetime.now().strftime("%Y-%m-%d")


def _price_reference_date(news: list[dict]) -> str:
    for item in news:
        label = _extract_date_label(item.get("publish_time", ""))
        if label:
            return label
    return datetime.now().strftime("%Y-%m-%d")


def _demo_price_rows(batch_id: str, news: list[dict] | None = None) -> list[dict]:
    label = _price_reference_date(news or [])
    seed = sum(ord(char) for char in label) % 5
    return [
        {
            "product_name": "小麦",
            "price": round(2.82 + seed * 0.03, 2),
            "unit": "元/公斤",
            "region": "郑州",
            "province": "河南",
            "city": "郑州",
            "market_name": "郑州本地演示市场",
            "source_level": "city",
            "date": label,
            "source": "演示实时行情",
        },
        {
            "product_name": "玉米",
            "price": round(2.28 + seed * 0.02, 2),
            "unit": "元/公斤",
            "region": "郑州",
            "province": "河南",
            "city": "郑州",
            "market_name": "郑州本地演示市场",
            "source_level": "city",
            "date": label,
            "source": "演示实时行情",
        },
        {
            "product_name": "番茄",
            "price": round(5.10 + seed * 0.12, 2),
            "unit": "元/公斤",
            "region": "郑州",
            "province": "河南",
            "city": "郑州",
            "market_name": "郑州本地演示市场",
            "source_level": "city",
            "date": label,
            "source": "演示实时行情",
        },
    ]


def _save_news_and_warnings(raw_news: list[dict], evidence_items: list[dict] | None = None) -> dict:
    analyzed_news = analyze_news_batch(raw_news)
    evidence_map = collect_evidence_for_news(analyzed_news, evidence_items or [], PRICE_SOURCES)
    for item in analyzed_news:
        evidence = evidence_map.get(item.get("url", ""), {})
        item["evidence_score"] = evidence.get("score", 0)
        item["evidence_summary"] = evidence.get("summary", "")
        item["evidence_links"] = evidence.get("links_json", "")
    news_rows = _to_news_rows(raw_news, analyzed_news)
    warnings = generate_warnings(analyzed_news, _current_price_changes())

    inserted_news = insert_news(news_rows)
    inserted_warnings = insert_warnings(warnings)
    removed_news = prune_news(NEWS_LIMIT)

    return {
        "news_rows": news_rows,
        "warnings": warnings,
        "news_saved": inserted_news,
        "warnings_saved": inserted_warnings,
        "news_removed": removed_news,
    }


@app.post("/api/crawl/update")
def crawl_update(limit_per_source: int = 5, total_limit: int = 5):
    batch_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    crawler = NewsCrawler(timeout=5)
    candidate_limit = max(min(limit_per_source * 5, 25), min(total_limit * 5, 25), 5)
    result = crawler.crawl_sources(PRIMARY_NEWS_SOURCES, limit_per_source=candidate_limit)
    candidates = deduplicate_news(result.items)
    news = _take_unseen_news(candidates, total_limit)
    news = _attach_batch_urls(news, batch_id, "crawl")
    evidence_result = crawler.crawl_sources(EVIDENCE_NEWS_SOURCES, limit_per_source=5)
    save_result = _save_news_and_warnings(news, evidence_result.items)

    inserted_prices = 0
    removed_prices = prune_prices(PRICE_LIMIT)

    return {
        "message": "crawl finished",
        "crawled": len(news),
        "candidates": len(candidates),
        "skipped_existing": max(len(candidates) - len(news), 0),
        "news_saved": save_result["news_saved"],
        "warnings_saved": save_result["warnings_saved"],
        "prices_saved": inserted_prices,
        "news_removed": save_result["news_removed"],
        "prices_removed": removed_prices,
        "errors": result.errors,
        "evidence_candidates": len(evidence_result.items),
        "evidence_errors": evidence_result.errors,
    }


@app.post("/api/crawl/search")
def crawl_search(limit_per_query: int = 5, total_limit: int = 5, keywords: str = ""):
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
    candidates = deduplicate_news(result.items)
    news = _take_unseen_news(candidates, total_limit)
    batch_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    news = _attach_batch_urls(news, batch_id, "search")
    evidence_result = crawler.crawl_sources(EVIDENCE_NEWS_SOURCES, limit_per_source=5)
    save_result = _save_news_and_warnings(news, evidence_result.items)

    return {
        "message": "search crawl finished",
        "crawled": len(news),
        "queries": queries,
        "candidates": len(candidates),
        "skipped_existing": max(len(candidates) - len(news), 0),
        "news_saved": save_result["news_saved"],
        "warnings_saved": save_result["warnings_saved"],
        "news_removed": save_result["news_removed"],
        "errors": result.errors,
        "evidence_candidates": len(evidence_result.items),
        "evidence_errors": evidence_result.errors,
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


def _score_part(name: str, value: object, max_value: int, reason: str, links: list[dict] | None = None) -> dict:
    number = float(value or 0)
    return {
        "name": name,
        "value": round(number, 1),
        "max": max_value,
        "reason": reason,
        "links": links or [],
    }


def _link_from_news(row: dict, note: str = "") -> dict:
    return {
        "name": row.get("title") or row.get("source") or "相关新闻",
        "url": row.get("url") or "",
        "note": note or f"{row.get('source', '')} {row.get('publish_time', '')}".strip(),
    }


def _find_related_news_links(item: dict, kind: str, limit: int = 3) -> list[dict]:
    region = item.get("region") or ""
    url = item.get("url") or ""
    trigger_words = [
        word.strip()
        for word in str(item.get("trigger_words") or "").replace("，", "、").split("、")
        if word.strip() and "未发现" not in word
    ]
    weather_words = ["气象", "天气", "降雨", "暴雨", "洪水", "汛情", "干旱", "高温", "低温", "预警"]
    price_words = ["价格", "行情", "批发", "市场"]
    words = weather_words if kind == "weather" else price_words
    words = list(dict.fromkeys(words + (trigger_words[:4] if kind == "weather" else [])))

    sql = "SELECT title, source, publish_time, url, region, category FROM news WHERE url <> ''"
    params: list[object] = []
    if url:
        sql += " AND url <> %s"
        params.append(url)
    if region:
        sql += " AND region LIKE %s"
        params.append(f"%{region}%")
    local_terms = ["河南", *HENAN_CITIES]
    local_conditions = []
    for term in local_terms:
        like = f"%{term}%"
        local_conditions.append("(title LIKE %s OR content LIKE %s OR keywords LIKE %s)")
        params.extend([like, like, like])
    sql += " AND (" + " OR ".join(local_conditions) + ")"
    if words:
        conditions = []
        for word in words:
            like = f"%{word}%"
            conditions.append("(title LIKE %s OR content LIKE %s OR keywords LIKE %s OR category LIKE %s)")
            params.extend([like, like, like, like])
        sql += " AND (" + " OR ".join(conditions) + ")"
    if kind == "price" and item.get("product") and item.get("product") != "未识别":
        product_like = f"%{item.get('product')}%"
        sql += " AND (title LIKE %s OR content LIKE %s OR keywords LIKE %s)"
        params.extend([product_like, product_like, product_like])
    sql += " ORDER BY id DESC LIMIT %s"
    params.append(limit)
    note = "同地区气象旁证新闻" if kind == "weather" else "同地区价格/行情旁证新闻"
    return [_link_from_news(row, note) for row in fetch_all(sql, tuple(params)) if row.get("url")]


def _source_links(sources: list[dict], note: str, limit: int = 3) -> list[dict]:
    links = []
    for source in sources:
        url = source.get("url") or source.get("list_url") or source.get("base_url") or source.get("path") or ""
        if not url:
            continue
        links.append({"name": source.get("name", "来源链接"), "url": url, "note": note})
        if len(links) >= limit:
            break
    return links


def _stored_evidence_links(item: dict, evidence_type: str = "") -> list[dict]:
    try:
        links = json.loads(item.get("evidence_links") or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(links, list):
        return []
    result = [link for link in links if isinstance(link, dict) and link.get("url")]
    if evidence_type:
        result = [link for link in result if link.get("type") == evidence_type]
    return result


@app.get("/api/warnings/{warning_id}/analysis")
def api_warning_analysis(warning_id: int):
    item = get_warning(warning_id)
    if not item:
        raise HTTPException(status_code=404, detail="warning not found")

    product = item.get("product") or "未识别"
    region = item.get("region") or "相关地区"
    risk_type = item.get("risk_type") or "综合风险"
    trigger_words = item.get("trigger_words") or "未发现明显风险词"
    price_match = (item.get("evidence_summary") or "").replace("证据数:", "证据数：").replace(";价格匹配:", "；价格匹配：")
    original_news_links = [
        {
            "name": item.get("title") or item.get("source") or "原始新闻",
            "url": item.get("url") or "",
            "note": "触发本条预警的原始新闻",
        }
    ] if item.get("url") else []
    weather_links = _stored_evidence_links(item, "weather") or _find_related_news_links(item, "weather")
    price_links = _stored_evidence_links(item, "price") or _find_related_news_links(item, "price")
    if not price_links:
        price_links = _source_links(PRICE_SOURCES, f"{product}在{region}的价格旁证来源", 2)
    if float(item.get("price_score") or 0) <= 0:
        if product in {"未识别", ""}:
            price_reason = f"当前新闻没有识别到明确农产品，因此不能直接匹配单品价格；系统会尝试使用{region}地区农产品整体波动作为折扣旁证。"
        else:
            price_reason = f"当前未匹配到{product}在{region}的连续价格波动，或波动幅度不足以形成价格风险分。"
    else:
        price_reason = f"根据{product}在{region}的价格变化计算，{price_match or '已匹配到价格旁证'}。"

    return {
        "id": warning_id,
        "title": item.get("title", ""),
        "risk_score": item.get("risk_score", 0),
        "risk_level": item.get("risk_level", ""),
        "risk_type": risk_type,
        "region": region,
        "product": product,
        "confidence": item.get("confidence", 0),
        "summary": item.get("reason", ""),
        "suggestion": item.get("suggestion", ""),
        "score_parts": [
            _score_part("关键词风险分", item.get("keyword_score"), 60, f"根据标题、摘要和触发词“{trigger_words}”判断风险类型为“{risk_type}”。", original_news_links + weather_links),
            _score_part("价格波动分", item.get("price_score"), 25, price_reason, price_links),
            _score_part("新闻热度分", item.get("heat_score"), 15, "同类新闻越集中，说明该风险主题关注度越高。", weather_links),
            _score_part("证据验证分", item.get("evidence_score"), 20, "根据旁证来源权威性、地区匹配、时间接近、关键词匹配和证据一致性计算。", weather_links + price_links),
            _score_part("地区与来源分", item.get("region_score"), 20, "综合地区集中度、河南作物产区匹配度和信息来源可信度计算。", original_news_links),
            _score_part("河南作物匹配分", item.get("local_match_score"), 8, f"判断{product}是否属于{region}重点关注作物或河南主要农产品。"),
            _score_part("来源可信度分", item.get("source_score"), 8, "农业农村、气象、发改等权威来源权重更高，普通来源权重较低。", original_news_links),
            _score_part("稳定降分", item.get("positive_adjustment"), 18, "新闻中出现平稳、供应充足、保障等正向词时降低风险。"),
        ],
    }


@app.get("/api/prices")
def api_list_prices(product_name: str = "", region: str = "", city: str = ""):
    return list_prices(product_name=product_name, region=region, city=city)


@app.get("/api/stats/overview")
def api_overview_stats():
    return overview_stats()


@app.get("/api/charts/category")
def api_category_chart():
    return category_chart()


@app.get("/api/charts/price-trend")
def api_price_trend(product_name: str = "", city: str = ""):
    return price_trend(product_name=product_name, city=city)


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
    batch_id = datetime.now().strftime("%Y%m%d%H%M%S%f")
    rows = _attach_batch_urls(import_news(temp_file), batch_id, "import")
    save_result = _save_news_and_warnings(rows)
    return {
        "message": "file imported",
        "rows": len(rows),
        "news_saved": save_result["news_saved"],
        "warnings_saved": save_result["warnings_saved"],
        "news_removed": save_result["news_removed"],
        "sample": rows[:3],
        "warnings": save_result["warnings"][:5],
    }


@app.post("/api/import/prices")
async def import_price_file(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".csv", ".xlsx", ".xls"}:
        raise HTTPException(status_code=400, detail="only csv/xlsx/xls files are supported")

    temp_dir = CURRENT_DIR / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"upload_prices{suffix}"
    temp_file.write_bytes(await file.read())

    rows = import_prices(temp_file)
    inserted_prices = insert_prices(rows)
    rebuild_result = _rebuild_warnings_from_existing_news()
    return {
        "message": "prices imported",
        "rows": len(rows),
        "prices_saved": inserted_prices,
        "news_rows": rebuild_result["news_rows"],
        "warnings_saved": rebuild_result["warnings_saved"],
        "sample": rows[:5],
        "warnings": rebuild_result["warnings"][:5],
    }
