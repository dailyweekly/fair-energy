"""공정에너지 Streamlit 진입점.

모든 페이지가 공유하는 세션 상태·DB 연결·면책 문구를 정의한다.
"""

from __future__ import annotations

import streamlit as st

from core import config, db
from core.auth import require_password
from core.guardrails import assert_safe_output
from core.safety import DEFAULT_DISCLAIMER


# ---------------------------------------------------------------------------
# 외부 접근 인증 게이트 (Streamlit Community Cloud 배포 시 활성화)
# 환경변수 APP_ACCESS_PASSWORD 또는 secrets.toml의 app_access_password 사용.
# 둘 다 비어 있으면 인증 없이 통과 (로컬 개발).
# ---------------------------------------------------------------------------

require_password()


# ---------------------------------------------------------------------------
# 페이지 설정
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="공정에너지 — Energy Bill Passport",
    page_icon="⚡",
    layout="centered",
)


# ---------------------------------------------------------------------------
# 공유 세션 상태 초기화
# ---------------------------------------------------------------------------


def _bootstrap_session_state() -> None:
    """페이지를 가로지르는 키를 항상 보장한다."""
    defaults = {
        "user_id": None,
        "consent_id": None,
        "safety_level": None,
        "safety_response": None,
        "uploaded_documents": [],  # list of document_id
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


@st.cache_resource
def _get_app_config() -> config.AppConfig:
    return config.load_config()


@st.cache_resource
def _get_db_connection():
    cfg = _get_app_config()
    return db.init_db(cfg.db_path)


# Streamlit 컨텍스트가 없는 환경(테스트 import 등)에서도 안전하도록 try.
try:
    _bootstrap_session_state()
    app_config = _get_app_config()
    conn = _get_db_connection()
except Exception:  # pragma: no cover — 런타임에 다시 시도된다
    pass


# ---------------------------------------------------------------------------
# 메인 페이지 본문
# ---------------------------------------------------------------------------

st.title("공정에너지")
st.caption("Energy Bill Passport — 임차인의 에너지 청구 자료 검산 가능성 진단 도구")

st.markdown(
    """
**공정에너지는 법률서비스가 아닙니다.**

공정에너지는 임차인의 에너지 청구 자료가 검산 가능한 상태인지 진단하고,
공식 요금 산식과 비교 가능한 경우에만 계산 근거를 제공하는 도구입니다.

- 임대인의 위법성 여부, 환급 가능성, 분쟁 결과를 판단하지 않습니다.
- 소장·내용증명·민원 본문을 작성하지 않습니다.
- 모든 결과는 산식 차이·근거 부족·확인 요망 등 중립 표현으로만 제공됩니다.
"""
)

# 면책 문구가 정책 01 통과인지 확인.
assert_safe_output("산식 차이·근거 부족·확인 요망")

st.info(
    "왼쪽 사이드바의 페이지 순서대로 진행하세요.\n\n"
    "1. 시작하기 → 2. 동의 및 안전체크 → 3. 문서 업로드 → 이후 자동 진행"
)

with st.expander("법적 면책 (필독)"):
    st.markdown(DEFAULT_DISCLAIMER)

# Demo 경고.
try:
    if app_config.demo_mode:
        st.warning(
            "현재 DEMO_MODE=true 상태입니다. "
            "실제 한전 요금표가 아닌 데모 요금표가 사용되며, "
            "결과는 분쟁 근거로 사용할 수 없습니다."
        )
except NameError:
    pass
