from collections import Counter

from risk_rules import SUGGESTION_TEMPLATES
from scorer import build_context_scores, score_news_item


def has_warning_signal(record: dict) -> bool:
    return any(
        float(record.get(key, 0) or 0) > 0
        for key in ("keyword_score", "price_score", "evidence_score")
    )


def mark_observation_record(record: dict) -> dict:
    record["risk_type"] = "低风险观察"
    record["risk_score"] = min(float(record.get("risk_score", 0) or 0), 15)
    record["risk_level"] = "低风险"
    record["confidence"] = min(float(record.get("confidence", 0) or 0), 45)
    record["trigger_words"] = "未发现明显风险词"
    record["evidence_summary"] = "未匹配到明确风险关键词、价格波动或本地旁证"
    record["reason"] = "该农业新闻暂未识别到明确风险关键词，也未匹配到有效价格或气象旁证，系统保留为低风险观察记录。"
    record["suggestion"] = "建议仅作日常关注，不触发预警处置；如后续出现气象、价格或病虫害旁证，再重新评估。"
    return record


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
    if record.get("evidence_summary"):
        reason += f" 证据链摘要：{record['evidence_summary']}。"
    return reason


def generate_warnings(news_items: list[dict], price_changes: dict[tuple[str, str], dict], use_llm: bool = True) -> list[dict]:
    category_counter, region_counter = build_context_scores(news_items)
    warnings = []
    for item in news_items:
        record = score_news_item(item, category_counter, region_counter, price_changes)
        if not has_warning_signal(record):
            record = mark_observation_record(record)
        else:
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

