"""1. 시작하기 — 서비스 소개와 사용자 생성.

여기서 익명 사용자 ID를 발급한다. 이후 페이지에서 동의·업로드가 이 ID에 묶인다.
"""

from __future__ import annotations

import streamlit as st

from core import db, demo, ui
from core.auth import require_password
from core.safety import DEFAULT_DISCLAIMER


require_password()

st.set_page_config(
    page_title="시작하기 · 공정에너지",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)

from app import conn  # type: ignore[attr-defined]

if demo.is_demo_mode():
    demo.ensure_demo_session(conn)

ui.render_chrome(current_page_num=1, demo_mode=demo.is_demo_mode())

st.title("1. 시작하기")


# ---------------------------------------------------------------------------
# 안내 문구
# ---------------------------------------------------------------------------

st.markdown(
    """
공정에너지는 **한전이 아닌 임대인이 매달 전기요금을 분배 청구하는 구조**의 임차인이
자신이 낸 전기요금이 **한전 공식 요금표대로 정확히 산정되었는지** 본인이 직접 확인할 수 있도록 돕는 도구입니다.

> ℹ️ **기준은 주거 형태가 아니라 청구 구조입니다.**
> 자주 발견되는 사례는 고시원·다가구 임차인이며, 다세대·반지하·원룸 등은 같은 건물·층이라도 호실마다 청구 구조가 다를 수 있습니다.
> 본인이 한전 명의로 직접 청구서를 받고 한전 고객번호를 가지고 있다면 본 서비스 대상이 아닙니다 —
> 한전 약관·요금표가 그대로 적용되어 별도 검산이 거의 필요하지 않기 때문입니다.
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
    st.success("✅ 준비가 완료되었어요. 다음 단계로 넘어가 주세요.")
    st.page_link("pages/2_동의_및_안전체크.py", label="다음: 동의 및 안전체크 →")
    # 기술 식별자는 문제 신고·로그 조회용으로만 노출.
    with st.expander("기술 정보 (문제 신고 시에만 필요)"):
        st.caption(
            "아래 ID는 로그인 계정이 아니라 이번 방문의 익명 식별자입니다. "
            "오류 신고 시 함께 알려주시면 로그 조회가 빨라집니다. 평소에는 무시해도 됩니다."
        )
        st.code(st.session_state["user_id"], language=None)
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
