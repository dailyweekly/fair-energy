"""4분류 + 정액 관리비 분류 테스트.

정책: docs/policies/02_calculation_gate_policy.md §9
"""

from __future__ import annotations

import pytest

from core.classification import classify_case
from core.models import CaseClassification, CompletenessScore, TariffInput


def _score(total: int) -> CompletenessScore:
    """total_score만 의미 있게 두는 헬퍼."""
    return CompletenessScore(total_score=total)


def _full_input(user_confirmed: bool = True) -> TariffInput:
    """필수 필드가 모두 채워진 TariffInput."""
    return TariffInput(
        usage_kwh=245.0,
        billing_start_date="2026-04-01",
        billing_end_date="2026-04-30",
        contract_type="residential_low_voltage",
        user_charged_amount=38000,
        allocation_formula="사용량 기반",
        user_confirmed=user_confirmed,
    )


def _empty_input() -> TariffInput:
    return TariffInput(user_confirmed=False)


# --- 점수 게이트 ---

@pytest.mark.parametrize("total", [0, 10, 39])
def test_below_40_is_not_calculable(total: int) -> None:
    assert classify_case(_score(total), _empty_input()) == CaseClassification.NOT_CALCULABLE


@pytest.mark.parametrize("total", [40, 55, 69])
def test_40_to_69_is_needs_basis_request(total: int) -> None:
    assert (
        classify_case(_score(total), _empty_input())
        == CaseClassification.NEEDS_BASIS_REQUEST
    )


@pytest.mark.parametrize("total", [70, 80, 89])
def test_70_to_89_is_preliminary(total: int) -> None:
    assert (
        classify_case(_score(total), _empty_input())
        == CaseClassification.PRELIMINARY_CALCULATION
    )


# --- 90점 이상: 필드/확인 게이트 ---

def test_90_plus_with_full_fields_and_confirmed_is_official() -> None:
    """점수 90+, 필수 필드 완비, user_confirmed=True → OFFICIAL_COMPARISON."""
    result = classify_case(_score(95), _full_input(user_confirmed=True))
    assert result == CaseClassification.OFFICIAL_COMPARISON


def test_90_plus_without_required_fields_is_preliminary() -> None:
    """점수만 높고 필수 필드 누락이면 PRELIMINARY로 강등."""
    partial = TariffInput(
        usage_kwh=245.0,
        billing_start_date=None,  # 누락
        billing_end_date="2026-04-30",
        user_charged_amount=38000,
        user_confirmed=True,
    )
    assert (
        classify_case(_score(95), partial)
        == CaseClassification.PRELIMINARY_CALCULATION
    )


def test_90_plus_without_user_confirmation_is_preliminary() -> None:
    """필드가 완비되어 있어도 user_confirmed=False면 OFFICIAL로 올리지 않음."""
    result = classify_case(_score(95), _full_input(user_confirmed=False))
    assert result == CaseClassification.PRELIMINARY_CALCULATION


def test_exactly_100_with_full_fields_is_official() -> None:
    result = classify_case(_score(100), _full_input(user_confirmed=True))
    assert result == CaseClassification.OFFICIAL_COMPARISON


# --- 정액 관리비 케이스 ---

def test_fixed_fee_overrides_score() -> None:
    """is_fixed_fee=True면 점수와 무관하게 FIXED_MANAGEMENT_FEE."""
    assert (
        classify_case(_score(100), _full_input(True), is_fixed_fee=True)
        == CaseClassification.FIXED_MANAGEMENT_FEE
    )
    assert (
        classify_case(_score(0), _empty_input(), is_fixed_fee=True)
        == CaseClassification.FIXED_MANAGEMENT_FEE
    )


# --- 경계값 회귀 ---

