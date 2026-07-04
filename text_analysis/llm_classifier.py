"""LLM-based news classification as an alternative to rule-based keyword matching.

Uses the same LLMConfig from data_management and the same client logic from
risk_warning/llm_enricher.py to perform zero-shot text classification.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

_CURRENT_DIR = Path(__file__).resolve().parent
_MGMT_DIR = _CURRENT_DIR.parent / "data_management"

for _d in (_MGMT_DIR, str(_CURRENT_DIR.parent / "risk_warning")):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

from config import LLM_CONFIG  # noqa: E402
from risk_rules import LLM_CLASSIFY_PROMPT_TEMPLATE, LLM_RISK_TYPE_PROMPT_TEMPLATE  # noqa: E402

logger = logging.getLogger("llm_classifier")

# Import the shared LLM call infrastructure
_has_llm_enricher = False
try:
    from llm_enricher import _call_llm, _parse_llm_json  # noqa: E402
    _has_llm_enricher = True
except ImportError:
    logger.warning("llm_enricher not available; LLM classification will fall back to rules.")


def _truncate_content(content: str, max_chars: int = 800) -> str:
    """Truncate content to fit within reasonable prompt size."""
    if len(content) <= max_chars:
        return content
    return content[:max_chars] + "..."


def classify_news_with_llm(title: str, content: str) -> dict | None:
    """Use LLM to classify a news article.

    Returns dict with keys: category, confidence, reasoning
    Returns None if LLM is unavailable or call fails.
    """
    if not LLM_CONFIG.enabled or not _has_llm_enricher:
        return None

    prompt = LLM_CLASSIFY_PROMPT_TEMPLATE.format(
        title=title,
        content=_truncate_content(content),
    )
    text = _call_llm(prompt, call_type="classify")
    parsed = _parse_llm_json(text)
    if parsed and parsed.get("category"):
        return {
            "category": parsed["category"],
            "confidence": float(parsed.get("confidence", 0.5)),
            "reasoning": parsed.get("reasoning", ""),
        }
    return None


def detect_risk_type_with_llm(title: str, content: str) -> dict | None:
    """Use LLM to detect risk type from news.

    Returns dict with keys: risk_type, confidence, matched_keywords, reasoning
    Returns None if LLM is unavailable or call fails.
    """
    if not LLM_CONFIG.enabled or not _has_llm_enricher:
        return None

    prompt = LLM_RISK_TYPE_PROMPT_TEMPLATE.format(
        title=title,
        content=_truncate_content(content),
    )
    text = _call_llm(prompt, call_type="risk_detect")
    parsed = _parse_llm_json(text)
    if parsed and parsed.get("risk_type"):
        return {
            "risk_type": parsed["risk_type"],
            "confidence": float(parsed.get("confidence", 0.5)),
            "matched_keywords": parsed.get("matched_keywords", []),
            "reasoning": parsed.get("reasoning", ""),
        }
    return None
