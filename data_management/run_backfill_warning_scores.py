import sys
from pathlib import Path


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent
RISK_WARNING_DIR = PROJECT_DIR / "risk_warning"
DATA_COLLECTION_DIR = PROJECT_DIR / "data_collection"

sys.path.insert(0, str(CURRENT_DIR))
sys.path.insert(0, str(DATA_COLLECTION_DIR))
sys.path.insert(0, str(RISK_WARNING_DIR))

from db import ensure_warning_score_columns
from price_monitor import build_price_change_map
from queries import list_prices
from repository import fetch_all, update_warning_score_parts
from scorer import build_context_scores, score_news_item


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def main() -> None:
    ensure_warning_score_columns()
    warnings = fetch_all("SELECT * FROM warnings ORDER BY id")
    price_rows = list_prices()
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
            for row in price_rows
        ]
    )

    score_inputs = [
        {
            "title": row.get("title", ""),
            "summary": row.get("reason", ""),
            "keywords": row.get("trigger_words", ""),
            "region": row.get("region", ""),
            "category": row.get("category", ""),
            "source": row.get("source", ""),
            "url": row.get("url", ""),
            "evidence_score": row.get("evidence_score", 0),
            "evidence_summary": row.get("evidence_summary", "") if row.get("evidence_links") else "",
            "evidence_links": row.get("evidence_links", ""),
        }
        for row in warnings
    ]
    category_counter, region_counter = build_context_scores(score_inputs)

    updates = []
    for row, item in zip(warnings, score_inputs):
        scored = score_news_item(item, category_counter, region_counter, price_changes)
        updates.append(
            {
                "id": row["id"],
                "risk_score": scored["risk_score"],
                "risk_level": scored["risk_level"],
                "keyword_score": scored["keyword_score"],
                "price_score": scored["price_score"],
                "heat_score": scored["heat_score"],
                "region_score": scored["region_score"],
                "local_match_score": scored["local_match_score"],
                "source_score": scored["source_score"],
                "evidence_score": scored["evidence_score"],
                "confidence": scored["confidence"],
                "positive_adjustment": scored["positive_adjustment"],
                "trigger_words": scored["trigger_words"],
                "evidence_summary": scored["evidence_summary"],
                "evidence_links": scored.get("evidence_links", row.get("evidence_links", "")),
            }
        )

    updated = update_warning_score_parts(updates)
    print("风险评分拆分字段回填完成")
    print(f"预警记录数: {len(warnings)}")
    print(f"更新数量: {updated}")


if __name__ == "__main__":
    main()
