"""Train a BERT-based classifier on AgriCHN-derived data.

Fine-tunes bert-base-chinese for 6-class agricultural news classification.
Training takes ~5 minutes on RTX 4060 GPU.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    import torch
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        Trainer,
        TrainingArguments,
        EarlyStoppingCallback,
    )
    from datasets import Dataset
except ImportError:
    print("Required packages missing. Install with:")
    print("  pip install torch transformers datasets accelerate")
    sys.exit(1)

# ── Configuration ───────────────────────────────────────────────────
MODEL_NAME = "bert-base-chinese"
MAX_SEQ_LEN = 256
BATCH_SIZE = 16
LEARNING_RATE = 2e-5
NUM_EPOCHS = 10
OUTPUT_MODEL_NAME = "bert_agri_classifier"


def load_jsonl(data_dir: Path, split: str) -> list[dict]:
    path = data_dir / f"classification_{split}_single.json"
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}. Run dataset_builder.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_realnews(data_dir: Path, oversample: int = 5) -> list[dict]:
    """Load LLM-labeled real-news samples (built by build_realnews_dataset.py).

    Real-news samples fix the train/inference distribution mismatch
    (test_results/test_2_model.md, ISSUE-MD-001). They usually start scarce, so
    they are oversampled to carry weight against the large AgriCHN corpus.
    """
    path = data_dir / "realnews_single.json"
    if not path.exists():
        print("  [info] realnews_single.json not found; training on AgriCHN only.")
        return []
    samples = json.loads(path.read_text(encoding="utf-8"))
    if not samples:
        return []
    expanded = samples * max(1, oversample)
    print(f"  [info] merged {len(samples)} real-news samples x{oversample} = {len(expanded)}")
    return expanded


def build_dataset(samples: list[dict], tokenizer, label2id: dict[str, int]) -> Dataset:
    """Convert samples to HuggingFace Dataset with tokenization."""
    texts = [s["text"] for s in samples]
    labels = [label2id[s["label"]] for s in samples]

    encodings = tokenizer(
        texts,
        truncation=True,
        padding="max_length",
        max_length=MAX_SEQ_LEN,
        return_tensors=None,
    )

    return Dataset.from_dict({
        "input_ids": encodings["input_ids"],
        "attention_mask": encodings["attention_mask"],
        "labels": labels,
    })


def train(data_dir: Path, output_dir: Path) -> None:
    print("Loading data...")
    train_samples = load_jsonl(data_dir, "train")
    train_samples = train_samples + load_realnews(data_dir)
    dev_samples = load_jsonl(data_dir, "dev")
    test_samples = load_jsonl(data_dir, "test")

    # Build label mapping
    all_labels = sorted(set(s["label"] for s in train_samples))
    label2id = {lbl: i for i, lbl in enumerate(all_labels)}
    id2label = {i: lbl for lbl, i in label2id.items()}
    num_classes = len(all_labels)
    print(f"  {len(train_samples)} train, {len(dev_samples)} dev, {len(test_samples)} test")
    print(f"  {num_classes} classes: {all_labels}")

    # Load tokenizer and model
    print(f"Loading {MODEL_NAME}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME,
        num_labels=num_classes,
        id2label=id2label,
        label2id=label2id,
    )

    # Build datasets
    print("Tokenizing...")
    train_dataset = build_dataset(train_samples, tokenizer, label2id)
    dev_dataset = build_dataset(dev_samples, tokenizer, label2id)
    test_dataset = build_dataset(test_samples, tokenizer, label2id)

    # Training args
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_strategy="epoch",
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        learning_rate=LEARNING_RATE,
        num_train_epochs=NUM_EPOCHS,
        weight_decay=0.01,
        warmup_ratio=0.1,
        load_best_model_at_end=True,
        metric_for_best_model="eval_accuracy",
        greater_is_better=True,
        save_total_limit=2,
        fp16=torch.cuda.is_available(),
        report_to="none",
    )

    # Compute metrics
    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        import numpy as np
        preds = np.argmax(logits, axis=1)
        acc = (preds == labels).mean()
        return {"accuracy": acc}

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=dev_dataset,
        compute_metrics=compute_metrics,
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)],
    )

    # Train
    device = "GPU" if torch.cuda.is_available() else "CPU"
    print(f"\nFine-tuning {MODEL_NAME} on {device}...")
    trainer.train()

    # Evaluate
    print("\n--- Test Evaluation ---")
    test_metrics = trainer.evaluate(test_dataset)
    print(f"  Test accuracy: {test_metrics['eval_accuracy']:.4f}")
    print(f"  Random baseline: {1.0 / num_classes:.4f}")
    print(f"  Keyword rule baseline: ~0.65-0.70")

    # Save final model
    output_dir.mkdir(parents=True, exist_ok=True)
    model_path = output_dir / OUTPUT_MODEL_NAME
    model.save_pretrained(str(model_path))
    tokenizer.save_pretrained(str(model_path))

    # Save metadata
    meta = {"label2id": label2id, "id2label": id2label, "max_seq_len": MAX_SEQ_LEN}
    meta_path = output_dir / "model_meta.json"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Model size
    total_mb = sum(
        f.stat().st_size for f in model_path.rglob("*") if f.is_file()
    ) / (1024 * 1024)
    print(f"\nModel saved: {model_path} ({total_mb:.0f} MB)")
    print(f"Meta saved: {meta_path}")
    print("\nDone! Model is ready for inference via inference.py")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    data_dir = Path(__file__).resolve().parent / "training_data"
    output_dir = Path(__file__).resolve().parent / "models"
    train(data_dir, output_dir)
