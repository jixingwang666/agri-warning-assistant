"""LLM enrichment for agricultural risk warnings.

Uses OpenAI-compatible API (DeepSeek by default) to generate context-aware
reason and suggestion text, replacing static templates.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path

_CURRENT_DIR = Path(__file__).resolve().parent
_MGMT_DIR = _CURRENT_DIR.parent / "data_management"
if str(_MGMT_DIR) not in sys.path:
    sys.path.insert(0, str(_MGMT_DIR))

from config import LLM_CONFIG  # noqa: E402
from risk_rules import LLM_BATCH_PROMPT_TEMPLATE, LLM_ENRICH_PROMPT_TEMPLATE  # noqa: E402

logger = logging.getLogger("llm_enricher")

# ── LLM call log ────────────────────────────────────────────────────
_LOG_DIR = _CURRENT_DIR.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_LOG_FILE = _LOG_DIR / "llm_calls.log"


def _log_llm_call(call_type: str, prompt: str, response: str | None, error: str | None = None) -> None:
    """Append an LLM call record to the log file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "OK" if response else f"FAIL: {error or 'no response'}"
    with open(_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{'=' * 60}\n")
        f.write(f"[{timestamp}]  {call_type}  |  {status}\n")
        f.write(f"Model: {LLM_CONFIG.model}\n")
        f.write(f"--- PROMPT ---\n{prompt}\n")
        if response:
            f.write(f"--- RESPONSE ---\n{response}\n")
        f.write("\n")

# ── lazy client cache ──────────────────────────────────────────────
_client = None
_client_kind = None  # "openai" | "requests" | None


def _get_openai_client():
    """Try to import and return an OpenAI client."""
    try:
        from openai import OpenAI  # noqa: F811
    except ImportError:
        return None
    return OpenAI(api_key=LLM_CONFIG.api_key, base_url=LLM_CONFIG.base_url)


def _init_client() -> tuple:
    """Return (client, kind) where kind is 'openai' or 'requests'."""
    global _client, _client_kind
    if _client_kind is not None:
        return _client, _client_kind

    if not LLM_CONFIG.enabled:
        _client_kind = None
        return None, None
    if not LLM_CONFIG.api_key or "sk-your-" in LLM_CONFIG.api_key:
        logger.warning("LLM enabled but API key not configured; falling back to rules.")
        _client_kind = None
        return None, None

    client = _get_openai_client()
    if client is not None:
        _client = client
        _client_kind = "openai"
        return _client, _client_kind

    # fallback: raw requests
    try:
        import requests  # noqa: F811
    except ImportError:
        logger.warning("Neither openai SDK nor requests available; LLM disabled.")
        _client_kind = None
        return None, None

    _client_kind = "requests"
    return None, _client_kind


def _build_context(record: dict) -> str:
    """Build the structured input string for the LLM prompt."""
    price_signal = record.get("price_signal") or {}
    change_rate_pct = round(price_signal.get("change_rate", 0) * 100, 1)

    return LLM_ENRICH_PROMPT_TEMPLATE.format(
        title=record.get("title", ""),
        region=record.get("region", ""),
        product=record.get("product", "未识别"),
        risk_type=record.get("risk_type", "综合风险"),
        trigger_words=record.get("trigger_words", ""),
        risk_score=record.get("risk_score", 0),
        risk_level=record.get("risk_level", "低风险"),
        keyword_score=record.get("keyword_score", 0),
        price_score=record.get("price_score", 0),
        heat_score=record.get("heat_score", 0),
        region_score=record.get("region_score", 0),
        positive_adjustment=record.get("positive_adjustment", 0),
        price_change_rate=change_rate_pct,
    )


def _call_llm_openai(prompt: str, call_type: str = "enrich") -> str | None:
    """Call via openai SDK. Returns response text or None on failure."""
    client, _ = _init_client()
    try:
        response = client.chat.completions.create(
            model=LLM_CONFIG.model,
            messages=[
                {"role": "system", "content": "你是一个农业风险预警分析专家。请严格按格式输出JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=LLM_CONFIG.temperature,
            max_tokens=LLM_CONFIG.max_tokens,
            timeout=LLM_CONFIG.timeout,
        )
        text = response.choices[0].message.content
        _log_llm_call(call_type, prompt, text)
        return text
    except Exception as exc:
        logger.warning("OpenAI SDK call failed: %s", exc)
        _log_llm_call(call_type, prompt, None, str(exc))
        return None


def _call_llm_requests(prompt: str, call_type: str = "enrich") -> str | None:
    """Call via raw requests. Returns response text or None on failure."""
    import requests

    try:
        response = requests.post(
            f"{LLM_CONFIG.base_url}/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {LLM_CONFIG.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": LLM_CONFIG.model,
                "messages": [
                    {"role": "system", "content": "你是一个农业风险预警分析专家。请严格按格式输出JSON。"},
                    {"role": "user", "content": prompt},
                ],
                "temperature": LLM_CONFIG.temperature,
                "max_tokens": LLM_CONFIG.max_tokens,
            },
            timeout=LLM_CONFIG.timeout,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"]
        _log_llm_call(call_type, prompt, text)
        return text
    except Exception as exc:
        logger.warning("Requests LLM call failed: %s", exc)
        _log_llm_call(call_type, prompt, None, str(exc))
        return None


def _call_llm(prompt: str, call_type: str = "enrich") -> str | None:
    """Single LLM call with auto-detected client."""
    _, kind = _init_client()
    if kind is None:
        return None
    if kind == "openai":
        return _call_llm_openai(prompt, call_type)
    return _call_llm_requests(prompt, call_type)


def _parse_llm_json(text: str | None) -> dict | None:
    """Parse LLM JSON response. Returns dict or None on failure."""
    if not text:
        return None
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:]) if lines[0].startswith("```") else text
        if text.endswith("```"):
            text = text[:-3]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # try to extract first JSON object
        import re
        match = re.search(r"\{[^{}]*\}", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


# ── public API ─────────────────────────────────────────────────────

def enrich_warning_with_llm(record: dict) -> dict:
    """Enrich a single warning record with LLM-generated reason and suggestion.

    Returns the record with updated 'reason' and 'suggestion' fields.
    On any failure the record is returned unmodified (graceful fallback).
    """
    if not LLM_CONFIG.enabled:
        return record
    prompt = _build_context(record)
    text = _call_llm(prompt)
    parsed = _parse_llm_json(text)
    if parsed and parsed.get("reason"):
        record["reason"] = parsed["reason"]
    if parsed and parsed.get("suggestion"):
        record["suggestion"] = parsed["suggestion"]
    return record


def enrich_warnings_batch(warnings: list[dict], low_risk_threshold: float = 31.0) -> list[dict]:
    """Batch-enrich warnings, skipping low-risk items for cost savings.

    Low-risk items (risk_score < low_risk_threshold) keep their rule-based text.
    The remaining items are sent in batches of 5 to reduce API calls.
    """
    if not LLM_CONFIG.enabled:
        return warnings

    high_risk = [w for w in warnings if w.get("risk_score", 0) >= low_risk_threshold]
    if not high_risk:
        return warnings

    batch_size = 5
    for i in range(0, len(high_risk), batch_size):
        batch = high_risk[i: i + batch_size]

        if len(batch) == 1:
            # single-item: use single prompt for better quality
            enriched = enrich_warning_with_llm(batch[0])
            batch[0] = enriched
            continue

        # multi-item: build batch prompt
        items_json = json.dumps(
            [
                {
                    "title": r.get("title", ""),
                    "region": r.get("region", ""),
                    "product": r.get("product", "未识别"),
                    "risk_type": r.get("risk_type", "综合风险"),
                    "trigger_words": r.get("trigger_words", ""),
                    "risk_score": r.get("risk_score", 0),
                    "risk_level": r.get("risk_level", "低风险"),
                    "keyword_score": r.get("keyword_score", 0),
                    "price_score": r.get("price_score", 0),
                    "heat_score": r.get("heat_score", 0),
                    "region_score": r.get("region_score", 0),
                    "positive_adjustment": r.get("positive_adjustment", 0),
                }
                for r in batch
            ],
            ensure_ascii=False,
            indent=2,
        )
        prompt = LLM_BATCH_PROMPT_TEMPLATE.format(warnings_json=items_json)
        text = _call_llm(prompt)
        if not text:
            continue

        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:]) if lines[0].startswith("```") else text
            if text.endswith("```"):
                text = text[:-3]

        try:
            results = json.loads(text)
            if isinstance(results, list):
                for j, result in enumerate(results):
                    if j < len(batch) and isinstance(result, dict):
                        if result.get("reason"):
                            batch[j]["reason"] = result["reason"]
                        if result.get("suggestion"):
                            batch[j]["suggestion"] = result["suggestion"]
        except json.JSONDecodeError:
            logger.warning("Failed to parse batch LLM response; keeping rule output.")

    return warnings
