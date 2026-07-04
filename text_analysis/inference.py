"""Inference interface for the trained agricultural classifier.

Supports both BERT (bert-base-chinese fine-tuned) and TextCNN (TorchScript) models.
Provides a drop-in classify_news() function compatible with the existing pipeline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_MODEL_DIR = Path(__file__).resolve().parent / "models"
_META_PATH = _MODEL_DIR / "model_meta.json"
_BERT_PATH = _MODEL_DIR / "bert_agri_classifier"
_CNN_PATH = _MODEL_DIR / "textcnn_agri_classifier.pt"

# ── Lazy load cache ─────────────────────────────────────────────────
_model = None
_tokenizer = None
_label2id = None
_id2label = None
_model_type = None  # "bert" | "textcnn" | None
_max_seq_len = 256


def _load_bert_model():
    """Lazy-load the fine-tuned BERT model."""
    global _model, _tokenizer, _label2id, _id2label, _model_type, _max_seq_len

    if not _BERT_PATH.exists():
        return False

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
    except ImportError:
        return False

    meta = json.loads(_META_PATH.read_text(encoding="utf-8"))
    _label2id = meta["label2id"]
    _id2label = {int(k): v for k, v in meta["id2label"].items()}
    _max_seq_len = meta.get("max_seq_len", 256)

    _tokenizer = AutoTokenizer.from_pretrained(str(_BERT_PATH))
    _model = AutoModelForSequenceClassification.from_pretrained(str(_BERT_PATH))
    _model.eval()
    _model_type = "bert"
    return True


def _load_cnn_model():
    """Lazy-load the TextCNN model (fallback)."""
    global _model, _label2id, _id2label, _model_type, _max_seq_len

    if not _CNN_PATH.exists() or not _META_PATH.exists():
        return False

    try:
        import torch
    except ImportError:
        return False

    meta = json.loads(_META_PATH.read_text(encoding="utf-8"))
    _vocab_local = meta.get("vocab", {})
    _label2id_local = meta.get("label2id", {})

    if not _vocab_local or not _label2id_local:
        # Old TextCNN format
        return False

    _id2label_local = {int(k): v for k, v in meta.get("id2label", {}).items()}
    _max_seq_len_local = meta.get("max_seq_len", 200)

    try:
        model = torch.jit.load(str(_CNN_PATH))
    except Exception:
        return False

    model.eval()
    # Store in local scope for TextCNN path
    globals()["_cnn_model"] = model
    globals()["_cnn_vocab"] = _vocab_local
    globals()["_cnn_label2id"] = _label2id_local
    globals()["_cnn_id2label"] = _id2label_local
    globals()["_cnn_max_seq_len"] = _max_seq_len_local
    _model_type_local = "textcnn"
    return True


def _load_model():
    """Load the best available model. BERT preferred over TextCNN."""
    global _model_type
    if _model_type is not None:
        return True
    if _load_bert_model():
        return True
    if _load_cnn_model():
        return True
    return False


def classify_news_model(title: str, content: str) -> str | None:
    """Classify using the local trained model (BERT or TextCNN).

    Returns the predicted category string, or None if no model is available.
    """
    if not _load_model():
        return None

    text = f"{title} {content}"

    if _model_type == "bert":
        import torch
        inputs = _tokenizer(
            text, truncation=True, padding="max_length",
            max_length=_max_seq_len, return_tensors="pt",
        )
        with torch.no_grad():
            outputs = _model(**inputs)
            pred = outputs.logits.argmax(dim=1).item()
        return _id2label.get(pred)

    if _model_type == "textcnn":
        import torch
        vocab = globals()["_cnn_vocab"]
        max_len = globals()["_cnn_max_seq_len"]
        model = globals()["_cnn_model"]
        id2label_local = globals()["_cnn_id2label"]

        ids = [vocab.get(char, vocab.get("<UNK>", 1)) for char in text[:max_len]]
        if len(ids) < max_len:
            ids.extend([vocab.get("<PAD>", 0)] * (max_len - len(ids)))
        input_ids = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            outputs = model(input_ids)
            pred = outputs.argmax(dim=1).item()
        return id2label_local.get(pred)

    return None


def classify_with_confidence(title: str, content: str) -> dict | None:
    """Classify with confidence scores for all categories.

    Returns {"category": str, "confidence": float, "scores": {label: prob}}
    or None if no model available.
    """
    if not _load_model():
        return None

    text = f"{title} {content}"

    if _model_type == "bert":
        import torch
        inputs = _tokenizer(
            text, truncation=True, padding="max_length",
            max_length=_max_seq_len, return_tensors="pt",
        )
        with torch.no_grad():
            outputs = _model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1)[0]

        scores = {}
        for i, prob in enumerate(probs.tolist()):
            label = _id2label.get(i, f"class_{i}")
            scores[label] = round(prob, 4)

        best_idx = probs.argmax().item()
        return {
            "category": _id2label[best_idx],
            "confidence": round(probs[best_idx].item(), 4),
            "scores": scores,
        }

    if _model_type == "textcnn":
        import torch
        vocab = globals()["_cnn_vocab"]
        max_len = globals()["_cnn_max_seq_len"]
        model = globals()["_cnn_model"]
        id2label_local = globals()["_cnn_id2label"]

        ids = [vocab.get(char, vocab.get("<UNK>", 1)) for char in text[:max_len]]
        if len(ids) < max_len:
            ids.extend([vocab.get("<PAD>", 0)] * (max_len - len(ids)))
        input_ids = torch.tensor([ids], dtype=torch.long)
        with torch.no_grad():
            outputs = model(input_ids)
            probs = torch.softmax(outputs, dim=1)[0]

        scores = {}
        for i, prob in enumerate(probs.tolist()):
            label = id2label_local.get(str(i), f"class_{i}")
            scores[label] = round(prob, 4)

        best_idx = probs.argmax().item()
        return {
            "category": id2label_local.get(str(best_idx), "unknown"),
            "confidence": round(probs[best_idx].item(), 4),
            "scores": scores,
        }

    return None


def model_available() -> bool:
    """Check if any trained model exists."""
    return _load_model()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    if not model_available():
        print("No trained model found. Run train_classifier.py first.")
        sys.exit(1)

    print(f"Model type: {_model_type}")

    test_cases = [
        ("河南多地发布小麦赤霉病防治提醒", "受近期连续降雨影响，部分地区小麦赤霉病发生风险增加"),
        ("农业部门提示强降雨天气下加强农田排涝", "气象部门预计未来三天局部地区有强降雨"),
        ("郑州蔬菜供应总体平稳价格小幅波动", "本周郑州主要批发市场蔬菜供应充足"),
        ("本地农产品电商助力特色水果销售", "多家合作社通过线上平台拓展销售渠道"),
        ("玉米苗期管理进入关键阶段", "专家建议加强水肥管理和病虫害监测"),
        ("农业农村部发布新一轮粮食补贴政策", "扶持粮食主产区农户，保障粮食安全"),
    ]

    print("\n模型分类测试\n")
    for title, content in test_cases:
        result = classify_with_confidence(title, content)
        if result:
            top_cat = result["category"]
            conf = result["confidence"]
            print(f"  [{top_cat}] (conf={conf:.3f})")
            print(f"    {title}")
            top3 = sorted(result["scores"].items(), key=lambda x: -x[1])[:3]
            print(f"    Top-3: {', '.join(f'{l}:{s:.2f}' for l, s in top3)}")
            print()
