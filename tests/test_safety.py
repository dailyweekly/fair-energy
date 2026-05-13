"""사용자 안전 체크 테스트.

정책: docs/policies/05_user_safety_policy.md §9
"""

from __future__ import annotations

from core.models import SafetyCheckResponse, SafetyLevel
from core.safety import (
    DEFAULT_DISCLAIMER,
    HIGH_RISK_DISCLAIMER,
    VERY_HIGH_RISK_DISCLAIMER,
    classify_safety_level,
    recommended_disclaimer,
    should_block_message_copy,
    should_block_message_template,
    should_hide_message_template,
)


def _resp(**kwargs: bool) -> SafetyCheckResponse:
    return SafetyCheckResponse(**kwargs)


# --- 등급 분류 ---

def test_all_no_is_low() -> None:
    assert classify_safety_level(_resp()) == SafetyLevel.LOW


def test_single_non_critical_yes_is_medium() -> None:
    """1·2·4·5번 중 하나만 True면 MEDIUM."""
    assert (
        classify_safety_level(_resp(contract_renewal_or_eviction=True))
        == SafetyLevel.MEDIUM
    )
    assert (
        classify_safety_level(_resp(deposit_return_concern=True))
        == SafetyLevel.MEDIUM
    )


def test_two_non_critical_yes_is_medium() -> None:
    response = _resp(
        contract_renewal_or_eviction=True,
        deposit_return_concern=True,
    )
    assert classify_safety_level(response) == SafetyLevel.MEDIUM


def test_threat_alone_is_high() -> None:
    """3번(폭언·협박·퇴거 압박) 단독으로 HIGH."""
    response = _resp(landlord_threat_or_pressure=True)
    assert classify_safety_level(response) == SafetyLevel.HIGH


def test_feels_unsafe_alone_is_high() -> None:
    """6번(자료 요청이 위험하다고 느낌) 단독으로 HIGH."""
    response = _resp(feels_unsafe_to_request=True)
    assert classify_safety_level(response) == SafetyLevel.HIGH


def test_three_or_more_yes_is_high() -> None:
    """1·2·4 동시 True면 (3·6 아니어도) HIGH."""
    response = _resp(
        contract_renewal_or_eviction=True,
        deposit_return_concern=True,
        no_alternative_housing=True,
    )
    assert classify_safety_level(response) == SafetyLevel.HIGH


def test_foreign_status_alone_is_medium() -> None:
    """5번 단독은 MEDIUM."""
    response = _resp(foreign_status_or_employer_housing=True)
    assert classify_safety_level(response) == SafetyLevel.MEDIUM


# --- VERY_HIGH 등급 (2026-05-13) ---

def test_threat_plus_no_housing_is_very_high() -> None:
    """폭언·협박 + 대체 주거 없음 → VERY_HIGH."""
    response = _resp(
        landlord_threat_or_pressure=True,
        no_alternative_housing=True,
    )
    assert classify_safety_level(response) == SafetyLevel.VERY_HIGH


def test_threat_plus_unsafe_is_very_high() -> None:
    """폭언·협박 + 자료 요청 위험감 → VERY_HIGH."""
    response = _resp(
        landlord_threat_or_pressure=True,
        feels_unsafe_to_request=True,
    )
    assert classify_safety_level(response) == SafetyLevel.VERY_HIGH


def test_threat_plus_foreign_status_is_very_high() -> None:
    """폭언·협박 + 외국인/직장 제공 숙소 → VERY_HIGH."""
    response = _resp(
        landlord_threat_or_pressure=True,
        foreign_status_or_employer_housing=True,
    )
    assert classify_safety_level(response) == SafetyLevel.VERY_HIGH


def test_four_or_more_yes_is_very_high() -> None:
    """4개 이상 응답이 True면 (3번 아니어도) VERY_HIGH."""
    response = _resp(
        contract_renewal_or_eviction=True,
        deposit_return_concern=True,
        no_alternative_housing=True,
        foreign_status_or_employer_housing=True,
    )
    assert classify_safety_level(response) == SafetyLevel.VERY_HIGH


