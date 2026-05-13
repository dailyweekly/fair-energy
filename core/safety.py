"""사용자 안전 체크 로직.

정책: docs/policies/05_user_safety_policy.md
"""

from __future__ import annotations

from .models import SafetyCheckResponse, SafetyLevel


# 정책 01_output_language_policy §4의 기본 면책 문구.
DEFAULT_DISCLAIMER = (
    "본 서비스는 법률 자문, 법률 의견, 소송 전략, 환급 가능성 판단을 제공하지 않습니다. "
    "본 결과는 사용자가 업로드하고 직접 확인한 자료를 바탕으로 한 요금 산식 검토 보조 자료입니다. "
    "임대인의 위법성 여부, 환급 가능성, 분쟁 결과는 판단하지 않습니다. "
    "분쟁이 예상되거나 계약갱신, 보증금 반환, 퇴거 압박, 신변 위험이 있는 경우 "
    "주거상담기관 또는 변호사 등 전문가와 먼저 상담하세요."
)


# 정책 05 §4의 HIGH 등급 안내 문구.
HIGH_RISK_DISCLAIMER = (
    "안전 확인 필요\n\n"
    "현재 상황에서는 임대인에게 직접 메시지를 보내기 전에 "
    "주거상담기관 또는 법률구조기관과 먼저 상담하는 것이 안전할 수 있습니다.\n\n"
    "공정에너지는 자료 정리와 검산 가능성 확인만 도와드리며, 분쟁 행동을 권유하지 않습니다.\n\n"
    "도움 받을 수 있는 곳:\n"
    "  • 주거상담기관 (지자체 주거복지센터)\n"
    "  • 법률구조공단 국번없이 132\n"
    "  • 외국인 노동자 지원기관\n"
    "  • 화우 ESG센터 공익 연계"
)

# VERY_HIGH 등급 — 메시지 예시 자체를 숨기고 상담기관만 노출 (2026-05-13).
VERY_HIGH_RISK_DISCLAIMER = (
    "⚠ 긴급 안전 확인 필요\n\n"
    "현재 응답하신 위험 신호 조합으로 볼 때, 임대인에게 직접 어떤 메시지도 보내기 전에 "
    "전문 상담기관과 먼저 상담하는 것을 강력히 권장합니다.\n\n"
    "공정에너지는 본 단계에서 자료요청 메시지 예시를 표시하지 않습니다.\n"
    "본 도구는 사용자 자료 정리 보조 기능만 제공하며, 분쟁 행동을 권유하지 않습니다.\n\n"
    "지금 도움을 받을 수 있는 곳:\n"
    "  • 주거상담기관 (지자체 주거복지센터)\n"
    "  • 법률구조공단 국번없이 132\n"
    "  • 여성긴급전화 1366 (가정폭력·성폭력 관련)\n"
    "  • 외국인 노동자 지원기관\n"
    "  • 화우 ESG센터 공익 연계"
)


def _count_yes(response: SafetyCheckResponse) -> int:
    return sum(
        1
        for v in (
            response.contract_renewal_or_eviction,
            response.deposit_return_concern,
            response.landlord_threat_or_pressure,
            response.no_alternative_housing,
            response.foreign_status_or_employer_housing,
            response.feels_unsafe_to_request,
        )
        if v
    )


def classify_safety_level(response: SafetyCheckResponse) -> SafetyLevel:
    """안전 체크 응답을 LOW/MEDIUM/HIGH/VERY_HIGH 등급으로 분류.

    정책 05 §3 (2026-05-13 외부 자문 반영):
      VERY_HIGH:
        - 3번(폭언·협박) AND 그 외 위험 신호(4·5·6번) 중 1개 이상
        - 또는 4개 이상 yes
      HIGH:
        - 3번(폭언·협박) 단독 True
        - 또는 6번(자료 요청이 위험하다고 느낌) 단독 True
        - 또는 3개 yes (3번 미포함)
      MEDIUM:
        - 1~2개 yes (3·6 제외)
      LOW:
        - 모든 응답 False
    """
    threat = response.landlord_threat_or_pressure
    unsafe = response.feels_unsafe_to_request
    yes_count = _count_yes(response)

    # VERY_HIGH: 폭언/협박 + 추가 취약 신호 또는 yes 4개 이상.
    if threat and (
        response.no_alternative_housing
        or response.foreign_status_or_employer_housing
        or unsafe
    ):
        return SafetyLevel.VERY_HIGH
    if yes_count >= 4:
        return SafetyLevel.VERY_HIGH

    # HIGH: 3번 또는 6번 단독, 또는 yes 3개.
    if threat or unsafe:
        return SafetyLevel.HIGH
    if yes_count >= 3:
        return SafetyLevel.HIGH

    # MEDIUM: 1~2 yes (3·6 제외 — 이 경로에서는 이미 3·6은 False).
    if yes_count >= 1:
        return SafetyLevel.MEDIUM
    return SafetyLevel.LOW


def should_block_message_copy(response: SafetyCheckResponse) -> bool:
    """HIGH 이상이면 메시지 「복사」 버튼을 차단해야 한다.

    페이지는 메시지 본문을 보여주되 복사 액션은 비활성화한다(HIGH).
    VERY_HIGH에서는 메시지 본문 자체가 숨겨진다(`should_hide_message_template`).
    """
    return classify_safety_level(response) in (
        SafetyLevel.HIGH, SafetyLevel.VERY_HIGH,
    )


def should_hide_message_template(response: SafetyCheckResponse) -> bool:
    """VERY_HIGH 등급은 자료요청 메시지 예시 본문 자체를 숨겨야 한다.

    2026-05-13 자문 권고: 「VERY HIGH 등급: NGO/상담기관 안내를 먼저 표시하고,
    메시지 예시는 숨김」.
    """
    return classify_safety_level(response) == SafetyLevel.VERY_HIGH


def requires_two_step_confirmation(response: SafetyCheckResponse) -> bool:
    """HIGH 등급은 상담기관 안내를 먼저 보여주고 2단계 확인 후 메시지 예시 표시.

    2026-05-13 NGO 자문 권고:
    - HIGH 등급: 상담기관 안내를 먼저 표시, 2단계 확인 체크박스 후 메시지 노출.
    - VERY_HIGH는 별도(`should_hide_message_template`)로 처리되어 본 함수는 False 반환.
    """
    return classify_safety_level(response) == SafetyLevel.HIGH


# 하위 호환을 위한 기존 함수 — should_block_message_copy의 별칭.
# 기존 호출처는 그대로 동작한다.
should_block_message_template = should_block_message_copy


def recommended_disclaimer(response: SafetyCheckResponse) -> str:
    """안전 등급에 따라 노출할 안내 문구를 반환한다."""
    level = classify_safety_level(response)
    if level == SafetyLevel.VERY_HIGH:
        return VERY_HIGH_RISK_DISCLAIMER
    if level == SafetyLevel.HIGH:
        return HIGH_RISK_DISCLAIMER
    return DEFAULT_DISCLAIMER
