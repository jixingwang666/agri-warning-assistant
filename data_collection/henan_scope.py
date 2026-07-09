HENAN_PROVINCE = "河南"

HENAN_CITIES = [
    "郑州",
    "开封",
    "洛阳",
    "平顶山",
    "安阳",
    "鹤壁",
    "新乡",
    "焦作",
    "濮阳",
    "许昌",
    "漯河",
    "三门峡",
    "南阳",
    "商丘",
    "信阳",
    "周口",
    "驻马店",
    "济源",
]

CITY_ALIASES = {
    "郑州市": "郑州",
    "开封市": "开封",
    "洛阳市": "洛阳",
    "平顶山市": "平顶山",
    "安阳市": "安阳",
    "鹤壁市": "鹤壁",
    "新乡市": "新乡",
    "焦作市": "焦作",
    "濮阳市": "濮阳",
    "许昌市": "许昌",
    "漯河市": "漯河",
    "三门峡市": "三门峡",
    "南阳市": "南阳",
    "商丘市": "商丘",
    "信阳市": "信阳",
    "周口市": "周口",
    "驻马店市": "驻马店",
    "济源市": "济源",
    "中牟": "郑州",
    "滑县": "安阳",
    "内黄": "安阳",
    "浚县": "鹤壁",
    "兰考": "开封",
    "扶沟": "周口",
    "太康": "周口",
    "西华": "周口",
    "永城": "商丘",
    "固始": "信阳",
    "唐河": "南阳",
    "邓州": "南阳",
    "遂平": "驻马店",
    "正阳": "驻马店",
}

REGION_ALIASES = {
    "豫北": ["安阳", "鹤壁", "新乡", "焦作", "濮阳"],
    "豫东": ["开封", "商丘", "周口"],
    "豫西": ["洛阳", "三门峡"],
    "豫南": ["南阳", "信阳", "驻马店"],
    "豫中": ["郑州", "许昌", "漯河", "平顶山"],
    "黄淮": ["周口", "驻马店", "商丘", "信阳"],
    "淮河以北": ["信阳", "驻马店", "周口", "商丘"],
}

CROP_PROFILES = {
    "小麦": {
        "cities": ["周口", "驻马店", "商丘", "南阳", "新乡", "安阳"],
        "risks": ["病虫害", "气象灾害", "价格波动"],
    },
    "玉米": {
        "cities": ["周口", "商丘", "开封", "新乡", "南阳"],
        "risks": ["气象灾害", "市场供需", "价格波动"],
    },
    "花生": {
        "cities": ["驻马店", "南阳", "开封", "商丘"],
        "risks": ["气象灾害", "市场供需", "价格波动"],
    },
    "大豆": {
        "cities": ["周口", "商丘", "南阳"],
        "risks": ["气象灾害", "市场供需"],
    },
    "蔬菜": {
        "cities": ["郑州", "开封", "周口", "安阳"],
        "risks": ["价格波动", "气象灾害", "市场供需"],
    },
    "生猪": {
        "cities": HENAN_CITIES,
        "risks": ["价格波动", "市场供需"],
    },
}

OFFICIAL_SOURCE_KEYWORDS = [
    "农业农村厅",
    "农业农村局",
    "气象局",
    "气象台",
    "发展改革委",
    "发改委",
    "政府",
    "中央气象台",
    "农业农村部",
]


def detect_henan_city(*texts: object) -> str:
    combined = " ".join(str(text or "") for text in texts)
    for alias, city in CITY_ALIASES.items():
        if alias in combined:
            return city
    for city in HENAN_CITIES:
        if city in combined:
            return city
    return ""


def detect_region_group(*texts: object) -> str:
    combined = " ".join(str(text or "") for text in texts)
    for group in REGION_ALIASES:
        if group in combined:
            return group
    return ""


def is_henan_related(*texts: object) -> bool:
    combined = " ".join(str(text or "") for text in texts)
    if HENAN_PROVINCE in combined or "河南省" in combined:
        return True
    if detect_henan_city(combined) or detect_region_group(combined):
        return True
    return False


def normalize_henan_region(region: str, *texts: object) -> str:
    city = detect_henan_city(region, *texts)
    if city:
        return city
    group = detect_region_group(region, *texts)
    if group:
        return group
    if is_henan_related(region, *texts):
        return HENAN_PROVINCE
    return region or ""


def infer_province(region: str, *texts: object) -> str:
    return HENAN_PROVINCE if is_henan_related(region, *texts) else ""


def source_credibility(source: str) -> float:
    if not source:
        return 0.0
    if any(word in source for word in OFFICIAL_SOURCE_KEYWORDS):
        return 8.0
    if "河南" in source:
        return 5.0
    return 2.0


def crop_region_bonus(product: str, region: str) -> float:
    profile = CROP_PROFILES.get(product)
    if not profile:
        return 0.0
    city = detect_henan_city(region)
    if city and city in profile["cities"]:
        return 8.0
    group = detect_region_group(region)
    if group and any(city in profile["cities"] for city in REGION_ALIASES[group]):
        return 5.0
    if region == HENAN_PROVINCE:
        return 3.0
    return 0.0
