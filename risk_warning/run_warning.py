from pathlib import Path
import csv
import sys


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
DATA_COLLECTION_DIR = PROJECT_DIR / "data_collection"
TEXT_ANALYSIS_DIR = PROJECT_DIR / "text_analysis"

sys.path.insert(0, str(DATA_COLLECTION_DIR))
sys.path.insert(0, str(CURRENT_DIR))

from importers import import_prices  # noqa: E402
from price_monitor import build_price_change_map  # noqa: E402
from warning_generator import filter_by_level, generate_warnings, level_summary  # noqa: E402


NEWS_FILE = TEXT_ANALYSIS_DIR / "output" / "analyzed_news.csv"
PRICE_FILE = DATA_COLLECTION_DIR / "sample_data" / "sample_prices.csv"
OUTPUT_DIR = CURRENT_DIR / "output"
OUTPUT_FILE = OUTPUT_DIR / "warnings.csv"


def read_analyzed_news(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def save_warnings(warnings: list[dict], path: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "title",
        "region",
        "product",
        "risk_type",
        "risk_score",
        "risk_level",
        "keyword_score",
        "price_score",
        "heat_score",
        "region_score",
        "local_match_score",
        "source_score",
        "confidence",
        "evidence_summary",
        "positive_adjustment",
        "trigger_words",
        "reason",
        "suggestion",
        "source",
        "category",
        "url",
    ]
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(warnings)


def main() -> None:
    if not NEWS_FILE.exists():
        raise FileNotFoundError(
            f"未找到文本分析结果: {NEWS_FILE}，请先运行 project/text_analysis/run_analysis.py"
        )

    news_items = read_analyzed_news(NEWS_FILE)
    price_items = import_prices(PRICE_FILE)
    price_changes = build_price_change_map(price_items)
    warnings = generate_warnings(news_items, price_changes)
    save_warnings(warnings, OUTPUT_FILE)

    summary = level_summary(warnings)
    important = filter_by_level(warnings, "中风险")

    print("风险预警模块演示")
    print(f"输入新闻数量: {len(news_items)}")
    print(f"价格趋势数量: {len(price_changes)}")
    print(f"预警记录数量: {len(warnings)}")
    print(f"中风险及以上数量: {len(important)}")
    print(f"风险等级统计: {dict(summary)}")
    print(f"输出文件: {OUTPUT_FILE}")

    if warnings:
        sample = warnings[0]
        print("\n最高风险样例:")
        print(f"- 标题: {sample['title']}")
        print(f"- 等级: {sample['risk_level']} ({sample['risk_score']})")
        print(f"- 类型: {sample['risk_type']}")
        print(f"- 触发词: {sample['trigger_words']}")
        print(f"- 原因: {sample['reason']}")


if __name__ == "__main__":
    main()
