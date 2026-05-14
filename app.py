"""공정에너지 Streamlit 진입점 — 토스 스타일 UI + 데모 모드.

모든 페이지가 공유하는 세션 상태·DB 연결·테마·인증을 정의한다.
실제 페이지 콘텐츠는 `pages/*.py`에 있다.
"""

from __future__ import annotations

import streamlit as st

from core import config, db, demo, ui
from core.auth import require_password


# ---------------------------------------------------------------------------
# 페이지 설정 (모든 페이지 공통)
# 사이드바·햄버거 메뉴는 ui.inject_theme()의 CSS로 숨김.
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="공정에너지 — Energy Bill Passport",
    page_icon="⚡",
    layout="centered",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# 외부 접근 인증 게이트
# ---------------------------------------------------------------------------

require_password()


# ---------------------------------------------------------------------------
# 공유 자원
# ---------------------------------------------------------------------------


def _bootstrap_session_state() -> None:
    """페이지를 가로지르는 키를 항상 보장."""
    defaults = {
        "user_id": None,
        "consent_id": None,
        "safety_level": None,
        "safety_response": None,
        "uploaded_documents": [],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource(show_spinner=False)
def _get_app_config() -> config.AppConfig:
    return config.load_config()


@st.cache_resource(show_spinner=False)
def _get_db_connection():
    cfg = _get_app_config()
    return db.init_db(cfg.db_path)


_bootstrap_session_state()
app_config = _get_app_config()
conn = _get_db_connection()


# 데모 모드면 진입 즉시 시드 사용자 자동 주입.
if demo.is_demo_mode():
    demo.ensure_demo_session(conn)


# ---------------------------------------------------------------------------
# 메인 페이지 본문 — UI Chrome 적용
# ---------------------------------------------------------------------------

ui.inject_theme()

# 데모 배너 (해당 시).
if demo.is_demo_mode():
    st.markdown(
        '<div class="demo-banner">'
        "🎬 데모 모드 활성화 — 모든 단계의 예시 데이터가 자동 생성되어 있습니다."
        "</div>",
        unsafe_allow_html=True,
    )

# 메인 헤더 카드.
st.markdown(
    """
    <div style="background:white;border-radius:16px;padding:32px 28px 24px;
                margin-bottom:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
                border:1px solid #E5E8EB;text-align:center;">
        <div style="font-size:42px;margin-bottom:8px;">⚡</div>
        <div style="font-size:26px;font-weight:700;color:#191F28;
                    letter-spacing:-0.02em;margin-bottom:8px;">
            공정에너지
        </div>
        <div style="font-size:15px;color:#4E5968;line-height:1.6;
                    max-width:520px;margin:0 auto;">
            <b>고시원·다세대·반지하</b>에 사는 분이 매달 받는 전기요금이
            <b>한전 공식 요금표대로 정확히 청구된 건지</b>
            본인이 직접 확인할 수 있도록 돕는 서비스입니다.
        </div>
        <div style="margin-top:14px;padding-top:14px;border-top:1px solid #F2F4F6;
                    font-size:13px;color:#8B95A1;">
            ⚖️ 본 서비스는 <b style="color:#3182F6;">법률 자문이 아닙니다</b>.
            임대인의 잘잘못이나 환급 가능성, 분쟁 결과는 판단하지 않습니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 1줄 문제 정의 — 어떤 문제를 해결하나요?
# ---------------------------------------------------------------------------

st.markdown(
    """
    <div style="background:#FFF7E5;border-radius:12px;padding:16px 20px;
                margin-bottom:20px;border-left:4px solid #FFCA28;">
        <div style="font-size:14px;font-weight:700;color:#5D4037;margin-bottom:6px;">
            💡 왜 필요한가요?
        </div>
        <div style="font-size:13px;color:#5D4037;line-height:1.6;">
            한전 명의 계량기 1개로 전기요금을 받은 임대인이
            세대별로 나눠서 청구하는데, <b>그 분배가 맞는지 임차인이 직접 확인할 도구가 지금은 없습니다</b>.
            매달 몇 만원이 잘못 청구돼도 그냥 내야 하는 셈입니다.
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# 두 진입점 — 사용자 vs 심사관·자문위원
# ---------------------------------------------------------------------------

st.markdown(
    "<div style='font-size:13px;color:#8B95A1;margin:8px 4px 12px;font-weight:600;'>"
    "방문 목적을 선택해주세요"
    "</div>",
    unsafe_allow_html=True,
)

entry_cols = st.columns(2)

with entry_cols[0]:
    st.markdown(
        """
        <div style="background:white;border-radius:16px;padding:22px 20px 18px;
                    border:1px solid #E5E8EB;min-height:260px;">
            <div style="font-size:30px;margin-bottom:6px;">🧑‍💼</div>
            <div style="font-size:17px;font-weight:700;color:#191F28;margin-bottom:6px;">
                내 전기요금 확인하기
            </div>
            <div style="font-size:13px;color:#6B7684;line-height:1.6;margin-bottom:12px;">
                고지서·계약서 등을 올리면
                <b>내가 낸 전기요금이 한전 공식 요금표대로</b>
                나온 건지 확인해드립니다.
            </div>
            <div style="font-size:11px;color:#8B95A1;line-height:1.6;">
                ① 간단한 동의·안전 확인<br>
                ② 자료 업로드 (또는 직접 입력)<br>
                ③ 추출값 확인·수정<br>
                ④ 자료 충분도 점수 (100점)<br>
                ⑤ 결과·메시지 예시·PDF<br>
                <br>
                <i>소요: 약 5~10분 · 본인 자료 필요</i>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "🧑‍💼 내 자료로 시작하기 →",
        use_container_width=True,
        type="primary",
        key="cta_user",
    ):
        st.switch_page("pages/1_시작하기.py")

with entry_cols[1]:
    st.markdown(
        """
        <div style="background:linear-gradient(135deg, #F0F6FF 0%, #FFFFFF 100%);
                    border-radius:16px;padding:22px 20px 18px;
                    border:1px solid #C6DAF8;min-height:260px;">
            <div style="font-size:30px;margin-bottom:6px;">🎬</div>
            <div style="font-size:17px;font-weight:700;color:#1B64DA;margin-bottom:6px;">
                심사관·자문위원 둘러보기
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.6;margin-bottom:12px;">
                <b>어떤 자료가 들어가서 어떤 결과가 나오는지</b>
                실제 데이터로 5분 안에 확인합니다.
            </div>
            <div style="font-size:11px;color:#6B7684;line-height:1.6;">
                ① 어떤 문제를 푸나요?<br>
                ② 어떤 자료를 받아 무엇을 하나요?<br>
                ③ 실제 결과 미리보기<br>
                ④ 안전장치 직접 체험<br>
                ⑤ 정책 문서 8종<br>
                <br>
                <i>소요: 약 5분 · 예시 데이터 자동 제공</i>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "🎬 5분 둘러보기 →",
        use_container_width=True,
        type="primary",
        key="cta_review",
    ):
        st.switch_page("pages/0_심사관_둘러보기.py")


# ---------------------------------------------------------------------------
# 페이지 점퍼
# ---------------------------------------------------------------------------

st.markdown("<div style='margin-top:12px;'></div>", unsafe_allow_html=True)
ui.render_page_jumper(current_page_num=0)


# ---------------------------------------------------------------------------
# 한계 사항 (시연용)
# ---------------------------------------------------------------------------

with st.expander("ℹ️ 본 베타 환경의 한계 사항"):
    st.markdown(
        """
        - **시연·자문위원 접근용 환경**입니다. 실제 베타 사용자 모집은 별도 호스팅 예정.
        - Streamlit Cloud 컨테이너는 재시작 시 데이터가 초기화됩니다.
        - 외부 자문(화우·한전·개인정보·NGO) 결과 수령 전 일부 표현·기능은 추정 의견 기반입니다.
        - 자세한 내용은 [GitHub 저장소](https://github.com/dailyweekly/fair-energy)·정책 07 참조.
        """
    )
