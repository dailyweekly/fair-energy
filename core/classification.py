"""검산 가능성 분류.

정책: docs/policies/02_calculation_gate_policy.md
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import CaseClassification, CompletenessScore, TariffInput


# 정책 02 §4의 필수 필드 목록.
REQUIRED_FIELDS_FOR_OFFICIAL = (
    "usage_kwh",
    "billing_start_date",
    "billing_end_date",
    "user_charged_amount",
)


# UI 노출용 한국어 라벨.
REQUIRED_FIELD_LABELS = {
    "usage_kwh": "사용량 (kWh)",
    "billing_start_date": "검침 시작일",
    "billing_end_date": "검침 종료일",
    "user_charged_amount": "사용자에게 청구된 금액",
    "contract_type": "계약종별",
    "allocation_formula": "세대별 배분 산식",
}


def _required_fields_present(tariff_input: TariffInput) -> bool:
    """공식 산식 비교에 필요한 필드가 모두 채워져 있는지."""
    return all(
        getattr(tariff_input, name) not in (None, "", 0)
        for name in REQUIRED_FIELDS_FOR_OFFICIAL
    )


def classify_case(
    score: CompletenessScore,
    tariff_input: TariffInput,
    is_fixed_fee: bool = False,
) -> CaseClassification:
    """검산 가능성을 5종 중 하나로 분류한다.

    정책 02 §6의 의사결정 트리를 그대로 구현한다.
    인위적으로 OFFICIAL_COMPARISON 비율을 올리려는 변경은 정책 위반이다.
    """
    if is_fixed_fee:
        return CaseClassification.FIXED_MANAGEMENT_FEE

    total = score.total_score

    if total < 40:
        return CaseClassification.NOT_CALCULABLE

    if total < 70:
        return CaseClassification.NEEDS_BASIS_REQUEST

    if total < 90:
        return CaseClassification.PRELIMINARY_CALCULATION

    # total >= 90: 필드/확인 게이트 통과 시에만 공식 비교.
    if _required_fields_present(tariff_input) and tariff_input.user_confirmed:
        return CaseClassification.OFFICIAL_COMPARISON

    return CaseClassification.PRELIMINARY_CALCULATION


# ---------------------------------------------------------------------------
# Phase 6 — 분류별 안내 디스크립터
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseDescriptor:
    """UI에서 사용하는 분류별 안내 데이터.

    `headline`·`explanation`·`next_actions`는 모두 정책 01의 금지어 필터를 통과한
    중립 표현으로 작성된다.
    """

    case: CaseClassification
    color_emoji: str
    headline: str
    explanation: str
    next_actions: tuple[str, ...]


CASE_DESCRIPTORS: dict[CaseClassification, CaseDescriptor] = {
    CaseClassification.NOT_CALCULABLE: CaseDescriptor(
        case=CaseClassification.NOT_CALCULABLE,
        color_emoji="🔴",
        headline="현재 자료만으로는 검산할 수 없습니다",
        explanation=(
            "자료 완결성 점수가 40점 미만입니다. "
            "검산을 위해서는 자료를 더 확보해야 합니다. "
            "본 단계에서는 계산이 수행되지 않으며, 필요한 자료 체크리스트만 제공됩니다."
        ),
        next_actions=(
            "부족한 자료를 추가 확보하세요",
            "문서 업로드 페이지로 돌아가 추가 업로드",
            "주거상담기관의 자료 확보 안내를 참고하세요",
        ),
    ),
    CaseClassification.NEEDS_BASIS_REQUEST: CaseDescriptor(
        case=CaseClassification.NEEDS_BASIS_REQUEST,
        color_emoji="🟠",
        headline="검산에 필요한 근거 자료가 부족합니다",
        explanation=(
            "자료 완결성 점수가 40~69점입니다. "
            "임대인에게 산식 공개를 요청하는 빈칸형 메시지 예시를 활용하실 수 있습니다. "
            "본 단계에서는 검산이 수행되지 않습니다."
        ),
        next_actions=(
            "자료요청 메시지 예시 확인 (Phase 9 이후)",
            "부족한 자료를 추가 업로드",
            "원고지서가 확보되면 분류가 자동으로 갱신됩니다",
        ),
    ),
    CaseClassification.PRELIMINARY_CALCULATION: CaseDescriptor(
        case=CaseClassification.PRELIMINARY_CALCULATION,
        color_emoji="🟡",
        headline="예비 검산 가능 — 일부 입력값 기반 추정",
        explanation=(
            "자료 완결성 점수가 70~89점이거나, 90점 이상이어도 필수 필드 일부가 "
            "확인되지 않았습니다. 누락 필드가 보강되면 결과가 달라질 수 있으며, "
            "본 결과는 공식 산식 비교가 아니므로 분쟁 근거로 사용할 수 없습니다."
        ),
        next_actions=(
            "예비 검산 결과 확인 (Phase 7 룰 엔진 활성화 후)",
            "Phase 4로 돌아가 누락된 필수 필드 확인",
            "추가 자료가 있으면 업로드",
        ),
    ),
    CaseClassification.OFFICIAL_COMPARISON: CaseDescriptor(
        case=CaseClassification.OFFICIAL_COMPARISON,
        color_emoji="🟢",
        headline="공식 산식 비교 가능",
        explanation=(
            "자료 완결성 점수가 90점 이상이고 필수 필드가 모두 사용자 확인되었습니다. "
            "한전 전기요금 공식 산식 기준 계산값과 사용자 청구액을 비교할 수 있습니다. "
            "본 결과는 사용자가 직접 확인한 자료를 기준으로 한 산식 차이 표시이며, "
            "법률 판단이나 분쟁 결과는 제공하지 않습니다."
        ),
        next_actions=(
            "공식 산식 비교 결과 확인 (Phase 7 룰 엔진 활성화 후)",
            "에너지 청구 자료 요약본 PDF 다운로드 (Phase 9 이후)",
            "결과를 직접 검토한 뒤 필요 시 주거상담기관에 상담",
        ),
    ),
    CaseClassification.FIXED_MANAGEMENT_FEE: CaseDescriptor(
        case=CaseClassification.FIXED_MANAGEMENT_FEE,
        color_emoji="🔵",
        headline="정액 관리비 케이스로 분류되었습니다",
        explanation=(
            "월세에 전기료가 포함된 정액 패키지 형태로 보입니다. "
            "이 케이스에서는 사용량 기반 계산이 의미가 없어 공식 산식 비교를 "
            "수행하지 않습니다. 국토부 관리비 세부표시 의무 정책 안내를 함께 제공합니다."
        ),
        next_actions=(
            "관리비 세부내역 표시 의무 정책 안내 확인",
            "임대차계약서의 관리비 항목을 다시 확인",
            "필요 시 주거상담기관 또는 분쟁조정위 안내",
        ),
    ),
}


def describe_case(case: CaseClassification) -> CaseDescriptor:
    """분류별 안내 디스크립터를 반환."""
    return CASE_DESCRIPTORS[case]


def reasons_blocking_official(
    score: CompletenessScore,
    tariff_input: TariffInput,
    *,
    is_fixed_fee: bool = False,
) -> list[str]:
    """OFFICIAL_COMPARISON 게이트를 막는 모든 사유를 반환.

    빈 리스트면 OFFICIAL이 활성화 가능한 상태.
    UI는 이 목록을 사용자에게 그대로 노출해 "무엇을 더 해야 하는지" 알려준다.
    """
    reasons: list[str] = []

    if is_fixed_fee:
        reasons.append(
            "정액 관리비 케이스로 분류되어 공식 산식 비교를 수행하지 않습니다."
        )
        return reasons

    if score.total_score < 90:
        reasons.append(
            f"자료 완결성 점수가 90점 미만입니다 (현재 {score.total_score}점)."
        )

    for key in REQUIRED_FIELDS_FOR_OFFICIAL:
        if getattr(tariff_input, key) in (None, "", 0):
            label = REQUIRED_FIELD_LABELS.get(key, key)
            reasons.append(f"필수 필드 누락: {label}")

    if not tariff_input.user_confirmed:
        reasons.append(
            "사용자가 모든 필수 필드를 직접 확인하지 않았습니다. "
            "Phase 4 추출값 확인 페이지로 돌아가 누락 필드를 확인해주세요."
        )

    return reasons
