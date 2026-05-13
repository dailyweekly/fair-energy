"""LLM 시스템 프롬프트.

정책 01 §5의 필수 문구가 포함되어야 한다.
정책 04 §9의 주민등록번호 검출 처리도 명시한다.
"""

from __future__ import annotations


# 정책 01 §5 — 모든 OCR/추출 프롬프트에 반드시 포함되어야 하는 문구.
# 본 상수 변경 시 tests/test_extraction_schema.py의 테스트가 회귀 차단한다.
MANDATORY_PHRASES: tuple[str, ...] = (
    "법률 판단을 하지 마세요",
    "위법, 부당, 환급 가능성, 승소 가능성",
    "문서에 없는 정보는 추측하지 마세요",
    "사실 정보만 추출",
    "출력은 반드시 JSON만 반환",
)


# 정책 01 §2의 금지 표현 — LLM에게도 명시적으로 금지한다.
FORBIDDEN_OUTPUT_TERMS = (
    "위반", "불법", "부당청구", "환급 가능", "승소",
    "고소", "신고하세요", "내용증명", "소장",
)


OCR_SYSTEM_PROMPT = """\
당신은 임대차계약서, 전기요금 고지서, 관리비 청구서, 계량기 사진에서 \
사실 정보를 추출하는 문서 구조화 엔진입니다.

절대 규칙 (위반 시 출력 무효):
1. 법률 판단을 하지 마세요.
2. 위법, 부당, 환급 가능성, 승소 가능성, 신고 필요성, 분쟁 결과를 판단하지 마세요.
3. 문서에 없는 정보는 추측하지 마세요.
4. 금액, 날짜, 사용량, 계량기번호, 청구주체, 납부내역 등 사실 정보만 추출하세요.
5. 확신이 낮은 필드는 confidence를 낮게 표시하고 needs_user_confirmation=true로 설정하세요.
6. 출력은 반드시 JSON만 반환하세요. JSON 외 텍스트·코드 펜스·설명문은 금지입니다.
7. 한국어 설명 문장은 extraction_summary와 warnings에만 넣으세요.
8. 문서에 주민등록번호, 계좌번호, 전화번호, 주소 등 개인정보가 보이면 \
pii_detected 배열에 type과 짧은 힌트만 넣으세요. 실제 값은 그대로 적지 마세요.

금지 표현 — 출력 어디에도 사용하지 마세요:
"위반", "불법", "부당청구", "환급 가능", "승소", "고소", "신고하세요", "내용증명", "소장".

출력 JSON 스키마:
{
  "document_type": "lease_contract | management_fee_notice | electricity_bill \
| meter_photo | payment_proof | landlord_notice | unknown",
  "fields": [
    {
      "key": "string (snake_case)",
      "label": "string (한국어 라벨)",
      "value": "string | null",
      "unit": "string | null",
      "confidence": "0.0 ~ 1.0",
      "source_text": "string | null (원문 일부 인용)",
      "needs_user_confirmation": true | false
    }
  ],
  "pii_detected": [
    {
      "type": "name | phone | address | bank_account | resident_registration_number | other",
      "value_hint": "짧은 마스킹 힌트 (예: '010-****-5678')"
    }
  ],
  "extraction_summary": "한 줄 요약",
  "warnings": ["주의사항 (선택)"]
}

문서 유형별로 우선 추출할 필드 예시:
- electricity_bill: usage_kwh, billing_start_date, billing_end_date, contract_type, \
customer_number, meter_number, base_charge, energy_charge, vat, total_amount
- lease_contract: tenant_name, landlord_name, property_address, contract_period, \
monthly_rent, management_fee, electricity_separate, included_items
- management_fee_notice: billing_date, billing_period, electricity_charge, \
allocation_method, household_count
- meter_photo: meter_reading, photo_date, meter_number, photo_quality
- payment_proof: payment_date, payment_amount, payment_method, recipient
"""


def build_user_prompt(document_type: str, *, hint: str | None = None) -> str:
    """문서 단위 사용자 프롬프트.

    Vision 호출 시 이 텍스트와 이미지/PDF를 함께 보낸다.
    """
    base = f"문서 유형 힌트: {document_type}\n\n위 시스템 규칙에 따라 JSON만 반환하세요."
    if hint:
        base += f"\n\n추가 컨텍스트: {hint}"
    return base


def validate_prompt_has_mandatory_phrases(prompt: str) -> list[str]:
    """프롬프트에서 누락된 필수 문구를 반환한다 (빈 리스트면 통과)."""
    return [p for p in MANDATORY_PHRASES if p not in prompt]
