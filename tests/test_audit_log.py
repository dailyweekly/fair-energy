"""audit_log 테스트 — 정책 04 §10의 접근 로그 무결성을 회귀 검증."""

from __future__ import annotations

import sqlite3

import pytest

from core import audit_log, db


def _make_user(conn: sqlite3.Connection) -> str:
    return db.insert_user(conn)


def test_log_basic_event(conn: sqlite3.Connection) -> None:
    user_id = _make_user(conn)
    log_id = audit_log.log_audit(
        conn,
        actor=user_id,
        action="upload",
        object_id="doc-123",
        object_type="document",
    )
    rows = audit_log.recent_logs(conn, actor=user_id)
    assert len(rows) == 1
    assert rows[0]["log_id"] == log_id
    assert rows[0]["action"] == "upload"
    assert rows[0]["object_type"] == "document"


def test_original_access_requires_consent_basis(conn: sqlite3.Connection) -> None:
    """원본 접근은 consent_basis 없이는 막혀야 한다 (정책 04 §10)."""
    user_id = _make_user(conn)
    with pytest.raises(audit_log.ConsentRequiredError):
        audit_log.log_audit(
            conn,
            actor=user_id,
            action="view",
            object_id="doc-123",
            object_type="original",  # consent_basis 누락
        )


def test_original_access_with_consent_basis_allowed(conn: sqlite3.Connection) -> None:
    user_id = _make_user(conn)
    consent_id = db.insert_consent(
        conn,
        user_id=user_id,
        consent_service=True,
        consent_personal_info=True,
        consent_ai_processing=True,
        consent_storage_months=6,
    )
    log_id = audit_log.log_audit(
        conn,
        actor=user_id,
        action="view",
        object_id="doc-123",
        object_type="original",
        consent_basis=consent_id,
    )
    row = conn.execute(
        "SELECT consent_basis FROM audit_logs WHERE log_id = ?", (log_id,)
    ).fetchone()
    assert row["consent_basis"] == consent_id


def test_masked_access_does_not_require_consent(conn: sqlite3.Connection) -> None:
    """마스킹본 접근은 consent_basis 없이도 가능."""
    user_id = _make_user(conn)
    audit_log.log_audit(
        conn,
        actor=user_id,
        action="view",
        object_id="doc-123",
        object_type="masked",
    )
    assert len(audit_log.recent_logs(conn, actor=user_id)) == 1


def test_invalid_action_rejected_by_db(conn: sqlite3.Connection) -> None:
    """audit_logs.action CHECK 제약."""
    user_id = _make_user(conn)
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO audit_logs (log_id, timestamp, actor, action) "
                "VALUES (?, ?, ?, ?)",
                (db.new_id(), db.utcnow_iso(), user_id, "bogus_action"),
            )


def test_recent_logs_ordering(conn: sqlite3.Connection) -> None:
    """recent_logs는 최신 timestamp 순서."""
    user_id = _make_user(conn)
    audit_log.log_audit(conn, actor=user_id, action="upload", object_id="a")
    audit_log.log_audit(conn, actor=user_id, action="view",
                        object_id="a", object_type="masked")
    rows = audit_log.recent_logs(conn, actor=user_id, limit=10)
    assert len(rows) == 2
    # 가장 최근 항목이 첫 번째.
    assert rows[0]["action"] == "view"
    assert rows[1]["action"] == "upload"
