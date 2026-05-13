"""7. 자료 확인 메시지 예시 (Phase 9 — 2026-05-13 외부 자문 반영).

정책 01 §8 + 05 §3의 4단계 안전 차단(LOW/MEDIUM/HIGH/VERY_HIGH)에 따라
메시지 예시 본문·복사 버튼 노출을 조절한다.

⚠ 한계 사항 (LIMITATION):
- 본 페이지의 표현 범위는 외부 전문가 의견(2026-05-13)을 반영한 추정 안전 영역.
- 화우 ESG센터 실제 사전 검토 의견서(G5) 수령 후 재검토 필요.
- 자동 발송 기능 절대 미구현.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from core import classification, demo, message_templates, metrics, scoring, ui
from core.auth import require_password
from core.guardrails import UnsafeOutputError
from core.models import CaseClassification, SafetyLevel
from core.safety import (
    HIGH_RISK_DISCLAIMER,
    VERY_HIGH_RISK_DISCLAIMER,
    classify_safety_level,
    requires_two_step_confirmation,
    should_hide_message_template,
)


require_password()

st.set_page_config(
    page_title="자료 확인 메시지 예시 · 공정에너지",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

if demo.is_demo_mode():
    demo.ensure_demo_session(conn)

ui.render_chrome(current_page_num=7, demo_mode=demo.is_demo_mode())

st.title("7. 자료 확인 메시지 예시")


# ---------------------------------------------------------------------------
# 가드
# ---------------------------------------------------------------------------

if not st.session_state.get("user_id"):
    st.warning("먼저 시작하기 페이지에서 시작해주세요.")
    st.page_link("pages/1_시작하기.py", label="← 시작하기")
    st.stop()

if not st.session_state.get("consent_id"):
    st.warning("동의가 필요합니다.")
    st.page_link("pages/2_동의_및_안전체크.py", label="← 동의 및 안전 체크")
    st.stop()


from app import conn  # type: ignore[attr-defined]

user_id = st.session_state["user_id"]

st.markdown(message_templates.MESSAGE_PAGE_HEADER_NOTE)


# ---------------------------------------------------------------------------
# 현재 분류 계산
# ---------------------------------------------------------------------------

score = scoring.compute_completeness_score(conn, user_id=user_id)
tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
is_fixed_fee = scoring.detect_fixed_fee(conn, user_id=user_id)

override = st.session_state.get("fixed_fee_override")
effective_fixed_fee = override if override is not None else is_fixed_fee
case = classification.classify_case(
    score, tariff_input, is_fixed_fee=effective_fixed_fee,
)


# ---------------------------------------------------------------------------
# 4단계 안전 차단 (정책 05 §3)
# ---------------------------------------------------------------------------

safety_response = st.session_state.get("safety_response")
safety_level_str = st.session_state.get("safety_level", "LOW")

if safety_response is not None and should_hide_message_template(safety_response):
    # VERY_HIGH — 메시지 본문 자체 숨김.
    st.error("VERY_HIGH 등급 안전 신호가 감지되어 메시지 예시는 표시되지 않습니다.")
    st.markdown(VERY_HIGH_RISK_DISCLAIMER)
    metrics.log_event(
        conn,
        event_name=metrics.EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED,
        user_id=user_id,
        metadata={
            "safety_level": "VERY_HIGH",
            "action": "template_hidden",
        },
    )
    st.markdown("---")
    st.page_link(
        "pages/8_자료요약본.py",
        label="자료 요약본으로 이동 (메시지 없이 본인이 직접 활용)",
    )
    st.stop()

if (
    safety_response is not None
    and requires_two_step_confirmation(safety_response)
):
    # HIGH — 상담기관 안내 우선, 2단계 확인 후 노출.
    st.warning("HIGH 등급 안전 신호가 감지되었습니다.")
    st.markdown(HIGH_RISK_DISCLAIMER)
    st.markdown("---")
    confirmed_view = st.checkbox(
        "위 안내를 확인하였으며, 메시지 예시를 검토하고자 합니다."
    )
    if not confirmed_view:
        metrics.log_event(
            conn,
            event_name=metrics.EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED,
            user_id=user_id,
            metadata={"safety_level": "HIGH", "action": "awaiting_confirmation"},
        )
        st.stop()

elif safety_level_str == SafetyLevel.MEDIUM.value:
    st.info(
        "안전 신호가 일부 감지되었습니다. 메시지를 보내기 전에 상황을 한 번 더 점검해 보세요."
    )


# ---------------------------------------------------------------------------
# 분류별 메시지 적용 가능성
# ---------------------------------------------------------------------------

templates = message_templates.list_applicable_templates(case)

if not templates:
    if case == CaseClassification.NOT_CALCULABLE:
        st.info(
            "현재 분류(**검산 불가**)에서는 자료 요청 메시지 예시가 제공되지 않습니다. "
            "먼저 자료 체크리스트를 확보하시기 바랍니다."
        )
    elif case == CaseClassification.FIXED_MANAGEMENT_FEE:
        st.info(
            "현재 분류(**정액 관리비 케이스**)에서는 자료 요청 메시지 예시가 제공되지 않습니다. "
            "국토부 관리비 세부표시 의무 정책 안내가 별도 페이지로 제공됩니다."
        )
    else:
        st.info(f"현재 분류({case.value})에서는 적용 가능한 템플릿이 없습니다.")
    st.page_link("pages/8_자료요약본.py", label="자료 요약본으로 이동 →")
    st.stop()


# ---------------------------------------------------------------------------
# 사용자 입력 — 중립 사실값 (자동 채움용)
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("메시지 자동 채움 값 (선택)")
st.caption("아래 값은 메시지의 `{address}`·`{billing_period}` 자리에만 사용됩니다.")

col_a, col_b = st.columns(2)
address_input = col_a.text_input(
    "주소·호실 (메시지 머리말)",
    placeholder="예: 관악구 봉천동 ○○호실",
)
period_input = col_b.text_input(
    "청구 기간",
    value=(
        f"{tariff_input.billing_start_date} ~ {tariff_input.billing_end_date}"
        if (tariff_input.billing_start_date and tariff_input.billing_end_date)
        else ""
    ),
    placeholder="예: 2026-04-01 ~ 2026-04-30",
)

context = message_templates.TemplateContext(
    address=address_input.strip() or None,
    billing_period=period_input.strip() or None,
)


# ---------------------------------------------------------------------------
# 템플릿 표시 + 편집 + 복사
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("적용 가능한 메시지 예시")
st.caption(message_templates.MESSAGE_EDIT_GUIDANCE)

for template in templates:
    with st.expander(f"{template.title} ({template.purpose})", expanded=False):
        rendered = message_templates.render_template(template, context)
        edited_key = f"edit_{template.key}"
        edited = st.text_area(
            "메시지 본문 (직접 수정 가능)",
            value=rendered,
            height=300,
            key=edited_key,
        )

        # 편집된 내용에 대한 가드레일 검증.
        try:
            message_templates.validate_edited_message(edited)
            safe = True
            err = None
        except UnsafeOutputError as exc:
            safe = False
            err = str(exc)

        if not safe:
            st.error(
                "편집한 메시지에서 자동 차단된 표현이 감지되었습니다. "
                "「반환 요구」·「과다 청구」·「법적 조치」 등의 표현을 제외하고 다시 수정해주세요."
            )
            st.caption(f"검출 내역: {err}")

        # 조회 이벤트 (한 번만, 페이지 로드 시).
        view_logged_key = f"viewed_{template.key}"
        if not st.session_state.get(view_logged_key):
            metrics.log_event(
                conn,
                event_name=metrics.EVENT_REQUEST_TEMPLATE_VIEWED,
                user_id=user_id,
                metadata={
                    "template_key": template.key,
                    "safety_level": safety_level_str,
                    "classification": case.value,
                },
            )
            st.session_state[view_logged_key] = True

        # 복사 영역 — Streamlit은 OS 클립보드 직접 접근이 제한적.
        # 사용자가 박스를 선택해 복사하도록 `st.code()` 박스 제공.
        if safe:
            if st.button(
                f"복사용 박스 표시 — {template.key}",
                key=f"copy_btn_{template.key}",
            ):
                metrics.log_event(
                    conn,
                    event_name=metrics.EVENT_REQUEST_TEMPLATE_COPIED,
                    user_id=user_id,
                    metadata={
                        "template_key": template.key,
                        "safety_level": safety_level_str,
                    },
                )
                st.code(edited, language=None)
                st.caption(
                    "위 박스를 길게 눌러 복사한 뒤 사용하세요. "
                    "보내기 전 한 번 더 내용을 검토해주시기 바랍니다."
                )


# ---------------------------------------------------------------------------
# 기관 안내 — 정적 정보 카드 (정책 07 권고: RAG 제외)
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("외부 기관 정적 안내")

procedures_dir = Path(__file__).resolve().parent.parent / "data" / "procedures"

procedure_files = {
    "한전 전기소비자보호센터": "kepco_consumer_center.md",
    "주택임대차분쟁조정위": "lease_dispute_committee.md",
    "법률구조공단·공익변호사": "legal_aid_corporation.md",
}

for label, filename in procedure_files.items():
    path = procedures_dir / filename
    if not path.exists():
        continue
    with st.expander(label, expanded=False):
        st.markdown(path.read_text(encoding="utf-8"))


st.markdown("---")
st.caption(
    "본 페이지의 메시지·안내문은 외부 자문(2026-05-13) 의견을 반영한 추정 안전 영역입니다. "
    "화우 ESG센터의 최종 검토 의견서 수령 후 표현이 조정될 수 있습니다."
)
