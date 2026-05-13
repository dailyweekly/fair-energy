"""1. 시작하기 — 서비스 소개와 사용자 생성.

여기서 익명 사용자 ID를 발급한다. 이후 페이지에서 동의·업로드가 이 ID에 묶인다.
"""

from __future__ import annotations

import streamlit as st

from core import db
from core.safety import DEFAULT_DISCLAIMER


st.set_page_config(page_title="시작하기 · 공정에너지", page_icon="⚡")
st.title("1. 시작하기")


# ---------------------------------------------------------------------------
# 안내 문구
# ---------------------------------------------------------------------------

st.markdown(
    """
공정에너지는 **임대 사각지대(고시원·다가구·다세대·반지하) 임차인**이
자신의 전기요금 청구 자료가 **검산 가능한 상태인지** 확인하고,
공식 요금 산식과 비교 가능한 경우에만 계산 근거를 제공하는 도구입니다.
"""
)

with st.container(border=True):
    st.markdown("**이 도구가 하는 일**")
    st.markdown(
        "- 업로드한 자료의 완결성 점수를 100점 만점으로 진단\n"
        "- 검산 가능성 4분류 (검산 불가 / 근거 요청 필요 / 예비 검산 가능 / 공식 산식 비교 가능)\n"
        "- 공식 산식 비교 가능 시 한전 전기요금 룰 엔진 계산\n"
        "- 빈칸형 자료요청 메시지 예시 (사용자 직접 편집)\n"
        "- 에너지 청구 자료 요약본 PDF 다운로드"
    )

with st.container(border=True):
    st.markdown("**이 도구가 하지 않는 일**")
    st.markdown(
        "- 위법성·부당청구·환급 가능성 판단\n"
        "- 소장·내용증명·민원 본문 작성\n"
        "- 임대인에게 자동 발송\n"
        "- 분쟁 행동 권유"
    )


# ---------------------------------------------------------------------------
# 사용자 발급
# ---------------------------------------------------------------------------

if st.session_state.get("user_id"):
    st.success(f"세션 사용자 ID: `{st.session_state['user_id']}`")
    st.page_link("pages/2_동의_및_안전체크.py", label="다음: 동의 및 안전체크 →")
else:
    st.markdown("---")
    st.markdown("**시작하기 전에**")
    cohort = st.radio(
        "어떤 경로로 오셨나요?",
        options=["일반 (직접 접속)", "NGO 동행"],
        index=0,
        help="KPI 측정용입니다. 익명 통계로만 사용됩니다.",
    )
    cohort_code = "ngo" if cohort.startswith("NGO") else "general"

    if st.button("시작하기", type="primary"):
        from app import conn  # type: ignore[attr-defined]
        from core import metrics

        user_id = db.insert_user(conn, cohort=cohort_code)
        st.session_state["user_id"] = user_id
        metrics.log_event(
            conn,
            event_name=metrics.EVENT_USER_REGISTERED,
            user_id=user_id,
            metadata={"cohort": cohort_code},
        )
        st.rerun()


# ---------------------------------------------------------------------------
# 면책 문구
# ---------------------------------------------------------------------------

with st.expander("법적 면책 (필독)"):
    st.markdown(DEFAULT_DISCLAIMER)
