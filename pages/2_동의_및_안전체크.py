"""2. 동의 및 안전 체크.

정책 04 §3 — 각 동의를 별도 체크박스로 받는다.
정책 05 §2 — 6문항 안전 체크 + 위험 등급 분류.
"""

from __future__ import annotations

import streamlit as st

from core import consent
from core.auth import require_password
from core.models import SafetyCheckResponse, SafetyLevel
from core.safety import (
    HIGH_RISK_DISCLAIMER,
    classify_safety_level,
)


require_password()

st.set_page_config(page_title="동의 및 안전체크 · 공정에너지", page_icon="⚡")
st.title("2. 동의 및 안전 체크")


# ---------------------------------------------------------------------------
# 가드: 사용자 ID
# ---------------------------------------------------------------------------

if not st.session_state.get("user_id"):
    st.warning("먼저 '시작하기' 페이지에서 시작해주세요.")
    st.page_link("pages/1_시작하기.py", label="← 시작하기로 이동")
    st.stop()


# ---------------------------------------------------------------------------
# 1) 동의 — 묶음 동의 금지(정책 04 §3)
# ---------------------------------------------------------------------------

st.subheader("1단계 — 동의")
st.caption("각 항목은 묶음 동의가 아니라 개별로 체크해주세요.")

with st.form("consent_form"):
    consent_service = st.checkbox(
        "**[필수]** 공정에너지 서비스 이용 약관에 동의합니다."
    )
    consent_personal_info = st.checkbox(
        "**[필수]** 개인정보 수집·이용에 동의합니다. "
        "(개인정보보호법 제15조)"
    )
    consent_ai_processing = st.checkbox(
        "**[필수]** 멀티모달 AI(외부 API) 처리에 동의합니다. "
        "동의하지 않으시면 수동 입력 모드를 이용하실 수 있습니다."
    )

    consent_storage_months = st.radio(
        "**[필수]** 원본 보관기간을 선택하세요.",
        options=[6, 12, 36],
        index=0,
        format_func=lambda m: f"{m}개월",
        horizontal=True,
        help="만료 30일 전 알림 후 재동의가 없으면 원본은 자동 파기됩니다.",
    )

    consent_ngo_share = st.checkbox(
        "**[선택]** NGO 케이스워커가 마스킹된 사본을 열람할 수 있도록 동의합니다. "
        "(원본은 공유되지 않습니다)"
    )

    st.markdown(
        "※ 외부 분쟁기관 제출 동의는 **건별·기관별 별도 동의**로 추후 진행됩니다 (정책 04 §7)."
    )

    consent_submitted = st.form_submit_button("동의 제출", type="primary")

if consent_submitted:
    try:
        from app import conn  # type: ignore[attr-defined]
        from core import metrics

        request = consent.ConsentRequest(
            consent_service=consent_service,
            consent_personal_info=consent_personal_info,
            consent_ai_processing=consent_ai_processing,
            consent_storage_months=consent_storage_months,
            consent_ngo_share=consent_ngo_share,
        )
        consent_id = consent.record_consent(
            conn, user_id=st.session_state["user_id"], request=request
        )
        st.session_state["consent_id"] = consent_id
        metrics.log_event(
            conn,
            event_name=metrics.EVENT_CONSENT_COMPLETED,
            user_id=st.session_state["user_id"],
            metadata={
                "storage_months": consent_storage_months,
                "ai_processing": consent_ai_processing,
                "ngo_share": consent_ngo_share,
            },
        )
        st.success("동의가 저장되었습니다. 다음 단계로 진행하세요.")
    except consent.ConsentValidationError as exc:
        st.error(f"동의 처리 실패: {exc}")


# ---------------------------------------------------------------------------
# 2) 안전 체크 (정책 05 §2)
# ---------------------------------------------------------------------------

if st.session_state.get("consent_id"):
    st.markdown("---")
    st.subheader("2단계 — 안전 체크")
    st.caption(
        "현재 상황의 안전도를 파악합니다. 응답은 위험 신호 평가에만 사용됩니다."
    )

    with st.form("safety_form"):
        q1 = st.radio("1. 현재 계약갱신 또는 퇴거 협의 중인가요?",
                      ["아니오", "예"], horizontal=True)
        q2 = st.radio("2. 보증금 반환이 걱정되나요?",
                      ["아니오", "예"], horizontal=True)
        q3 = st.radio("3. 임대인으로부터 폭언·협박·퇴거 압박을 받은 적이 있나요?",
                      ["아니오", "예"], horizontal=True)
        q4 = st.radio("4. 대체 주거지가 없나요?",
                      ["아니오", "예"], horizontal=True)
        q5 = st.radio("5. 외국인 체류자격 또는 직장 제공 숙소와 연결되어 있나요?",
                      ["아니오", "예"], horizontal=True)
        q6 = st.radio("6. 임대인에게 자료 요청을 보내는 것이 위험하다고 느끼나요?",
                      ["아니오", "예"], horizontal=True)

        safety_submitted = st.form_submit_button("안전 체크 제출", type="primary")

    if safety_submitted:
        from app import conn  # type: ignore[attr-defined]
        from core import metrics

        response = SafetyCheckResponse(
            contract_renewal_or_eviction=(q1 == "예"),
            deposit_return_concern=(q2 == "예"),
            landlord_threat_or_pressure=(q3 == "예"),
            no_alternative_housing=(q4 == "예"),
            foreign_status_or_employer_housing=(q5 == "예"),
            feels_unsafe_to_request=(q6 == "예"),
        )
        level = classify_safety_level(response)
        st.session_state["safety_response"] = response
        st.session_state["safety_level"] = level.value
        metrics.log_event(
            conn,
            event_name=metrics.EVENT_SAFETY_CHECK_COMPLETED,
            user_id=st.session_state["user_id"],
            metadata={"safety_level": level.value},
        )

        if level == SafetyLevel.HIGH:
            st.error(HIGH_RISK_DISCLAIMER)
        elif level == SafetyLevel.MEDIUM:
            st.info(
                "안전 신호가 일부 감지되었습니다. "
                "진행하시되, 결과 확인 전에 주거상담기관 안내를 함께 확인해주세요."
            )
        else:
            st.success("안전 체크 완료. 다음 단계로 진행하세요.")

        st.page_link("pages/3_문서업로드.py", label="다음: 문서 업로드 →")
