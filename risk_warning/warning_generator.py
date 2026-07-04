from collections import Counter

from risk_rules import SUGGESTION_TEMPLATES
from scorer import build_context_scores, score_news_item


def build_reason(record: dict) -> str:
    words = record["trigger_words"]
    region = record["region"] or "相关地区"
    product = record["product"]
    risk_type = record["risk_type"]
    price_signal = record.get("price_signal") or {}

    reason = f"{region}相关新闻中出现“{words}”等信息，系统判断存在{risk_type}迹象。"
    if product != "未识别":
        reason += f" 涉及对象可能包括{product}。"
    if price_signal:
        change_rate = price_signal["change_rate"] * 100
        reason += f" 价格数据较前期变化约{change_rate:.1f}%，需结合市场情况继续观察。"
    return reason


def generate_warnings(news_items: list[dict], price_changes: dict[tuple[str, str], dict], use_llm: bool = True) -> list[dict]:
    category_counter, region_counter = build_context_scores(news_items)
    warnings = []
    for item in news_items:
        record = score_news_item(item, category_counter, region_counter, price_changes)
        record["reason"] = build_reason(record)
        record["suggestion"] = SUGGESTION_TEMPLATES.get(
            record["risk_type"], SUGGESTION_TEMPLATES["综合风险"]
        )
        record.pop("price_signal", None)
        warnings.append(record)

    # LLM enrichment: replace template reason/suggestion with context-aware LLM output
    if use_llm:
        try:
            from llm_enricher import enrich_warnings_batch  # noqa: F811
            warnings = enrich_warnings_batch(warnings)
        except Exception:
            pass  # graceful fallback — keep rule-based output

    return sorted(warnings, key=lambda row: row["risk_score"], reverse=True)


def filter_by_level(warnings: list[dict], min_level: str = "中风险") -> list[dict]:
    order = {"低风险": 0, "中风险": 1, "较高风险": 2, "高风险": 3}
    threshold = order.get(min_level, 1)
    return [item for item in warnings if order.get(item["risk_level"], 0) >= threshold]


def filter_by_region(warnings: list[dict], region: str) -> list[dict]:
    return [item for item in warnings if region in item.get("region", "")]


def filter_by_product(warnings: list[dict], product: str) -> list[dict]:
    return [item for item in warnings if product in item.get("product", "")]


def level_summary(warnings: list[dict]) -> Counter:
    return Counter(item["risk_level"] for item in warnings)

