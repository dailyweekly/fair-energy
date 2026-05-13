"""LLM 클라이언트 팩토리·데모 클라이언트 테스트."""

from __future__ import annotations

import json

import pytest

from core import config, llm_client
from core.extraction_schema import parse_llm_output
from core.llm_client import DemoLLMClient, ExtractionRequest, get_llm_client
from core.models import DocumentType


def _demo_request(doc_type: str = "electricity_bill") -> ExtractionRequest:
    return ExtractionRequest(
        document_bytes=b"FAKE",
        document_type=doc_type,
        mime_type="image/png",
        filename="demo.png",
    )


# --- DemoLLMClient ---

def test_demo_client_returns_valid_json_for_each_doc_type() -> None:
    """모든 DocumentType에 대해 데모 응답이 스키마 검증을 통과해야 한다."""
    client = DemoLLMClient()
    for dt in DocumentType:
        request = _demo_request(dt.value)
        raw = client.extract(request)
        # JSON으로 파싱되고
        payload = json.loads(raw)
        assert payload["document_type"] in {dt.value, "unknown"}
        # 스키마 검증도 통과
        doc = parse_llm_output(raw)
        assert doc is not None


def test_demo_client_electricity_bill_has_usage() -> None:
    raw = DemoLLMClient().extract(_demo_request("electricity_bill"))
    payload = json.loads(raw)
    keys = {f["key"] for f in payload["fields"]}
    # 분류·룰 엔진이 필요로 하는 핵심 필드가 들어 있다.
    assert {"usage_kwh", "billing_start_date", "billing_end_date",
            "total_amount"}.issubset(keys)


def test_demo_client_unknown_falls_back() -> None:
    """fixtures에 없는 type은 unknown 응답으로 폴백."""
    client = DemoLLMClient()
    request = _demo_request("not_a_real_type")
    raw = client.extract(request)
    payload = json.loads(raw)
    assert payload["document_type"] == "unknown"


def test_demo_outputs_have_no_forbidden_terms() -> None:
    """데모 응답들이 가드레일을 모두 통과해야 한다."""
    client = DemoLLMClient()
    for dt in DocumentType:
        raw = client.extract(_demo_request(dt.value))
        # parse_llm_output가 통과하면 summary/warnings에 금지어 없음.
        parse_llm_output(raw)


# --- Factory ---

def _cfg(**env_overrides: str) -> config.AppConfig:
    env = {"APP_ENV": "test"}
    env.update(env_overrides)
    return config.load_config(env=env)


def test_factory_returns_demo_when_demo_mode_true() -> None:
    cfg = _cfg(DEMO_MODE="true", ENABLE_LLM_OCR="true",
               ANTHROPIC_API_KEY="sk-fake")
    client = get_llm_client(cfg)
    assert isinstance(client, DemoLLMClient)


def test_factory_returns_demo_when_ocr_disabled() -> None:
    cfg = _cfg(DEMO_MODE="false", ENABLE_LLM_OCR="false",
               ANTHROPIC_API_KEY="sk-fake")
    client = get_llm_client(cfg)
    assert isinstance(client, DemoLLMClient)


def test_factory_falls_back_when_no_key() -> None:
    cfg = _cfg(DEMO_MODE="false", ENABLE_LLM_OCR="true")
    # ANTHROPIC_API_KEY 비어 있음 → DemoLLMClient
    client = get_llm_client(cfg)
    assert isinstance(client, DemoLLMClient)
