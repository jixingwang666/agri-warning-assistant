from __future__ import annotations

import json
from datetime import datetime

from henan_scope import HENAN_CITIES, detect_henan_city, normalize_henan_region, source_credibility


WEATHER_TERMS = ["气象", "天气", "降雨", "暴雨", "洪水", "汛情", "干旱", "高温", "低温", "预警"]
PRICE_TERMS = ["价格", "行情", "批发", "市场", "涨价", "下跌", "波动"]


def _date_label(value: object) -> str:
    text = str(value or "").strip()
    for separator in (" ", "T"):
        if separator in text:
            text = text.split(separator, 1)[0]
    if len(text) >= 10 and text[4] in "-/" and text[7] in "-/":
        return text[:10].replace("/", "-")
    return ""


def _days_apart(left: str, right: str) -> int | None:
    if not left or not right:
        return None
    try:
        first = datetime.strptime(left, "%Y-%m-%d")
        second = datetime.strptime(right, "%Y-%m-%d")
    except ValueError:
        return None
    return abs((first - second).days)


def _split_words(value: object) -> list[str]:
    text = str(value or "").replace("，", "、").replace(",", "、")
    return [word.strip() for word in text.split("、") if word.strip()]


def _dedupe_links(links: list[dict], limit: int = 4) -> list[dict]:
    seen = set()
    result = []
    for link in links:
        url = link.get("url", "")
        key = url or link.get("name", "")
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(link)
        if len(result) >= limit:
            break
    return result


def _score_link(news: dict, evidence: dict, terms: list[str]) -> tuple[float, str]:
    news_region = normalize_henan_region(news.get("region", ""), news.get("title", ""), news.get("summary", ""))
    evidence_text = f"{evidence.get('title', '')} {evidence.get('content', '')} {evidence.get('keywords', '')}"
    evidence_region = normalize_henan_region("", evidence_text)
    news_city = detect_henan_city(news_region, news.get("title", ""), news.get("summary", ""))
    evidence_city = detect_henan_city(evidence_region, evidence_text)

    # Do not trust the source-level default region for evidence. A national page
    # must explicitly mention Henan or a Henan city before it can support a
    # local Henan warning.
    local_terms = ["河南", *HENAN_CITIES]
    if not any(term in evidence_text for term in local_terms):
        return 0, ""

    text = f"{evidence_text} {evidence.get('category', '')}"
    matched_terms = [term for term in terms if term in text]
    if not matched_terms:
        return 0, ""

    source_score = min(source_credibility(evidence.get("source", "")), 5)
    if news_city and evidence_city and news_city == evidence_city:
        region_score = 4
    elif news_region and evidence_region and (news_region in evidence_region or evidence_region in news_region):
        region_score = 3
    elif "河南" in {news_region, evidence_region}:
        region_score = 2
    else:
        region_score = 0

    days = _days_apart(_date_label(news.get("publish_time", "")), _date_label(evidence.get("publish_time", "")))
    if days is None:
        time_score = 1
    elif days <= 1:
        time_score = 4
    elif days <= 3:
        time_score = 3
    elif days <= 7:
        time_score = 2
    else:
        time_score = 0

    keyword_score = min(len(matched_terms), 4)
    score = source_score + region_score + time_score + keyword_score
    note = f"匹配词：{'、'.join(matched_terms[:4])}；地区分{region_score}，时间分{time_score}"
    return round(score, 1), note


def collect_evidence_for_news(news_items: list[dict], evidence_items: list[dict], price_sources: list[dict]) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for news in news_items:
        trigger_words = _split_words(news.get("keywords", ""))
        title_text = f"{news.get('title', '')} {news.get('summary', '')} {news.get('content', '')} {' '.join(trigger_words)}"
        needs_weather = any(term in title_text for term in WEATHER_TERMS)
        needs_price = any(term in title_text for term in PRICE_TERMS)

        links: list[dict] = []
        weather_scores = []
        if needs_weather:
            for evidence in evidence_items:
                score, note = _score_link(news, evidence, WEATHER_TERMS + trigger_words[:4])
                if score <= 0:
                    continue
                weather_scores.append(score)
                links.append({
                    "type": "weather",
                    "name": evidence.get("title") or evidence.get("source") or "气象旁证",
                    "url": evidence.get("url", ""),
                    "note": note,
                    "score": score,
                })

        price_scores = []
        if needs_price:
            for source in price_sources[:2]:
                url = source.get("url") or source.get("path") or ""
                if not url:
                    continue
                price_scores.append(4)
                links.append({
                    "type": "price",
                    "name": source.get("name", "价格旁证"),
                    "url": url,
                    "note": "价格/行情关键词触发，使用该来源核验市场波动",
                    "score": 4,
                })

        best_weather = max(weather_scores, default=0)
        best_price = max(price_scores, default=0)
        consistency = min(max(len(weather_scores) + len(price_scores) - 1, 0), 3)
        score = min(best_weather + best_price + consistency, 20)
        links = sorted(_dedupe_links(links), key=lambda item: item.get("score", 0), reverse=True)
        summary = f"证据验证分:{round(score, 1)};气象旁证:{len(weather_scores)};价格旁证:{len(price_scores)}"
        result[news.get("url", "")] = {
            "score": round(score, 1),
            "summary": summary,
            "links": links,
            "links_json": json.dumps(links, ensure_ascii=False),
        }
    return result
