"""LLM JSON 출력 스키마 검증.

LLM이 절대 규칙을 어겼거나 형식이 깨진 출력을 반환했을 때 즉시 차단한다.
정책 01 §6 — 모든 LLM 출력은 guardrails를 통과해야 한다.
"""

from __future__ import annotations

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, ValidationError, field_validator

from .guardrails import scan_forbidden


class ExtractionSchemaError(ValueError):
    """LLM 출력이 스키마/가드레일을 통과하지 못했을 때."""


# 정책 01의 금지 표현을 LLM이 출력해도 차단한다.
class LLMField(BaseModel):
    key: str
    label: str
    value: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    source_text: Optional[str] = None
    needs_user_confirmation: bool = True

    @field_validator("key")
    @classmethod
    def _key_must_be_snake_case(cls, v: str) -> str:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", v):
            raise ValueError(f"key must be snake_case: {v}")
        return v


class LLMPIIEntry(BaseModel):
    type: Literal[
        "name", "phone", "address", "bank_account",
        "resident_registration_number", "other",
    ]
    value_hint: Optional[str] = None


DOCUMENT_TYPES = {
    "lease_contract", "management_fee_notice", "electricity_bill",
    "meter_photo", "payment_proof", "landlord_notice", "unknown",
}


class LLMOutputDocument(BaseModel):
    """OCR LLM의 표준 출력."""

    document_type: str
    fields: list[LLMField]
    pii_detected: list[LLMPIIEntry] = Field(default_factory=list)
    extraction_summary: str = ""
    warnings: list[str] = Field(default_factory=list)

    @field_validator("document_type")
    @classmethod
    def _doc_type_in_enum(cls, v: str) -> str:
        if v not in DOCUMENT_TYPES:
            raise ValueError(f"document_type must be one of {sorted(DOCUMENT_TYPES)}")
        return v


# ---------------------------------------------------------------------------
# 파싱·검증
# ---------------------------------------------------------------------------


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE | re.MULTILINE)


def _strip_code_fence(raw: str) -> str:
    """LLM이 ```json ... ``` 코드펜스를 붙여 출력한 경우 제거."""
    return _FENCE_RE.sub("", raw).strip()


def _scan_summary_and_warnings(doc: LLMOutputDocument) -> list[str]:
    """summary/warnings에서 금지 표현이 검출되면 차단한다."""
    issues: list[str] = []
    for hit in scan_forbidden(doc.extraction_summary or ""):
        issues.append(f"extraction_summary: {hit.matched_text} ({hit.reason})")
    for idx, w in enumerate(doc.warnings):
        for hit in scan_forbidden(w):
            issues.append(f"warnings[{idx}]: {hit.matched_text} ({hit.reason})")
    return issues


def parse_llm_output(raw: str) -> LLMOutputDocument:
    """원시 LLM 응답 문자열을 LLMOutputDocument로 변환.

    실패 케이스:
      - JSON 파싱 실패
      - 스키마 검증 실패
      - summary/warnings에 금지 표현 포함
    """
    if not raw or not raw.strip():
        raise ExtractionSchemaError("LLM returned empty output.")

    cleaned = _strip_code_fence(raw)

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ExtractionSchemaError(f"Output is not valid JSON: {exc}") from exc

    try:
        doc = LLMOutputDocument.model_validate(parsed)
    except ValidationError as exc:
        raise ExtractionSchemaError(
            f"Output failed schema validation: {exc.errors()}"
        ) from exc

    issues = _scan_summary_and_warnings(doc)
    if issues:
        raise ExtractionSchemaError(
            "Forbidden terms detected in LLM output: " + " | ".join(issues)
        )

    return doc
