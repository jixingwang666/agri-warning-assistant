PRIMARY_NEWS_SOURCES = [
    {
        "name": "河南省农业农村厅",
        "base_url": "https://nynct.henan.gov.cn/",
        "list_url": "https://nynct.henan.gov.cn/",
        "region": "河南",
        "category": "农业新闻",
        "source_level": "province",
    },
    {
        "name": "农业农村部",
        "base_url": "https://www.moa.gov.cn/",
        "list_url": "https://www.moa.gov.cn/xw/",
        "region": "河南",
        "category": "农业政策",
        "source_level": "national",
    },
]

EVIDENCE_NEWS_SOURCES = [
    {
        "name": "河南省气象局",
        "base_url": "https://ha.cma.gov.cn/",
        "list_url": "https://ha.cma.gov.cn/",
        "region": "河南",
        "category": "气象灾害",
        "source_level": "province",
        "verify_ssl": False,
    },
    {
        "name": "中央气象台农业气象",
        "base_url": "https://www.nmc.cn/",
        "list_url": "https://www.nmc.cn/",
        "region": "河南",
        "category": "气象灾害",
        "source_level": "national",
    },
]

NEWS_SOURCES = PRIMARY_NEWS_SOURCES + EVIDENCE_NEWS_SOURCES

PRICE_SOURCES = [
    {
        "name": "农业农村部农产品批发价格",
        "type": "official_reference",
        "url": "https://zdscxx.moa.gov.cn/",
        "province": "全国",
        "source_level": "national",
    },
]

# 搜索引擎反向爬取配置：关键词 -> 搜索引擎 -> 结果链接 -> 抓正文。
# 与上面的列表页采集并存，主要用于补充本地农业新闻和旁证线索。
SEARCH_ENGINE = "baidu"
SEARCH_ENGINE_FALLBACKS = ["bing", "sogou", "so360"]
SEARCH_REGIONS = [
    "河南",
    "郑州",
    "开封",
    "洛阳",
    "南阳",
    "商丘",
]
SEARCH_LIMIT_PER_QUERY = 5
MAX_QUERIES = 20
SEARCH_DELAY = 1.0
