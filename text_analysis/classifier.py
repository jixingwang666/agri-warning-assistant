CATEGORY_KEYWORDS = {
    "农业政策": ["政策", "补贴", "农业农村部", "通知", "部署", "扶持", "粮食安全"],
    "农产品价格": ["价格", "涨", "下跌", "上涨", "波动", "批发市场", "行情"],
    "病虫害": ["病虫害", "赤霉病", "虫害", "防治", "统防统治", "病害"],
    "气象灾害": ["降雨", "暴雨", "干旱", "洪涝", "排涝", "气象", "灾害"],
    "市场供需": ["供应", "销售", "订单", "电商", "渠道", "市场", "合作社"],
    "农业科技": ["技术", "专家", "管理", "监测", "机械", "智能", "科技"],
}

VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys()) | {"其他"}


def classify_news_rule(title: str, content: str) -> str:
    """Rule-based classification using keyword counting (original method)."""
    text = f"{title} {content}"
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(text.count(keyword) for keyword in keywords)

    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score > 0 else "其他"


def classify_news(title: str, content: str, use_llm: bool = True) -> str:
    """Classify news article. Two modes:

    Online  (LLM enabled):  DeepSeek only — best quality, zero-shot.
                             Falls back to offline mode on failure.
    Offline (no LLM):       BERT model → rule keywords (last resort).

    Args:
        title: News title
        content: News body text
        use_llm: If True and LLM is configured, use DeepSeek classification.
    """
    # 联网模式: LLM only
    if use_llm:
        try:
            from llm_classifier import classify_news_with_llm  # noqa: F811
            result = classify_news_with_llm(title, content)
            if result and result.get("category") in VALID_CATEGORIES:
                return result["category"]
        except Exception:
            pass
        # LLM 失败或不可用，降级到离线模式（继续往下走）

    # 离线模式: 本地 BERT 模型 → 规则关键词
    try:
        from inference import classify_news_model  # noqa: F811
        pred = classify_news_model(title, content)
        if pred and pred in VALID_CATEGORIES:
            return pred
    except Exception:
        pass

    return classify_news_rule(title, content)

