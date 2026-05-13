"""공정에너지 핵심 데이터 모델.

신청서 v5의 Energy Bill Completeness Score, 4분류, TariffInput 정의를 반영한다.
계산 게이트는 docs/policies/02_calculation_gate_policy.md를 참조.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    LEASE_CONTRACT = "lease_contract"
    MANAGEMENT_FEE_NOTICE = "management_fee_notice"
    ELECTRICITY_BILL = "electricity_bill"
    METER_PHOTO = "meter_photo"
    PAYMENT_PROOF = "payment_proof"
    LANDLORD_NOTICE = "landlord_notice"
    UNKNOWN = "unknown"


class FieldConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExtractedField(BaseModel):
    """OCR/LLM이 추출한 단일 필드.

    `user_confirmed=False`인 필드는 계산에 사용되지 않는다.
    """

    key: str
    label: str
    value: Optional[str] = None
    unit: Optional[str] = None
    confidence: float = Field(ge=0, le=1)
    source_document_id: str
    source_text: Optional[str] = None
    needs_user_confirmation: bool = True
    user_confirmed: bool = False


class ExtractedDocument(BaseModel):
    document_id: str
    document_type: DocumentType
    original_filename: str
    extracted_fields: list[ExtractedField]
    extraction_summary: str
    warnings: list[str] = Field(default_factory=list)


class CompletenessScore(BaseModel):
    """Energy Bill Completeness Score (100점 만점).

    배점은 docs/policies/02_calculation_gate_policy.md §2와 동일하다.
    """

    lease_contract: int = 0              # 15
    itemized_fee_notice: int = 0         # 15
    meter_photo_with_date: int = 0       # 15
    original_electricity_bill: int = 0   # 25
    allocation_formula: int = 0          # 20
    payment_proof: int = 0               # 10
    total_score: int = 0
    missing_items: list[str] = Field(default_factory=list)
    available_actions: list[str] = Field(default_factory=list)


class CaseClassification(str, Enum):
    """검산 가능성 4분류 + 정액 관리비."""

    NOT_CALCULABLE = "검산 불가"
    NEEDS_BASIS_REQUEST = "근거 요청 필요"
    PRELIMINARY_CALCULATION = "예비 검산 가능"
    OFFICIAL_COMPARISON = "공식 산식 비교 가능"
    FIXED_MANAGEMENT_FEE = "정액 관리비 케이스"


class TariffInput(BaseModel):
    """전기요금 룰 엔진 입력.

    `user_confirmed=True`가 아니면 룰 엔진은 계산을 거부한다.
    """

    usage_kwh: Optional[float] = None
    billing_start_date: Optional[str] = None
    billing_end_date: Optional[str] = None
    contract_type: Optional[str] = None
    household_count: Optional[int] = None
    user_charged_amount: Optional[int] = None
    allocation_formula: Optional[str] = None
    user_confirmed: bool = False


class CalculationResult(BaseModel):
    can_calculate: bool
    calculated_amount: Optional[int] = None
    user_charged_amount: Optional[int] = None
    difference_amount: Optional[int] = None
    difference_rate: Optional[float] = None
    formula_breakdown: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    neutral_label: str = ""


class SafetyLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"  # 2026-05-13 외부 자문 — 메시지 자체 숨김 + 상담기관 우선


class SafetyCheckResponse(BaseModel):
    """사용자 안전 체크 응답 (docs/policies/05_user_safety_policy.md §2)."""

    contract_renewal_or_eviction: bool = False     # 1
    deposit_return_concern: bool = False           # 2
    landlord_threat_or_pressure: bool = False      # 3 (HIGH 직접 신호)
    no_alternative_housing: bool = False           # 4
    foreign_status_or_employer_housing: bool = False  # 5
    feels_unsafe_to_request: bool = False          # 6 (HIGH 직접 신호)


class ConsentRecord(BaseModel):
    user_id: str
    consent_service: bool
    consent_personal_info: bool
    consent_ai_processing: bool
    consent_storage_months: int
    consent_ngo_share: bool = False
    consent_external_submission: bool = False
    created_at: datetime
