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
        "🎬 데모 모드 활성화 — 모든 단계의 예시 데이터가 자동 생성되어 있습니다. "
        "어느 페이지든 자유롭게 둘러보세요."
        "</div>",
        unsafe_allow_html=True,
    )

# 메인 헤더 카드.
st.markdown(
    """
    <div style="background:white;border-radius:16px;padding:32px 28px;
                margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
                border:1px solid #E5E8EB;text-align:center;">
        <div style="font-size:42px;margin-bottom:8px;">⚡</div>
        <div style="font-size:26px;font-weight:700;color:#191F28;
                    letter-spacing:-0.02em;margin-bottom:6px;">
            공정에너지
        </div>
        <div style="font-size:14px;color:#6B7684;">
            Energy Bill Passport · 임차인 전기요금 검산 가능성 진단
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# 정체성 선언 카드.
st.markdown(
    """
    <div style="background:white;border-radius:16px;padding:24px;
                margin-bottom:12px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
                border:1px solid #E5E8EB;">
        <div style="font-size:16px;font-weight:700;color:#191F28;margin-bottom:10px;">
            본 서비스는 법률서비스가 아닙니다
        </div>
        <div style="font-size:14px;color:#4E5968;line-height:1.65;">
            임차인의 에너지 청구 자료가 검산 가능한 상태인지 진단하고,
            공식 요금 산식과 비교 가능한 경우에만 계산 근거를 제공하는 도구입니다.
            <br><br>
            <span style="color:#8B95A1;">
                ・ 임대인의 위법성 여부·환급 가능성·분쟁 결과를 판단하지 않습니다<br>
                ・ 소장·내용증명·민원 본문을 작성하지 않습니다<br>
                ・ 모든 결과는 산식 차이·근거 부족·확인 요망 등 중립 표현만 사용합니다
            </span>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# CTA 카드.
st.markdown("<div style='margin:20px 0 8px;'></div>", unsafe_allow_html=True)

cta_cols = st.columns([1, 1])
with cta_cols[0]:
    if st.button("🚀 시작하기", use_container_width=True, type="primary"):
        st.switch_page("pages/1_시작하기.py")
with cta_cols[1]:
    if st.button("📋 단계별 둘러보기", use_container_width=True, type="secondary"):
        st.switch_page("pages/5_자료완결성점수.py")


# 페이지 점퍼 (전체 페이지 이동).
ui.render_page_jumper(current_page_num=0)

# 데모 안내 (해당 시 강조).
if demo.is_demo_mode():
    st.info(
        "🎬 **데모 모드 안내** — "
        "이미 5종 자료가 모두 업로드·확인되어 있고, 점수가 100점인 가짜 사용자로 진입 중입니다. "
        "어느 페이지로 이동해도 결과 화면을 바로 볼 수 있습니다."
    )

# DEMO_MODE 사용자 안내 (시연용).
with st.expander("ℹ️ 본 베타 환경의 한계 사항"):
    st.markdown(
        """
        - **시연·자문위원 접근용 환경**입니다. 실제 베타 사용자 모집은 별도 호스팅 예정.
        - Streamlit Cloud 컨테이너는 재시작 시 데이터가 초기화됩니다.
        - 외부 자문(화우·한전·NGO) 결과 수령 전 일부 표현·기능은 추정 의견 기반입니다.
        - 자세한 내용은 [GitHub repo](https://github.com/dailyweekly/fair-energy)·정책 07 참조.
        """
    )
