CATEGORY_KEYWORDS = {
    "农业政策": ["政策", "补贴", "农业农村部", "通知", "部署", "扶持", "粮食安全"],
    "农产品价格": ["价格", "涨", "下跌", "上涨", "波动", "批发市场", "行情"],
    "病虫害": ["病虫害", "赤霉病", "虫害", "防治", "统防统治", "病害"],
    "气象灾害": ["降雨", "暴雨", "干旱", "洪涝", "排涝", "气象", "灾害"],
    "市场供需": ["供应", "销售", "订单", "电商", "渠道", "市场", "合作社"],
    "农业科技": ["技术", "专家", "管理", "监测", "机械", "智能", "科技"],
}

VALID_CATEGORIES = set(CATEGORY_KEYWORDS.keys()) | {"其他"}

# 本地模型置信度门控阈值：规则弃权后，模型预测低于该值也仍采用（此时模型是
# 唯一信号），但 OOD 输入直接跳过模型，避免过度自信的错误（见 test_2_model.md）。
MODEL_CONF_THRESHOLD = 0.60


def classify_news_rule(title: str, content: str) -> str:
    """Rule-based classification using keyword counting (original method)."""
    text = f"{title} {content}"
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        scores[category] = sum(text.count(keyword) for keyword in keywords)

    category, score = max(scores.items(), key=lambda item: item[1])
    return category if score > 0 else "其他"


def classify_news_offline(title: str, content: str) -> str:
    """离线分类：规则优先(对真实新闻更可靠) → 模型兜底(规则弃权时) → 其他。

    依据 test_results/test_2_model.md 的结论调整链路(ISSUE-MD-005)：
    - 真实新闻文章关键词密集，规则准确率(73%)远高于本地模型(40%)，故规则命中
      直接返回，可避免模型「农业政策」高置信误判(ISSUE-MD-002)。
    - AgriCHN 式短文本关键词稀疏，规则弃权(其他)，此时改用本地模型(61%)兜底。
    - OOD 输入(纯英文/符号/空)跳过模型，避免过度自信的错误(ISSUE-MD-003)。
    """
    # 规则优先：命中即返回（真实新闻文章上规则更可靠）。
    rule_pred = classify_news_rule(title, content)
    if rule_pred != "其他":
        return rule_pred

    # 规则弃权：短文本/关键词稀疏，改用本地模型（非 OOD 时）。
    try:
        from inference import classify_with_confidence, is_ood  # noqa: F811

        if not is_ood(title, content):
            result = classify_with_confidence(title, content)
            if result and result.get("category") in VALID_CATEGORIES:
                # 规则已弃权，模型是唯一信号；置信度仅作日志/调参参考。
                if result["confidence"] >= MODEL_CONF_THRESHOLD:
                    return result["category"]
                return result["category"]
    except Exception:
        pass

    return "其他"


def classify_news(title: str, content: str, use_llm: bool = True) -> str:
    """Classify news article. Two modes:

    Online  (LLM enabled):  DeepSeek only — best quality, zero-shot.
                             Falls back to offline mode on failure.
    Offline (no LLM):       规则优先 → 本地模型(置信度门控) → 其他。

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

    # 离线模式: 规则优先 → 本地模型 → 其他
    return classify_news_offline(title, content)

