"""Build a text classification dataset from AgriCHN-2023 BIO annotations.

AgriCHN-2023 format (character-level BIO):
    旱\tB-农业技术
    地\tI-农业技术
    ，\tO
    ...(blank line separates sentences)...

This script converts sentences into a 6-class classification dataset matching
the project's existing category system.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# ── Mapping: AgriCHN entity types → project categories ─────────────
ENTITY_TO_CATEGORY = {
    "病虫草害": "病虫害",
    "疾病": "病虫害",
    "气象现象": "气象灾害",
    "温度": "气象灾害",
    "水文现象": "气象灾害",
    "农业技术": "农业科技",
    "农业设备": "农业科技",
    "农业设施": "农业科技",
    "农药": "病虫害",
    "肥料": "农业科技",
    "组织结构": "农业政策",
    "经济作物类": "农产品价格",
    "粮食作物类": "农产品价格",
    "蔬菜类": "市场供需",
    "水果类": "市场供需",
    "畜禽类": "市场供需",
    "水产类": "市场供需",
    "饲料作物类": "市场供需",
    "产品类": "市场供需",
    "营养物质": "农业科技",
    "土壤类型": "农业科技",
    "土壤墒情": "农业科技",
    "其他生物": "病虫害",
}

# All project categories we want to classify into
ALL_CATEGORIES = ["农业政策", "农产品价格", "病虫害", "气象灾害", "市场供需", "农业科技"]

# Entities that don't indicate a specific agricultural category
NON_CLASSIFYING_ENTITIES = {"地名", "时间", "人名", "水域"}


def parse_bio_file(path: str | Path) -> list[dict]:
    """Parse a BIO-format file into a list of sentences with entity annotations.

    Returns list of dicts: {"text": str, "entities": set[str]}
    """
    content = Path(path).read_text(encoding="utf-8")
    blocks = content.strip().split("\n\n")

    sentences = []
    for block in blocks:
        lines = block.strip().split("\n")
        chars = []
        entities = set()
        for line in lines:
            if "\t" not in line:
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            char = parts[0]
            tag = parts[1].strip()
            chars.append(char)
            if tag != "O":
                # Extract entity type (strip B- / I- prefix)
                etype = tag[2:] if (tag.startswith("B-") or tag.startswith("I-")) else tag
                entities.add(etype)
        if chars:
            text = "".join(chars)
            sentences.append({"text": text, "entities": entities})

    return sentences


def _get_categories(entities: set[str]) -> set[str]:
    """Map a set of AgriCHN entity types to project categories."""
    categories = set()
    for entity in entities:
        if entity in NON_CLASSIFYING_ENTITIES:
            continue
        cat = ENTITY_TO_CATEGORY.get(entity)
        if cat:
            categories.add(cat)
    # If no category matched, treat as "其他" (will be dropped in multi-class version)
    # For multi-label, we keep only if at least one category is present
    return categories if categories else {"其他"}


def build_classification_dataset(
    dataset_dir: str | Path,
    output_dir: str | Path | None = None,
) -> dict:
    """Build train/dev/test classification datasets from AgriCHN BIO files.

    Args:
        dataset_dir: Path to AgriCHN-2023/dataset/ directory (contains train.txt, dev.txt, test.txt)
        output_dir: If provided, save JSON files here.

    Returns:
        dict with keys "train", "dev", "test", each a list of {"text": str, "labels": [str]}
    """
    dataset_dir = Path(dataset_dir)
    result = {}

    for split in ("train", "dev", "test"):
        bio_file = dataset_dir / f"{split}.txt"
        if not bio_file.exists():
            print(f"  [skip] {bio_file} not found")
            continue

        raw = parse_bio_file(bio_file)
        samples = []
        for item in raw:
            cats = _get_categories(item["entities"])
            # Keep only samples with at least one valid agricultural category
            if "其他" not in cats and cats:
                samples.append({
                    "text": item["text"],
                    "labels": sorted(cats),
                })

        # Drop "其他" samples to keep only labeled data
        result[split] = samples
        label_counts = {}
        for s in samples:
            for lbl in s["labels"]:
                label_counts[lbl] = label_counts.get(lbl, 0) + 1
        print(f"  {split}: {len(samples)} samples")
        for lbl, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
            print(f"    {lbl}: {cnt}")

    # Save to disk if output_dir provided
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for split, samples in result.items():
            path = output_dir / f"classification_{split}.json"
            path.write_text(
                json.dumps(samples, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print(f"\n  Saved to {output_dir}/classification_*.json")

    return result


def build_single_label_dataset(
    dataset_dir: str | Path,
    output_dir: str | Path | None = None,
) -> dict:
    """Same as build_classification_dataset but creates single-label samples.

    Multi-label samples are duplicated: one copy per label.
    This is simpler for TextCNN training.
    """
    multi = build_classification_dataset(dataset_dir, output_dir=None)
    result = {}

    for split, samples in multi.items():
        single = []
        for sample in samples:
            for label in sample["labels"]:
                single.append({"text": sample["text"], "label": label})
        result[split] = single
        label_counts = {}
        for s in single:
            label_counts[s["label"]] = label_counts.get(s["label"], 0) + 1
        print(f"  {split} (single-label): {len(single)} samples")
        for lbl, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
            print(f"    {lbl}: {cnt}")

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for split, samples in result.items():
            path = output_dir / f"classification_{split}_single.json"
            path.write_text(
                json.dumps(samples, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    return result


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    # Default: clone AgriCHN-2023 to a known location if not present
    dataset_path = Path(__file__).resolve().parent / "agrichn_dataset"
    if not dataset_path.exists():
        print("AgriCHN-2023 dataset not found. Clone it first:")
        print("  git clone https://github.com/SleeperZLX/AgriCHN-2023.git")
        print(f"  Then place the 'dataset/' folder at: {dataset_path}/dataset/")
        sys.exit(1)

    dataset_dir = dataset_path / "dataset"
    output = Path(__file__).resolve().parent / "training_data"
    print("Building multi-label dataset...")
    build_classification_dataset(dataset_dir, output)
    print("\nBuilding single-label dataset...")
    build_single_label_dataset(dataset_dir, output)
