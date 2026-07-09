"""评估推理门控效果：对比 规则 / 模型 / 新离线链路(规则优先+模型兜底)。

在两个分布上测：
- AgriCHN 测试集(短文本，规则弱、模型强)
- labeled_news.csv(真实新闻，规则强、模型弱)
新链路应在两个分布上都接近各自的最优，验证「取长补短」。
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

from classifier import (  # noqa: E402
    classify_news_offline,
    classify_news_rule,
)
from inference import classify_news_model, model_available  # noqa: E402

TRAIN_DIR = CURRENT_DIR / "training_data"
LABELED_FILE = CURRENT_DIR / "resources" / "labeled_news.csv"


def _acc(preds: list[str], golds: list[str]) -> float:
    correct = sum(1 for p, g in zip(preds, golds) if p == g)
    return correct / len(golds) if golds else 0.0


def eval_set(name: str, samples: list[tuple[str, str, str]]) -> None:
    """samples: list of (title, content, gold_label)."""
    golds = [s[2] for s in samples]
    rule = [classify_news_rule(t, c) for t, c, _ in samples]
    model = [(classify_news_model(t, c) or "其他") for t, c, _ in samples]
    gated = [classify_news_offline(t, c) for t, c, _ in samples]

    print(f"\n== {name} (n={len(samples)}) ==")
    print(f"  规则(rule)         : {_acc(rule, golds):.3f}")
    print(f"  模型(model)        : {_acc(model, golds):.3f}")
    print(f"  新链路(rule→model) : {_acc(gated, golds):.3f}")


def load_agrichn(limit: int | None = None) -> list[tuple[str, str, str]]:
    path = TRAIN_DIR / "classification_test_single.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if limit:
        data = data[:limit]
    return [("", d["text"], d["label"]) for d in data]


def load_labeled_news() -> list[tuple[str, str, str]]:
    with open(LABELED_FILE, "r", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    return [(r["title"], r["content"], r["label"]) for r in rows]


def main() -> None:
    if not model_available():
        print("未找到本地模型，无法评估。请先训练 train_classifier.py。")
        return
    # AgriCHN 全量可能较慢，可用 limit 采样；此处全量。
    eval_set("AgriCHN 短文本测试集", load_agrichn())
    eval_set("labeled_news 真实新闻", load_labeled_news())


if __name__ == "__main__":
    main()