@pytest.mark.parametrize(
    "total, expected",
    [
        (39, CaseClassification.NOT_CALCULABLE),
        (40, CaseClassification.NEEDS_BASIS_REQUEST),
        (69, CaseClassification.NEEDS_BASIS_REQUEST),
        (70, CaseClassification.PRELIMINARY_CALCULATION),
        (89, CaseClassification.PRELIMINARY_CALCULATION),
    ],
)
def test_boundary_values(total: int, expected: CaseClassification) -> None:
    assert classify_case(_score(total), _empty_input()) == expected


# ===========================================================================
# Phase 6 — 디스크립터와 사유 헬퍼
# ===========================================================================

from core.classification import (  # noqa: E402
    CASE_DESCRIPTORS,
    describe_case,
    reasons_blocking_official,
)
from core.guardrails import is_safe_output  # noqa: E402


@pytest.mark.parametrize("case", list(CaseClassification))
def test_every_case_has_descriptor(case: CaseClassification) -> None:
    descriptor = describe_case(case)
    assert descriptor.case == case
    assert descriptor.headline
    assert descriptor.explanation
    assert descriptor.next_actions  # non-empty


@pytest.mark.parametrize("case", list(CaseClassification))
def test_descriptor_texts_pass_guardrails(case: CaseClassification) -> None:
    """디스크립터의 모든 사용자 노출 문구가 정책 01 금지어 필터를 통과해야 한다."""
    d = describe_case(case)
    assert is_safe_output(d.headline), f"headline failed: {d.headline}"
    assert is_safe_output(d.explanation), f"explanation failed: {d.explanation}"
    for action in d.next_actions:
        assert is_safe_output(action), f"action failed: {action}"


def test_fixed_fee_descriptor_mentions_policy_guidance() -> None:
    """정액 관리비 케이스 안내에 국토부 정책 안내가 포함되어야 한다."""
    d = describe_case(CaseClassification.FIXED_MANAGEMENT_FEE)
    combined = d.explanation + " " + " ".join(d.next_actions)
    assert "국토부" in combined or "관리비 세부" in combined


def test_official_descriptor_keeps_neutral_tone() -> None:
    """OFFICIAL_COMPARISON 안내는 환급·승소 등을 단정해서는 안 된다."""
    d = describe_case(CaseClassification.OFFICIAL_COMPARISON)
    text = d.headline + " " + d.explanation + " " + " ".join(d.next_actions)
    # 가드레일 통과 = 환급 가능·승소 등 단정 표현 없음.
    assert is_safe_output(text)


# --- reasons_blocking_official ---

def test_blocking_empty_when_official_ready() -> None:
    """100점 + 필수 필드 + 사용자 확인 → 사유 없음(OFFICIAL 가능)."""
    reasons = reasons_blocking_official(
        _score(95),
        _full_input(user_confirmed=True),
        is_fixed_fee=False,
    )
    assert reasons == []


def test_blocking_includes_score_below_90() -> None:
    reasons = reasons_blocking_official(
        _score(70),
        _full_input(user_confirmed=True),
    )
    assert any("90점 미만" in r for r in reasons)


def test_blocking_includes_each_missing_required_field() -> None:
    partial = TariffInput(
        usage_kwh=None,             # 누락
        billing_start_date="2026-04-01",
        billing_end_date=None,      # 누락
        user_charged_amount=38000,
        user_confirmed=True,
    )
    reasons = reasons_blocking_official(_score(95), partial)
    joined = " ".join(reasons)
    assert "사용량" in joined
    assert "검침 종료일" in joined


def test_blocking_includes_unconfirmed_flag() -> None:
    reasons = reasons_blocking_official(
        _score(95),
        _full_input(user_confirmed=False),
    )
    assert any("직접 확인하지 않았습니다" in r for r in reasons)


def test_blocking_short_circuits_on_fixed_fee() -> None:
    """정액 케이스이면 다른 사유는 무의미 — 단일 사유로 종료."""
    reasons = reasons_blocking_official(
        _score(0),
        _empty_input(),
        is_fixed_fee=True,
    )
    assert len(reasons) == 1
    assert "정액 관리비" in reasons[0]
