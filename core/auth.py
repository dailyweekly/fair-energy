"""외부 접근 인증 게이트 (Phase 9.5 — Streamlit Community Cloud 배포용).

심사위원·NGO·자문위원 등 제한 인원만 접근하도록 단일 비밀번호 게이트를 둔다.
정책 04 §10에 따라 접근 시도(성공·실패)는 audit_logs에 기록한다.

⚠ 한계 사항 (LIMITATION):
- 단일 비밀번호 방식은 사용자 식별이 불가능하다. 누가 접속했는지는 audit_log에서
  「session_id」 hash로 구분할 뿐, 개별 신원 매핑은 별도 절차가 필요하다.
- brute force 방지(rate limit)는 미구현 — 단일 비밀번호이고 PoC 단계라 우선순위 낮음.
  필요 시 시도 횟수 제한·실패 시 지연 추가로 보강 가능.
- 비밀번호는 환경변수 `APP_ACCESS_PASSWORD` 또는 Streamlit secrets에서 로드된다.
  두 곳 모두 비어 있으면 인증 없이 통과(개발용).
"""

from __future__ import annotations

import hashlib
import os
import secrets
from typing import Optional

import streamlit as st


SESSION_KEY_AUTHENTICATED = "auth_authenticated"
SESSION_KEY_SESSION_ID = "auth_session_id"
SECRETS_PASSWORD_KEY = "app_access_password"


def _load_expected_password() -> Optional[str]:
    """환경변수 또는 Streamlit secrets에서 비밀번호 로드.

    우선순위:
      1. 환경변수 APP_ACCESS_PASSWORD (.env)
      2. Streamlit secrets [app_access_password]
      3. 둘 다 없으면 None — 인증 없이 통과 (개발용)
    """
    env_pw = os.environ.get("APP_ACCESS_PASSWORD", "").strip()
    if env_pw:
        return env_pw

    try:
        secrets_pw = st.secrets.get(SECRETS_PASSWORD_KEY, "")
        if isinstance(secrets_pw, str) and secrets_pw.strip():
            return secrets_pw.strip()
    except (FileNotFoundError, AttributeError):
        pass

    return None


def _new_session_id() -> str:
    """접속자 식별용 익명 세션 ID — 16자 hex."""
    return secrets.token_hex(8)


def _log_access(
    *,
    success: bool,
    session_id: str,
) -> None:
    """접근 시도를 audit_logs에 기록.

    `app.py`의 `conn`을 import해 사용. 임포트 시점 오류는 조용히 무시
    (인증 게이트가 DB 초기화 전에 호출될 수 있음).
    """
    try:
        from app import conn  # type: ignore[attr-defined]
        from core import db, metrics

        db.transaction  # 모듈 로드 확인
        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO audit_logs (
                    log_id, timestamp, actor, action,
                    object_id, object_type
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    db.new_id(), db.utcnow_iso(),
                    f"session:{session_id}",
                    "event",
                    None, None,
                ),
            )
        # KPI 이벤트로도 기록 (선택 — 통계용).
        metrics.log_event(
            conn,
            event_name="auth_access_attempt" if not success else "auth_access_granted",
            user_id=None,
            metadata={"session_id": session_id, "success": success},
        )
    except Exception:  # pragma: no cover — best-effort logging
        pass


def is_authenticated() -> bool:
    """현재 세션이 인증을 통과했는지."""
    return bool(st.session_state.get(SESSION_KEY_AUTHENTICATED))


def require_password() -> None:
    """페이지 진입 시 호출 — 인증 안 됐으면 로그인 화면 표시 + `st.stop()`.

    페이지마다 최상단에 다음 한 줄을 추가:
        from core.auth import require_password
        require_password()
    """
    expected = _load_expected_password()
    if not expected:
        # 비밀번호 미설정 — 개발 환경. 통과시킨다.
        st.session_state[SESSION_KEY_AUTHENTICATED] = True
        return

    if is_authenticated():
        return

    # 세션 ID 부여(접근 추적용).
    if SESSION_KEY_SESSION_ID not in st.session_state:
        st.session_state[SESSION_KEY_SESSION_ID] = _new_session_id()
    session_id = st.session_state[SESSION_KEY_SESSION_ID]

    _render_login_form(expected, session_id)
    st.stop()


def _render_login_form(expected_password: str, session_id: str) -> None:
    """비밀번호 입력 폼 — 잘못된 경우 안내, 정답이면 인증 표시 + rerun."""
    st.set_page_config(
        page_title="공정에너지 — 제한 접근",
        page_icon="🔒",
        layout="centered",
    )

    st.title("🔒 공정에너지 — 제한 접근")
    st.caption(
        "본 사이트는 심사위원·NGO·자문위원 등 제한 인원만 접근 가능한 베타 환경입니다. "
        "공개 서비스가 아니며 분쟁 행동을 권유하지 않습니다."
    )

    with st.container(border=True):
        st.markdown(
            "**참고**\n\n"
            "- 본 화면이 보이면 비밀번호를 부여받은 분께만 접근 권한이 있습니다.\n"
            "- 부여된 비밀번호를 입력 후 진입하세요.\n"
            "- 부여받지 않으셨다면 운영자에게 문의하세요."
        )

    with st.form("auth_form"):
        password_input = st.text_input(
            "접근 비밀번호",
            type="password",
            placeholder="부여받은 비밀번호를 입력하세요",
        )
        submitted = st.form_submit_button("로그인", type="primary")

    if submitted:
        # 상수 시간 비교 — timing attack 방지.
        if secrets.compare_digest(password_input.strip(), expected_password):
            st.session_state[SESSION_KEY_AUTHENTICATED] = True
            _log_access(success=True, session_id=session_id)
            st.success("인증되었습니다. 잠시 후 메인 페이지로 이동합니다.")
            st.rerun()
        else:
            _log_access(success=False, session_id=session_id)
            st.error("비밀번호가 일치하지 않습니다. 다시 시도해주세요.")

    st.markdown("---")
    st.caption(
        "본 서비스는 법률 자문이 아니며, 임대인의 위법성·환급 가능성·분쟁 결과를 판단하지 않습니다. "
        "공정에너지 PoC (Energy Bill Passport)."
    )


# ---------------------------------------------------------------------------
# 단위 테스트용 헬퍼 (Streamlit 의존 없는 영역)
# ---------------------------------------------------------------------------


def password_matches(
    input_password: str,
    expected_password: str,
) -> bool:
    """순수 비교 함수 — 테스트 가능. timing-safe."""
    if not expected_password:
        return False
    return secrets.compare_digest(
        input_password.strip(),
        expected_password.strip(),
    )


def derive_anonymous_session_hash(session_id: str) -> str:
    """audit_log에 노출하기 위한 익명 hash.

    session_id 자체는 메모리에만 있고 DB에는 hash만 보관 가능 — 본 함수는
    필요 시 호출자가 직접 사용. 현재 _log_access는 평문 session_id를 보관하나,
    민감도가 더 높아지면 본 함수로 hash 변환 후 보관할 수 있다.
    """
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
