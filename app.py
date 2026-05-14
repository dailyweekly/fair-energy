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
                margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,0.04);
                border:1px solid #E5E8EB;text-align:center;">
        <div style="font-size:42px;margin-bottom:8px;">⚡</div>
        <div style="font-size:26px;font-weight:700;color:#191F28;
                    letter-spacing:-0.02em;margin-bottom:6px;">
            공정에너지
        </div>
        <div style="font-size:14px;color:#6B7684;line-height:1.5;">
            Energy Bill Passport · 임차인 전기요금 검산 가능성 진단
        </div>
        <div style="margin-top:12px;font-size:13px;color:#8B95A1;">
            본 서비스는 <b style="color:#3182F6;">법률서비스가 아닙니다</b>.
            임대인의 위법성·환급 가능성·분쟁 결과를 판단하지 않습니다.
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
                    border:1px solid #E5E8EB;min-height:230px;">
            <div style="font-size:30px;margin-bottom:6px;">🧑‍💼</div>
            <div style="font-size:17px;font-weight:700;color:#191F28;margin-bottom:6px;">
                본인 자료로 시작
            </div>
            <div style="font-size:13px;color:#6B7684;line-height:1.6;margin-bottom:12px;">
                실제 임차인이 본인 전기요금 자료를 업로드해
                <b>검산 가능한 상태인지 확인</b>합니다.
            </div>
            <div style="font-size:11px;color:#8B95A1;line-height:1.6;">
                ① 동의·안전체크<br>
                ② 자료 5종 업로드<br>
                ③ 추출값 직접 확인<br>
                ④ 점수·분류·검산<br>
                ⑤ 자료요청 메시지·요약본<br>
                <br>
                <i>소요: 약 5~10분</i>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button(
        "🧑‍💼 사용자로 시작하기 →",
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
                    border:1px solid #C6DAF8;min-height:230px;">
            <div style="font-size:30px;margin-bottom:6px;">🎬</div>
            <div style="font-size:17px;font-weight:700;color:#1B64DA;margin-bottom:6px;">
                심사관·자문위원 둘러보기
            </div>
            <div style="font-size:13px;color:#4E5968;line-height:1.6;margin-bottom:12px;">
                솔루션의 작동·정책 가드레일·결과 화면을
                <b>5분 안에</b> 확인합니다.
            </div>
            <div style="font-size:11px;color:#6B7684;line-height:1.6;">
                ① 한 줄 정체성<br>
                ② 결과 미리보기 (점수·분류)<br>
                ③ 가드레일 라이브 데모<br>
                ④ 정책 8종 카드<br>
                ⑤ 두 여정 비교<br>
                <br>
                <i>소요: 약 5분 · 데모 데이터 자동 제공</i>
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
