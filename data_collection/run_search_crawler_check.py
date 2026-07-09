"""关键词反向爬取的 CLI 冒烟测试（脱离数据库）。

镜像 run_crawler_check.py：自动生成查询词 → 百度搜索采集 → 去重 →
写 output/search_crawler_news.csv → 打印数量/样例/错误。
"""

from pathlib import Path
import csv
import sys

from dedup import deduplicate_news
from keyword_query import build_search_queries
from news_crawler import NewsCrawler
from search_engines import build_engine_chain
from sources import (
    MAX_QUERIES,
    SEARCH_DELAY,
    SEARCH_ENGINE,
    SEARCH_ENGINE_FALLBACKS,
    SEARCH_LIMIT_PER_QUERY,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "search_crawler_news.csv"


def save_news(items: list[dict], path: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = ["title", "content", "source", "publish_time", "url", "region", "category"]
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(items)


def main() -> None:
    # 演示时用较小的查询规模，避免请求过多。
    max_queries = min(MAX_QUERIES, 6)
    queries = build_search_queries(max_queries=max_queries)
    engine = build_engine_chain(
        SEARCH_ENGINE, SEARCH_ENGINE_FALLBACKS, timeout=12, delay=SEARCH_DELAY
    )

    crawler = NewsCrawler(timeout=12)
    result = crawler.crawl_by_queries(
        queries, engine, limit_per_query=SEARCH_LIMIT_PER_QUERY
    )
    news = deduplicate_news(result.items)
    save_news(news, OUTPUT_FILE)

    print("关键词反向爬取验证")
    print(f"搜索引擎: {SEARCH_ENGINE}")
    print(f"查询词数量: {len(queries)}")
    print(f"抓取新闻数量: {len(news)}")
    print(f"输出文件: {OUTPUT_FILE}")

    print("\n查询词样例:")
    for spec in queries[:5]:
        print(f"- {spec['query']}  (地区={spec['region']}, 风险={spec['risk_type']})")

    if result.errors:
        print("\n异常查询:")
        for error in result.errors[:5]:
            print(f"- {error}")

    if news:
        print("\n新闻样例:")
        for item in news[:3]:
            print(f"- {item['title']} | {item['source']} | {item['url']}")
    else:
        print("\n没有抓取到新闻，请检查网络、搜索引擎结构或反爬限制。")


if __name__ == "__main__":
    main()
