NEWS_SOURCES = [
    {
        "name": "农业农村部",
        "base_url": "https://www.moa.gov.cn/",
        "list_url": "https://www.moa.gov.cn/xw/",
        "region": "全国",
        "category": "农业政策",
    },
    {
        "name": "中国农业新闻网",
        "base_url": "https://www.farmer.com.cn/",
        "list_url": "https://www.farmer.com.cn/",
        "region": "全国",
        "category": "农业新闻",
    },
]

PRICE_SOURCES = [
    {
        "name": "演示价格数据",
        "type": "csv",
        "path": "sample_data/sample_prices.csv",
    }
]

# ── 搜索引擎反向爬取配置 ──────────────────────────────────────────
# 采集升级为「关键词 → 搜索引擎 → 结果链接 → 抓正文」，与上面的列表页
# 采集(NEWS_SOURCES)并存。引擎做成可插拔适配器(search_engines.py)。

# 默认搜索引擎，目前支持 "baidu"/"bing"/"sogou"/"so360"，可插拔扩展。
SEARCH_ENGINE = "baidu"

# 备用引擎链：主引擎被验证码/限流拦截时按顺序自动切换（见 build_engine_chain）。
# 说明：百度对脚本请求普遍返回「百度安全验证」，静态爬取常失败；bing 最稳定，
# sogou/so360 相关性更好但会在多次请求后限流。
SEARCH_ENGINE_FALLBACKS = ["bing", "sogou", "so360"]

# 目标「本地」地区词，用于和农业词、风险词组合成查询。可按需增删。
SEARCH_REGIONS = [
    "河南",
    "山东",
    "河北",
    "安徽",
    "江苏",
]

# 每个查询词从搜索引擎抓取的结果条数上限。
SEARCH_LIMIT_PER_QUERY = 5

# 自动生成的查询词总数上限，避免请求量爆炸。
MAX_QUERIES = 20

# 每次网络请求之间的礼貌性间隔(秒)，降低被搜索引擎限流/反爬的概率。
SEARCH_DELAY = 1.0

