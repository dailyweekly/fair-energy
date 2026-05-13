"""LLM 출력 JSON 스키마 검증 테스트.

정책 01 §6과 03 §8 — LLM이 금지 표현을 출력해도 차단되어야 한다.
"""

from __future__ import annotations

import json

import pytest

from core.extraction_schema import (
    ExtractionSchemaError,
    LLMOutputDocument,
    parse_llm_output,
)


# --- valid 케이스 ---

VALID_PAYLOAD = {
    "document_type": "electricity_bill",
    "fields": [
        {
            "key": "usage_kwh",
            "label": "사용량",
            "value": "245",
            "unit": "kWh",
            "confidence": 0.9,
            "source_text": "당월 사용량 245 kWh",
            "needs_user_confirmation": True,
        }
    ],
    "pii_detected": [{"type": "address", "value_hint": "서울시 관악구 ***"}],
    "extraction_summary": "주택용 저압 1개월 청구 자료를 추출했습니다.",
    "warnings": ["검침기간을 확인해주세요."],
}


def test_valid_payload_parses() -> None:
    raw = json.dumps(VALID_PAYLOAD, ensure_ascii=False)
    doc = parse_llm_output(raw)
    assert isinstance(doc, LLMOutputDocument)
    assert doc.document_type == "electricity_bill"
    assert len(doc.fields) == 1
    assert doc.fields[0].confidence == 0.9


def test_code_fence_is_stripped() -> None:
    raw = "```json\n" + json.dumps(VALID_PAYLOAD, ensure_ascii=False) + "\n```"
    doc = parse_llm_output(raw)
    assert doc.document_type == "electricity_bill"


def test_empty_string_rejected() -> None:
    with pytest.raises(ExtractionSchemaError):
        parse_llm_output("")


def test_non_json_rejected() -> None:
    with pytest.raises(ExtractionSchemaError):
        parse_llm_output("문서를 분석한 결과 위반이 의심됩니다.")


def test_unknown_document_type_rejected() -> None:
    payload = dict(VALID_PAYLOAD, document_type="random_value")
    with pytest.raises(ExtractionSchemaError):
        parse_llm_output(json.dumps(payload))


def test_confidence_out_of_range_rejected() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["fields"] = [dict(payload["fields"][0], confidence=1.5)]
    with pytest.raises(ExtractionSchemaError):
        parse_llm_output(json.dumps(payload, ensure_ascii=False))


def test_non_snake_case_key_rejected() -> None:
    payload = dict(VALID_PAYLOAD)
    payload["fields"] = [dict(payload["fields"][0], key="UsageKwh")]
    with pytest.raises(ExtractionSchemaError):
        parse_llm_output(json.dumps(payload, ensure_ascii=False))


# --- 금지 표현 차단 ---

def test_forbidden_term_in_summary_rejected() -> None:
    payload = dict(VALID_PAYLOAD,
                   extraction_summary="이 청구는 부당청구로 보입니다.")
    with pytest.raises(ExtractionSchemaError) as exc:
        parse_llm_output(json.dumps(payload, ensure_ascii=False))
    assert "Forbidden terms" in str(exc.value)


def test_forbidden_term_in_warnings_rejected() -> None:
    payload = dict(VALID_PAYLOAD,
                   warnings=["임대인을 신고하세요.", "검침일을 확인하세요."])
    with pytest.raises(ExtractionSchemaError):
        parse_llm_output(json.dumps(payload, ensure_ascii=False))


def test_safe_warnings_pass() -> None:
    payload = dict(VALID_PAYLOAD,
                   warnings=["검침일이 누락되어 있습니다. 사용자가 직접 확인해주세요."])
    parse_llm_output(json.dumps(payload, ensure_ascii=False))


# --- PII 항목 ---

def test_pii_with_invalid_type_rejected() -> None:
    payload = dict(VALID_PAYLOAD,
                   pii_detected=[{"type": "credit_card", "value_hint": "****"}])
    with pytest.raises(ExtractionSchemaError):
        parse_llm_output(json.dumps(payload, ensure_ascii=False))


def test_pii_can_be_empty() -> None:
    payload = dict(VALID_PAYLOAD, pii_detected=[])
    parse_llm_output(json.dumps(payload, ensure_ascii=False))


# --- 빈 fields 허용 (unknown 문서) ---

def test_unknown_document_with_empty_fields() -> None:
    payload = {
        "document_type": "unknown",
        "fields": [],
        "pii_detected": [],
        "extraction_summary": "문서 유형을 식별하지 못했습니다.",
        "warnings": ["사용자에게 문서 유형 선택을 요청하세요."],
    }
    doc = parse_llm_output(json.dumps(payload, ensure_ascii=False))
    assert doc.document_type == "unknown"
    assert doc.fields == []
