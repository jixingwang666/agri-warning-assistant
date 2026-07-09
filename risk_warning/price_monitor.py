from collections import defaultdict

from henan_scope import detect_henan_city, normalize_henan_region


SOURCE_LEVEL_WEIGHT = {
    "city": 1.15,
    "市级": 1.15,
    "market": 1.1,
    "市场": 1.1,
    "province": 1.0,
    "省级": 1.0,
    "national": 0.85,
    "全国": 0.85,
}


def build_price_change_map(price_items: list[dict]) -> dict[tuple[str, str], dict]:
    grouped = defaultdict(list)
    for item in price_items:
        product = item.get("product_name", "")
        region = normalize_henan_region(item.get("region", ""), item.get("city", ""))
        if not product or not region:
            continue
        grouped[(product, region)].append(item)

    changes = {}
    for key, rows in grouped.items():
        rows = sorted(rows, key=lambda row: row.get("date", ""))
        if len(rows) < 2:
            continue
        first = float(rows[0].get("price", 0) or 0)
        last = float(rows[-1].get("price", 0) or 0)
        if first <= 0:
            continue
        change_rate = (last - first) / first
        source_level = rows[-1].get("source_level", "")
        level_weight = SOURCE_LEVEL_WEIGHT.get(source_level, 1.0)
        changes[key] = {
            "first_price": first,
            "last_price": last,
            "change_rate": change_rate,
            "score": min(abs(change_rate) * 220 * level_weight, 25),
            "region": key[1],
            "city": detect_henan_city(key[1], rows[-1].get("city", "")),
            "source_level": source_level,
            "market_name": rows[-1].get("market_name", ""),
            "source": rows[-1].get("source", ""),
            "source_url": rows[-1].get("source_url", ""),
        }
    return changes


def find_price_signal(product: str, region: str, price_changes: dict[tuple[str, str], dict]) -> dict:
    normalized_region = normalize_henan_region(region)
    city = detect_henan_city(normalized_region)

    if not product:
        candidates = []
        for (_price_product, price_region), signal in price_changes.items():
            if (
                normalized_region
                and normalized_region != "河南"
                and price_region != normalized_region
                and not (city and price_region == city)
                and price_region != "河南"
            ):
                continue
            candidates.append(signal)
        if not candidates:
            return {}
        best = max(candidates, key=lambda item: item.get("score", 0))
        return {**best, "score": round(best.get("score", 0) * 0.6, 1), "match_level": "地区农产品旁证"}

    exact = price_changes.get((product, normalized_region))
    if exact:
        return {**exact, "match_level": "同地区"}

    if city:
        city_match = price_changes.get((product, city))
        if city_match:
            return {**city_match, "match_level": "同市"}

    province_match = price_changes.get((product, "河南"))
    if province_match:
        return {**province_match, "match_level": "河南省"}

    if normalized_region == "河南":
        province_city_candidates = [
            signal
            for (price_product, _price_region), signal in price_changes.items()
            if price_product == product
        ]
        if province_city_candidates:
            best = max(province_city_candidates, key=lambda item: item.get("score", 0))
            return {**best, "score": round(best.get("score", 0) * 0.8, 1), "match_level": "省内城市旁证"}

    for (price_product, price_region), signal in price_changes.items():
        if price_product == product and (
            not normalized_region
            or normalized_region in price_region
            or price_region in normalized_region
        ):
            return {**signal, "match_level": "模糊地区"}
    return {}
