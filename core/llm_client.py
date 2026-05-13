"""LLM 클라이언트 — provider abstraction + 데모 폴백.

`DEMO_MODE=true` 또는 API 키가 없으면 `DemoLLMClient`를 반환한다.
실제 API 호출은 `AnthropicLLMClient`(Claude Vision)가 담당한다.

정책 03 §1 — LLM은 문서 구조화/필드 추출만 수행한다. 요금 계산은 절대 호출 금지.
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from .config import AppConfig
from .prompts import OCR_SYSTEM_PROMPT, build_user_prompt


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionRequest:
    document_bytes: bytes
    document_type: str   # DocumentType.value
    mime_type: str       # "image/png" | "image/jpeg" | "application/pdf"
    filename: str
    hint: Optional[str] = None


@runtime_checkable
class LLMClient(Protocol):
    """모든 LLM 백엔드가 구현해야 하는 인터페이스."""

    name: str

    def extract(self, request: ExtractionRequest) -> str:
        """원시 JSON 문자열을 반환한다. 검증은 extraction_schema에서."""
        ...


# ---------------------------------------------------------------------------
# Demo client — API 키 없이도 앱이 동작하도록 fixture 데이터를 반환
# ---------------------------------------------------------------------------


DEMO_FIXTURES: dict[str, dict] = {
    "electricity_bill": {
        "document_type": "electricity_bill",
        "fields": [
            {"key": "usage_kwh", "label": "사용량", "value": "245",
             "unit": "kWh", "confidence": 0.93,
             "source_text": "당월 사용량 245 kWh",
             "needs_user_confirmation": True},
            {"key": "billing_start_date", "label": "검침 시작일",
             "value": "2026-04-01", "unit": None, "confidence": 0.91,
             "source_text": "검침기간 2026-04-01 ~ 2026-04-30",
             "needs_user_confirmation": True},
            {"key": "billing_end_date", "label": "검침 종료일",
             "value": "2026-04-30", "unit": None, "confidence": 0.91,
             "source_text": "검침기간 2026-04-01 ~ 2026-04-30",
             "needs_user_confirmation": True},
            {"key": "contract_type", "label": "계약종별",
             "value": "주택용 저압", "unit": None, "confidence": 0.88,
             "source_text": "주택용(저압)",
             "needs_user_confirmation": True},
            {"key": "total_amount", "label": "청구액",
             "value": "38000", "unit": "KRW", "confidence": 0.95,
             "source_text": "당월 청구금액 38,000원",
             "needs_user_confirmation": True},
        ],
        "pii_detected": [
            {"type": "address", "value_hint": "서울시 관악구 ***"},
        ],
        "extraction_summary": "주택용 저압 1개월 청구 자료를 추출했습니다.",
        "warnings": ["검침기간 일자가 사용자 청구 기간과 일치하는지 확인해주세요."],
    },
    "lease_contract": {
        "document_type": "lease_contract",
        "fields": [
            {"key": "monthly_rent", "label": "월세", "value": "350000",
             "unit": "KRW", "confidence": 0.94,
             "source_text": "월차임 350,000원",
             "needs_user_confirmation": True},
            {"key": "management_fee", "label": "관리비",
             "value": "50000", "unit": "KRW", "confidence": 0.88,
             "source_text": "관리비 50,000원 (전기·수도 포함)",
             "needs_user_confirmation": True},
            {"key": "electricity_separate", "label": "전기료 별도 여부",
             "value": "포함", "unit": None, "confidence": 0.78,
             "source_text": "관리비에 전기료가 포함",
             "needs_user_confirmation": True},
        ],
        "pii_detected": [
            {"type": "name", "value_hint": "홍**"},
            {"type": "address", "value_hint": "서울시 관악구 ***"},
        ],
        "extraction_summary": "관리비 정액 포함형 임대차계약서를 추출했습니다.",
        "warnings": ["관리비 포함 항목과 전기료 분리 여부를 사용자가 직접 확인해주세요."],
    },
    "meter_photo": {
        "document_type": "meter_photo",
        "fields": [
            {"key": "meter_reading", "label": "계량기 숫자",
             "value": "08245", "unit": "kWh", "confidence": 0.72,
             "source_text": None,
             "needs_user_confirmation": True},
            {"key": "photo_date", "label": "촬영일",
             "value": "2026-04-30", "unit": None, "confidence": 0.65,
             "source_text": "사진 메타데이터 추정",
             "needs_user_confirmation": True},
            {"key": "photo_quality", "label": "사진 품질",
             "value": "medium", "unit": None, "confidence": 0.80,
             "source_text": None,
             "needs_user_confirmation": True},
        ],
        "pii_detected": [],
        "extraction_summary": "계량기 사진 1장에서 숫자와 촬영일 추정값을 추출했습니다.",
        "warnings": ["계량기 숫자 신뢰도가 낮습니다. 사용자가 직접 확인해주세요."],
    },
    "management_fee_notice": {
        "document_type": "management_fee_notice",
        "fields": [
            {"key": "billing_period", "label": "청구 기간",
             "value": "2026-04", "unit": None, "confidence": 0.92,
             "source_text": "2026년 4월분",
             "needs_user_confirmation": True},
            {"key": "electricity_charge", "label": "전기료 항목",
             "value": "42000", "unit": "KRW", "confidence": 0.85,
             "source_text": "전기료 42,000원",
             "needs_user_confirmation": True},
            {"key": "allocation_method", "label": "배분 산식",
             "value": "미기재", "unit": None, "confidence": 0.40,
             "source_text": None,
             "needs_user_confirmation": True},
        ],
        "pii_detected": [],
        "extraction_summary": "관리비 청구 내역을 추출했습니다.",
        "warnings": [
            "세대별 배분 산식이 청구서에 기재되어 있지 않습니다.",
            "임대인에게 산식 공개 요청 메시지 예시를 검토해보세요.",
        ],
    },
    "payment_proof": {
        "document_type": "payment_proof",
        "fields": [
            {"key": "payment_date", "label": "납부일",
             "value": "2026-05-05", "unit": None, "confidence": 0.96,
             "source_text": "2026.05.05",
             "needs_user_confirmation": True},
            {"key": "payment_amount", "label": "납부 금액",
             "value": "42000", "unit": "KRW", "confidence": 0.97,
             "source_text": "42,000원 이체",
             "needs_user_confirmation": True},
        ],
        "pii_detected": [
            {"type": "bank_account", "value_hint": "110-***-******"},
        ],
        "extraction_summary": "계좌이체 납부 내역을 추출했습니다.",
        "warnings": [],
    },
    "landlord_notice": {
        "document_type": "landlord_notice",
        "fields": [],
        "pii_detected": [],
        "extraction_summary": "임대인 공지문에서 추출 가능한 사실 필드가 없습니다.",
        "warnings": ["문서가 비표준 양식입니다. 사용자가 필드를 직접 입력해주세요."],
    },
    "unknown": {
        "document_type": "unknown",
        "fields": [],
        "pii_detected": [],
        "extraction_summary": "문서 유형을 식별하지 못했습니다.",
        "warnings": ["사용자에게 문서 유형 선택을 요청하세요."],
    },
}


class DemoLLMClient:
    """API 키 없이도 동작하는 결정론적 fixture 클라이언트.

    문서 유형별 고정 응답을 반환한다 — 분류·룰 엔진의 회귀 테스트에 사용된다.
    """

    name = "demo"

    def extract(self, request: ExtractionRequest) -> str:
        fixture = DEMO_FIXTURES.get(request.document_type, DEMO_FIXTURES["unknown"])
        return json.dumps(fixture, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Anthropic client — 실 API 호출
# ---------------------------------------------------------------------------


class AnthropicLLMClient:
    """Claude Vision 호출 클라이언트.

    실제 베타에서는 모델·max_tokens·temperature를 환경에 맞게 조정한다.
    본 모듈은 호출만 책임지고, JSON 검증은 extraction_schema에서 수행한다.
    """

    name = "anthropic"

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-6") -> None:
        try:
            import anthropic  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "anthropic SDK is not installed. Run: pip install anthropic"
            ) from exc
        self._api_key = api_key
        self._model = model

    def extract(self, request: ExtractionRequest) -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=self._api_key)

        content: list[dict] = []
        if request.mime_type.startswith("image/"):
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": request.mime_type,
                    "data": base64.standard_b64encode(request.document_bytes).decode(),
                },
            })
        elif request.mime_type == "application/pdf":
            content.append({
                "type": "document",
                "source": {
                    "type": "base64",
                    "media_type": "application/pdf",
                    "data": base64.standard_b64encode(request.document_bytes).decode(),
                },
            })
        else:
            # 텍스트만 첨부 — 호출자가 미리 추출한 텍스트를 보낼 수 있다.
            content.append({"type": "text",
                            "text": request.document_bytes.decode("utf-8", "replace")})

        content.append({"type": "text",
                        "text": build_user_prompt(request.document_type,
                                                  hint=request.hint)})

        response = client.messages.create(
            model=self._model,
            max_tokens=2048,
            system=OCR_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )

        # Anthropic 응답 텍스트 블록만 추출.
        texts = [block.text for block in response.content
                 if getattr(block, "type", None) == "text"]
        return "\n".join(texts) if texts else ""


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_llm_client(config: AppConfig) -> LLMClient:
    """설정에 맞는 LLM 클라이언트를 반환한다.

    우선순위:
      1. DEMO_MODE=true 또는 ENABLE_LLM_OCR=false → DemoLLMClient
      2. ANTHROPIC_API_KEY 존재 → AnthropicLLMClient
      3. 그 외 → DemoLLMClient (실패 안전 폴백)
    """
    if config.demo_mode or not config.enable_llm_ocr:
        logger.info("Using DemoLLMClient (demo_mode=%s, llm_ocr=%s)",
                    config.demo_mode, config.enable_llm_ocr)
        return DemoLLMClient()

    if config.anthropic_api_key:
        return AnthropicLLMClient(config.anthropic_api_key)

    logger.warning("No LLM API key — falling back to DemoLLMClient.")
    return DemoLLMClient()