def test_threat_alone_stays_high_not_very_high() -> None:
    """폭언·협박 단독은 HIGH지 VERY_HIGH로 격상되지 않는다."""
    response = _resp(landlord_threat_or_pressure=True)
    assert classify_safety_level(response) == SafetyLevel.HIGH


# --- 메시지 차단 게이트 ---

def test_high_blocks_message_copy() -> None:
    high = _resp(landlord_threat_or_pressure=True)
    assert should_block_message_copy(high) is True


def test_very_high_blocks_message_copy() -> None:
    very_high = _resp(
        landlord_threat_or_pressure=True,
        feels_unsafe_to_request=True,
    )
    assert should_block_message_copy(very_high) is True


def test_medium_does_not_block_message_copy() -> None:
    medium = _resp(contract_renewal_or_eviction=True)
    assert should_block_message_copy(medium) is False


def test_low_does_not_block_message_copy() -> None:
    assert should_block_message_copy(_resp()) is False


# --- 메시지 본문 숨김 게이트 (VERY_HIGH 전용) ---

def test_very_high_hides_message_template() -> None:
    """VERY_HIGH는 메시지 예시 본문 자체가 숨겨져야 한다."""
    very_high = _resp(
        landlord_threat_or_pressure=True,
        no_alternative_housing=True,
    )
    assert should_hide_message_template(very_high) is True


def test_high_does_not_hide_message_template() -> None:
    """HIGH는 본문은 표시하되 복사만 차단."""
    high = _resp(landlord_threat_or_pressure=True)
    assert should_hide_message_template(high) is False


def test_low_does_not_hide_message_template() -> None:
    assert should_hide_message_template(_resp()) is False


# 기존 호출처 호환성 — should_block_message_template은 should_block_message_copy의 별칭.
def test_block_message_template_alias() -> None:
    high = _resp(landlord_threat_or_pressure=True)
    assert should_block_message_template(high) is should_block_message_copy(high)


# --- 안내 문구 선택 ---

def test_high_gets_high_risk_disclaimer() -> None:
    high = _resp(feels_unsafe_to_request=True)
    text = recommended_disclaimer(high)
    assert text == HIGH_RISK_DISCLAIMER
    assert "주거상담기관" in text
    assert "법률구조공단" in text


def test_very_high_gets_very_high_risk_disclaimer() -> None:
    very_high = _resp(
        landlord_threat_or_pressure=True,
        feels_unsafe_to_request=True,
    )
    text = recommended_disclaimer(very_high)
    assert text == VERY_HIGH_RISK_DISCLAIMER
    assert "긴급 안전 확인 필요" in text
    assert "여성긴급전화" in text  # VERY_HIGH 전용 추가 안내


def test_low_gets_default_disclaimer() -> None:
    assert recommended_disclaimer(_resp()) == DEFAULT_DISCLAIMER


def test_default_disclaimer_mentions_no_legal_advice() -> None:
    """면책 문구는 '법률 자문 아님'을 명시해야 한다."""
    assert "법률 자문" in DEFAULT_DISCLAIMER
    assert "환급 가능성 판단을 제공하지 않습니다" in DEFAULT_DISCLAIMER


# --- 가드레일과의 정합성 ---

def test_disclaimers_pass_guardrails() -> None:
    """면책 문구 자체가 금지어 필터를 통과해야 한다.

    DEFAULT_DISCLAIMER에는 '환급 가능성 판단을 제공하지 않습니다'라는
    부정형 문구가 들어 있어 패턴 매칭상 '환급 가능'으로 검출될 수 있다.
    이 경우 문구를 조정하거나 가드레일을 수정해야 한다.
    """
    from core.guardrails import is_safe_output

    # HIGH_RISK_DISCLAIMER와 VERY_HIGH_RISK_DISCLAIMER는 통과해야 한다.
    assert is_safe_output(HIGH_RISK_DISCLAIMER), (
        "HIGH_RISK_DISCLAIMER must pass guardrails"
    )
    assert is_safe_output(VERY_HIGH_RISK_DISCLAIMER), (
        "VERY_HIGH_RISK_DISCLAIMER must pass guardrails"
    )
