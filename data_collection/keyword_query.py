"""关键词自动生成：农业主体词 × 地区词 × 风险词 → 搜索查询。

产出如 "河南 小麦 赤霉病"、"山东 蔬菜 价格" 的查询词，供反向爬取使用。
复用现有词表，避免重复维护：
- 农业主体词/风险词：text_analysis/resources/agriculture_keywords.txt
- 风险类型与关键词：risk_warning/risk_rules.py 的 RISK_KEYWORDS
- 地区词：data_collection/sources.py 的 SEARCH_REGIONS
"""

from __future__ import annotations

import sys
from pathlib import Path

from sources import MAX_QUERIES, SEARCH_REGIONS

_CURRENT_DIR = Path(__file__).resolve().parent
_PROJECT_DIR = _CURRENT_DIR.parent
_KEYWORDS_FILE = _PROJECT_DIR / "text_analysis" / "resources" / "agriculture_keywords.txt"

# 让 RISK_KEYWORDS 可被导入（standalone 运行时 risk_warning 未必在 sys.path 上）。
_RISK_DIR = _PROJECT_DIR / "risk_warning"
if str(_RISK_DIR) not in sys.path:
    sys.path.insert(0, str(_RISK_DIR))

try:
    from risk_rules import RISK_KEYWORDS  # noqa: E402
except Exception:  # pragma: no cover - 词表缺失时降级
    RISK_KEYWORDS = {}

# 作为「农业主体」参与组合的核心作物/主体词（从词表中挑选，避免和风险词重复）。
_CORE_SUBJECTS = [
    "小麦", "玉米", "大豆", "水稻", "蔬菜", "水果", "生猪", "农产品",
]

# 每个风险类型挑选的代表性风险词（取 RISK_KEYWORDS 每类前若干个）。
_RISK_WORDS_PER_TYPE = 3


def _load_subject_words() -> list[str]:
    """读取农业词表作为主体词来源，失败则用内置核心词。"""
    words = list(_CORE_SUBJECTS)
    try:
        for line in _KEYWORDS_FILE.read_text(encoding="utf-8").splitlines():
            word = line.strip()
            if word and word not in words:
                words.append(word)
    except OSError:
        pass
    return words


def _risk_pairs() -> list[tuple[str, str]]:
    """返回 (风险类型, 风险词) 组合，风险词取自 RISK_KEYWORDS。"""
    pairs: list[tuple[str, str]] = []
    for risk_type, config in RISK_KEYWORDS.items():
        for word in config.get("keywords", [])[:_RISK_WORDS_PER_TYPE]:
            pairs.append((risk_type, word))
    return pairs


def build_search_queries(max_queries: int = MAX_QUERIES) -> list[dict]:
    """生成查询词列表。

    返回 [{"query": "河南 小麦 赤霉病", "region": "河南", "risk_type": "病虫害"}, ...]
    query 携带地区上下文，抓到的新闻会回填 region 供下游风险评分使用。
    组合规模受 max_queries 截断，避免请求量爆炸。
    """
    subjects = _load_subject_words()
    risk_pairs = _risk_pairs()
    regions = SEARCH_REGIONS or [""]

    queries: list[dict] = []
    seen: set[str] = set()

    # 地区 × 风险词(带主体) 交替组合，保证覆盖多地区多风险类型。
    for region in regions:
        for subject in subjects:
            for risk_type, risk_word in risk_pairs:
                # 主题词在前、地区在后，通用检索相关性更好。
                parts = [p for p in (subject, risk_word, region) if p]
                query = " ".join(parts)
                if query in seen:
                    continue
                seen.add(query)
                queries.append(
                    {"query": query, "region": region, "risk_type": risk_type}
                )
                if len(queries) >= max_queries:
                    return queries
    return queries


def parse_manual_keywords(keywords: str, region: str = "") -> list[dict]:
    """把用户传入的关键词字符串转成查询列表。

    以逗号/顿号/换行分隔多个查询；每个查询内部的空格保留（如 "河南 小麦"）。
    """
    if not keywords:
        return []
    raw = keywords.replace("\n", ",").replace("，", ",").replace("、", ",")
    items = [k.strip() for k in raw.split(",") if k.strip()]
    return [{"query": k, "region": region, "risk_type": ""} for k in items]
