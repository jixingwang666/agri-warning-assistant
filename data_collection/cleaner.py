import html
import re

from henan_scope import detect_henan_city, infer_province, normalize_henan_region


_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")


def clean_text(value: object) -> str:
    """Normalize scraped or imported text while keeping Chinese punctuation."""
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = _TAG_RE.sub(" ", text)
    text = text.replace("\u3000", " ")
    text = _SPACE_RE.sub(" ", text)
    return text.strip()


def clean_news_row(row: dict) -> dict:
    title = clean_text(row.get("title") or row.get("标题"))
    content = clean_text(row.get("content") or row.get("正文"))
    region = clean_text(row.get("region") or row.get("地区"))
    normalized_region = normalize_henan_region(region, title, content)
    return {
        "title": title,
        "content": content,
        "source": clean_text(row.get("source") or row.get("来源")),
        "publish_time": clean_text(row.get("publish_time") or row.get("发布时间")),
        "url": clean_text(row.get("url") or row.get("链接")),
        "region": normalized_region,
        "province": infer_province(normalized_region, title, content),
        "city": detect_henan_city(normalized_region, title, content),
        "category": clean_text(row.get("category") or row.get("分类")),
    }


def clean_price_row(row: dict) -> dict:
    raw_price = clean_text(row.get("price") or row.get("价格") or "0")
    try:
        price = float(raw_price)
    except ValueError:
        price = 0.0

    product_name = clean_text(row.get("product_name") or row.get("农产品名称"))
    region = clean_text(row.get("region") or row.get("地区"))
    city = clean_text(row.get("city") or row.get("城市")) or detect_henan_city(region)
    normalized_region = normalize_henan_region(region, city, product_name)

    return {
        "product_name": product_name,
        "price": price,
        "unit": clean_text(row.get("unit") or row.get("单位")),
        "region": normalized_region,
        "province": clean_text(row.get("province") or row.get("省份")) or infer_province(normalized_region),
        "city": city or detect_henan_city(normalized_region),
        "market_name": clean_text(row.get("market_name") or row.get("市场名称")),
        "source_level": clean_text(row.get("source_level") or row.get("来源级别")),
        "date": clean_text(row.get("date") or row.get("日期")),
        "source": clean_text(row.get("source") or row.get("来源")),
        "source_url": clean_text(row.get("source_url") or row.get("url") or row.get("链接")),
    }
