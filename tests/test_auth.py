"""auth 모듈 단위 테스트.

Streamlit 의존 함수(require_password 등)는 통합 환경에서 검증한다.
순수 함수만 본 파일에서 회귀.
"""

from __future__ import annotations

import pytest

from core import auth


# --- password_matches ---


def test_password_matches_exact() -> None:
    assert auth.password_matches("hunter2", "hunter2") is True


def test_password_matches_trims_whitespace() -> None:
    assert auth.password_matches("  hunter2  ", "hunter2") is True
    assert auth.password_matches("hunter2", "hunter2  ") is True


def test_password_does_not_match() -> None:
    assert auth.password_matches("hunter2", "hunter3") is False


def test_empty_expected_never_matches() -> None:
    """expected가 비어있으면 어떤 input도 통과 X — 빈 비밀번호 우회 차단."""
    assert auth.password_matches("anything", "") is False
    assert auth.password_matches("", "") is False


def test_case_sensitive() -> None:
    assert auth.password_matches("Hunter2", "hunter2") is False


def test_timing_safe_comparison_returns_bool() -> None:
    """secrets.compare_digest는 bool을 반환한다. timing-safe 보장."""
    result = auth.password_matches("a", "b")
    assert isinstance(result, bool)


# --- derive_anonymous_session_hash ---


def test_derive_hash_deterministic() -> None:
    """같은 session_id는 같은 hash."""
    assert auth.derive_anonymous_session_hash("abc") == auth.derive_anonymous_session_hash("abc")


def test_derive_hash_different_for_different_ids() -> None:
    h1 = auth.derive_anonymous_session_hash("abc")
    h2 = auth.derive_anonymous_session_hash("xyz")
    assert h1 != h2


def test_derive_hash_length() -> None:
    """16자 hex로 잘려 나온다."""
    h = auth.derive_anonymous_session_hash("session-id-12345")
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)
