from collections import Counter

from price_monitor import find_price_signal
from risk_rules import POSITIVE_OR_STABLE_WORDS, PRODUCT_KEYWORDS, RISK_KEYWORDS


def detect_product(text: str) -> str:
    for product, words in PRODUCT_KEYWORDS.items():
        if any(word in text for word in words):
            return product
    return ""


def detect_risk_type_and_words(text: str) -> tuple[str, list[str], int]:
    best_type = "综合风险"
    best_words: list[str] = []
    best_score = 0

    for risk_type, config in RISK_KEYWORDS.items():
        words = [word for word in config["keywords"] if word in text]
        if not words:
            continue
        score = config["base_score"] + len(words) * 7
        if score > best_score:
            best_type = risk_type
            best_words = words
            best_score = score

    return best_type, best_words, best_score


def detect_risk_type_hybrid(title: str, content: str) -> tuple[str, list[str], float]:
    """Detect risk type with optional LLM enhancement.

    LLM-first: if LLM returns a high-confidence result, use its keywords.
    Falls back to rule-based keyword matching on failure.
    """
    # Try LLM first
    try:
        from llm_classifier import detect_risk_type_with_llm  # noqa: F811
        result = detect_risk_type_with_llm(title, content)
        if result and result.get("confidence", 0) >= 0.7:
            risk_type = result.get("risk_type", "综合风险")
            keywords = result.get("matched_keywords", [])
            if risk_type in RISK_KEYWORDS or risk_type == "综合风险":
                base = RISK_KEYWORDS.get(risk_type, {}).get("base_score", 8)
                score = base + len(keywords) * 7
                return risk_type, keywords, float(score)
    except Exception:
        pass

    # Fall back to rules
    text = f"{title} {content}"
    return detect_risk_type_and_words(text)


def risk_level(score: float) -> str:
    if score >= 81:
        return "高风险"
    if score >= 61:
        return "较高风险"
    if score >= 31:
        return "中风险"
    return "低风险"


def build_context_scores(news_items: list[dict]) -> tuple[Counter, Counter]:
    category_counter = Counter(item.get("category", "") for item in news_items)
    region_counter = Counter(item.get("region", "") for item in news_items)
    return category_counter, region_counter


def score_news_item(
    item: dict,
    category_counter: Counter,
    region_counter: Counter,
    price_changes: dict[tuple[str, str], dict],
) -> dict:
    title = item.get("title", "")
    content = item.get("content", "")
    summary = item.get("summary", "")
    keywords = item.get("keywords", "")
    region = item.get("region", "")
    category = item.get("category", "")
    text = f"{title} {summary} {keywords}"

    product = detect_product(text)
    # Hybrid risk detection: LLM → rules fallback
    risk_type, trigger_words, keyword_score = detect_risk_type_hybrid(title, content)

    heat_score = min(max(category_counter.get(category, 0) - 1, 0) * 5, 15)
    region_score = min(max(region_counter.get(region, 0) - 1, 0) * 4, 12)

    price_signal = find_price_signal(product, region, price_changes)
    price_score = float(price_signal.get("score", 0))
    if price_score and "价格" not in trigger_words:
        trigger_words.append("价格波动")

    positive_adjustment = 0
    if any(word in text for word in POSITIVE_OR_STABLE_WORDS):
        positive_adjustment = 18

    total_score = min(
        max(round(keyword_score + price_score + heat_score + region_score - positive_adjustment, 1), 0),
        100,
    )

    return {
        "title": title,
        "region": region,
        "product": product or "未识别",
        "risk_type": risk_type,
        "risk_score": total_score,
        "risk_level": risk_level(total_score),
        "keyword_score": round(keyword_score, 1),
        "price_score": round(price_score, 1),
        "heat_score": round(heat_score, 1),
        "region_score": round(region_score, 1),
        "positive_adjustment": round(positive_adjustment, 1),
        "trigger_words": "、".join(trigger_words) if trigger_words else "未发现明显风险词",
        "url": item.get("url", ""),
        "source": item.get("source", ""),
        "category": category,
        "price_signal": price_signal,
    }
