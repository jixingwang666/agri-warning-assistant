"""用 LLM(DeepSeek) 自动标注真实爬取新闻，构建「真实分布」训练集。

修复 test_results/test_2_model.md 记录的核心问题(ISSUE-MD-001)：本地模型只在
AgriCHN 短句上训练，迁移到真实全文新闻时准确率骤降。做法：
- 读取反向爬虫产出的真实新闻(CSV，默认 data_collection/output/*.csv)。
- 调 classify_news_with_llm 用 DeepSeek 打标(zero-shot，准确率高)。
- 只保留高置信(>=阈值)、属于 6 个类别的样本，去重。
- 追加写入 training_data/realnews_single.json，供 train_classifier 混入重训。

需要 AGRI_LLM_ENABLED=true 且已配置 API Key(见 data_management/config.py)。
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

CURRENT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(CURRENT_DIR))

from classifier import VALID_CATEGORIES  # noqa: E402
from llm_classifier import classify_news_with_llm  # noqa: E402

_COLLECTION_OUTPUT = CURRENT_DIR.parent / "data_collection" / "output"
DEFAULT_INPUTS = [
    _COLLECTION_OUTPUT / "search_crawler_news.csv",
    _COLLECTION_OUTPUT / "crawler_news.csv",
]
OUTPUT_FILE = CURRENT_DIR / "training_data" / "realnews_single.json"

CONFIDENCE_THRESHOLD = 0.80
MAX_TEXT_CHARS = 400


def read_news_csv(paths: list[Path]) -> list[dict]:
    rows: list[dict] = []
    for path in paths:
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                title = (row.get("title") or "").strip()
                content = (row.get("content") or "").strip()
                if title:
                    rows.append({"title": title, "content": content})
    return rows


def _load_existing() -> tuple[list[dict], set[str]]:
    if not OUTPUT_FILE.exists():
        return [], set()
    data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    seen = {d["text"] for d in data}
    return data, seen


def build(paths: list[Path] | None = None, threshold: float = CONFIDENCE_THRESHOLD) -> None:
    paths = paths or DEFAULT_INPUTS
    news = read_news_csv(paths)
    if not news:
        print("没有可标注的新闻。请先运行反向爬虫产出 CSV。")
        return

    samples, seen = _load_existing()
    added = 0
    skipped_lowconf = 0
    skipped_other = 0

    for item in news:
        title = item["title"]
        content = item["content"]
        text = f"{title} {content}".strip()[:MAX_TEXT_CHARS]
        if text in seen:
            continue

        result = classify_news_with_llm(title, content)
        if not result:
            continue
        category = result.get("category")
        confidence = float(result.get("confidence", 0.0))

        if category not in VALID_CATEGORIES or category == "其他":
            skipped_other += 1
            continue
        if confidence < threshold:
            skipped_lowconf += 1
            continue

        samples.append({"text": text, "label": category})
        seen.add(text)
        added += 1

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(
        json.dumps(samples, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print("真实新闻自动标注完成")
    print(f"  输入新闻: {len(news)} 条")
    print(f"  新增标注: {added} 条 (低置信丢弃 {skipped_lowconf}, 其他类丢弃 {skipped_other})")
    print(f"  累计样本: {len(samples)} 条 -> {OUTPUT_FILE}")
    label_counts: dict[str, int] = {}
    for s in samples:
        label_counts[s["label"]] = label_counts.get(s["label"], 0) + 1
    for lbl, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
        print(f"    {lbl}: {cnt}")


if __name__ == "__main__":
    build()
