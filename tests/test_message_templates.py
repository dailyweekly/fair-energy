"""자료 확인 메시지 예시 모듈 테스트 (Phase 9).

정책 01 §8 + 외부 자문(2026-05-13) 표현 범위 회귀 검증.
"""

from __future__ import annotations

import pytest

from core import message_templates
from core.guardrails import UnsafeOutputError, is_safe_output
from core.models import CaseClassification


# ---------------------------------------------------------------------------
# 템플릿 목록 / 적용 분류
# ---------------------------------------------------------------------------


def test_templates_defined_and_have_required_fields() -> None:
    """모든 템플릿이 핵심 필드를 가져야 한다."""
    assert len(message_templates.MESSAGE_TEMPLATES) >= 3
    for t in message_templates.MESSAGE_TEMPLATES:
        assert t.key
        assert t.title
        assert t.purpose
        assert t.body
        assert t.applicable_to


def test_all_template_bodies_pass_guardrail() -> None:
    """템플릿 본문이 금지어 필터를 모두 통과해야 한다."""
    for t in message_templates.MESSAGE_TEMPLATES:
        assert is_safe_output(t.body), f"템플릿 가드레일 실패: {t.key}"


def test_not_calculable_returns_no_template() -> None:
    """검산 불가 케이스는 메시지 예시를 제공하지 않는다."""
    result = message_templates.list_applicable_templates(
        CaseClassification.NOT_CALCULABLE,
    )
    assert result == []


def test_fixed_fee_returns_no_template() -> None:
    """정액 관리비 케이스도 메시지 예시 미제공."""
    result = message_templates.list_applicable_templates(
        CaseClassification.FIXED_MANAGEMENT_FEE,
    )
    assert result == []


def test_needs_basis_returns_multiple_templates() -> None:
    """근거 요청 필요 케이스에서는 여러 템플릿이 제공된다."""
    result = message_templates.list_applicable_templates(
        CaseClassification.NEEDS_BASIS_REQUEST,
    )
    assert len(result) >= 3  # basic, allocation, meter, reconciliation 중 다수


def test_official_returns_only_reconciliation() -> None:
    """공식 산식 비교 가능 케이스는 정산 재확인 템플릿만 제공된다.

    이미 검산이 가능한 케이스에서는 자료 요청이 분쟁 행동으로 비치지 않도록
    범위를 좁힌다 — 「정산 재확인 요청」 한 종류만.
    """
    result = message_templates.list_applicable_templates(
        CaseClassification.OFFICIAL_COMPARISON,
    )
    assert len(result) == 1
    assert result[0].purpose == "정산 재확인 요청"


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------


def test_render_with_full_context() -> None:
    t = message_templates.MESSAGE_TEMPLATES[0]
    ctx = message_templates.TemplateContext(
        address="관악구 봉천동 ○○호실",
        billing_period="2026-04-01 ~ 2026-04-30",
    )
    rendered = message_templates.render_template(t, ctx)
    assert "관악구 봉천동" in rendered
    assert "2026-04-01" in rendered
    # 플레이스홀더가 모두 치환되었는지.
    assert "{address}" not in rendered
    assert "{billing_period}" not in rendered


def test_render_with_empty_context_uses_placeholder() -> None:
    """컨텍스트가 비어 있으면 「직접 입력」 안내문이 들어간다."""
    t = next(
        x for x in message_templates.MESSAGE_TEMPLATES
        if "{address}" in x.body
    )
    rendered = message_templates.render_template(
        t, message_templates.TemplateContext(),
    )
    assert "직접 입력" in rendered


def test_render_result_passes_guardrail() -> None:
    """렌더 결과가 가드레일을 통과해야 한다."""
    for t in message_templates.MESSAGE_TEMPLATES:
        rendered = message_templates.render_template(
            t,
            message_templates.TemplateContext(
                address="○○구 ○○호실",
                billing_period="2026-04-01 ~ 2026-04-30",
            ),
        )
        assert is_safe_output(rendered)


# ---------------------------------------------------------------------------
# 편집 후 검증 — 금지 표현 차단
# ---------------------------------------------------------------------------


def test_validate_edited_passes_neutral_text() -> None:
    text = (
        "안녕하세요. 임대인님께 자료 확인을 요청드립니다. "
        "정산 내역을 함께 살펴볼 수 있을까요?"
    )
    message_templates.validate_edited_message(text)  # 예외 없음


def test_validate_edited_blocks_refund_demand() -> None:
    """반환 요구 표현은 차단되어야 한다."""
    text = "X원을 반환해 주시기 바랍니다."
    with pytest.raises(UnsafeOutputError):
        message_templates.validate_edited_message(text)


def test_validate_edited_blocks_overcharge_assertion() -> None:
    """과다 청구 단정 표현 차단."""
    text = "귀하의 청구는 과다 청구로 보입니다."
    with pytest.raises(UnsafeOutputError):
        message_templates.validate_edited_message(text)


def test_validate_edited_blocks_legal_threat() -> None:
    """법적 조치 암시 표현 차단."""
    text = "응답이 없을 시 법적 조치를 검토하겠습니다."
    with pytest.raises(UnsafeOutputError):
        message_templates.validate_edited_message(text)


def test_validate_edited_blocks_violation_assertion() -> None:
    """위법성 단정 표현 차단."""
    text = "임대인의 위법한 청구로 보입니다."
    with pytest.raises(UnsafeOutputError):
        message_templates.validate_edited_message(text)


def test_validate_edited_blocks_blame() -> None:
    """임대인 비난 표현 차단."""
    text = "임대인이 잘못한 부분이 있어 정정을 요청합니다."
    with pytest.raises(UnsafeOutputError):
        message_templates.validate_edited_message(text)


# ---------------------------------------------------------------------------
# 안내 문구 가드레일
# ---------------------------------------------------------------------------


def test_static_guidance_passes_guardrail() -> None:
    assert is_safe_output(message_templates.MESSAGE_PAGE_HEADER_NOTE)
    assert is_safe_output(message_templates.MESSAGE_EDIT_GUIDANCE)
