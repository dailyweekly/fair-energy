"""SQLite 스키마와 INSERT 헬퍼 테스트.

정책 04 §5의 원본/마스킹 경로 분리, §6의 보관기간을 회귀 검증한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core import db


# --- 초기화 ---

def test_init_creates_all_tables(conn: sqlite3.Connection) -> None:
    tables = set(db.list_tables(conn))
    assert set(db.TABLE_NAMES).issubset(tables)


def test_init_db_is_idempotent(db_path) -> None:
    """동일 경로에 두 번 init 해도 예외 없이 통과한다."""
    db.init_db(db_path).close()
    conn2 = db.init_db(db_path)
    try:
        assert set(db.TABLE_NAMES).issubset(set(db.list_tables(conn2)))
    finally:
        conn2.close()


def test_foreign_keys_enabled(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA foreign_keys")
    assert cur.fetchone()[0] == 1


# --- users ---

def test_insert_user_returns_uuid(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn, cohort="ngo")
    row = conn.execute(
        "SELECT user_id, cohort, locale FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    assert row is not None
    assert row["cohort"] == "ngo"
    assert row["locale"] == "ko"


def test_user_cohort_constraint(conn: sqlite3.Connection) -> None:
    """cohort는 ngo/general/admin 중 하나만 허용."""
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_user(conn, cohort="random_value")


# --- consents ---

def test_insert_consent_links_to_user(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    consent_id = db.insert_consent(
        conn,
        user_id=user_id,
        consent_service=True,
        consent_personal_info=True,
        consent_ai_processing=True,
        consent_storage_months=12,
        consent_ngo_share=True,
    )
    row = conn.execute(
        "SELECT user_id, consent_storage_months, consent_ngo_share "
        "FROM consents WHERE consent_id = ?",
        (consent_id,),
    ).fetchone()
    assert row["user_id"] == user_id
    assert row["consent_storage_months"] == 12
    assert row["consent_ngo_share"] == 1


def test_storage_months_must_be_valid(conn: sqlite3.Connection) -> None:
    """보관기간은 6/12/36 중 하나만 허용 (정책 04 §6)."""
    user_id = db.insert_user(conn)
    with pytest.raises(ValueError):
        db.insert_consent(
            conn,
            user_id=user_id,
            consent_service=True,
            consent_personal_info=True,
            consent_ai_processing=True,
            consent_storage_months=24,  # 허용 외 값
        )


def test_consent_storage_months_db_constraint(conn: sqlite3.Connection) -> None:
    """CHECK 제약이 DB 레벨에서도 동작하는지."""
    user_id = db.insert_user(conn)
    now = db.utcnow_iso()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO consents (consent_id, user_id, consent_service, "
            "consent_personal_info, consent_ai_processing, consent_storage_months, "
            "created_at) VALUES (?, ?, 1, 1, 1, 99, ?)",
            (db.new_id(), user_id, now),
        )


# --- documents: 원본/마스킹 경로 분리 ---

def test_documents_separate_original_and_masked_paths(
    conn: sqlite3.Connection,
) -> None:
    """정책 04 §1: 원본과 표시용 사본을 분리 저장."""
    user_id = db.insert_user(conn)
    retention = (datetime.now(timezone.utc) + timedelta(days=180)).isoformat()
    doc_id = db.new_id()
    now = db.utcnow_iso()

    with db.transaction(conn):
        conn.execute(
            "INSERT INTO documents (document_id, user_id, document_type, "
            "original_filename, original_path, masked_path, retention_until, "
            "created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, "electricity_bill", "bill.pdf",
             "/storage/originals/abc.bin", "/storage/masked/abc.pdf",
             retention, now, now),
        )

    row = conn.execute(
        "SELECT original_path, masked_path FROM documents WHERE document_id = ?",
        (doc_id,),
    ).fetchone()
    assert row["original_path"] != row["masked_path"]
    assert "originals" in row["original_path"]
    assert "masked" in row["masked_path"]


def test_documents_user_fk_cascade(conn: sqlite3.Connection) -> None:
    """user 삭제 시 documents도 함께 삭제(CASCADE)."""
    user_id = db.insert_user(conn)
    retention = db.utcnow_iso()
    now = db.utcnow_iso()
    doc_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO documents (document_id, user_id, document_type, "
            "original_filename, original_path, retention_until, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, "lease_contract", "lease.pdf",
             "/storage/originals/x.bin", retention, now, now),
        )

    with db.transaction(conn):
        conn.execute("DELETE FROM users WHERE user_id = ?", (user_id,))

    row = conn.execute(
        "SELECT 1 FROM documents WHERE document_id = ?", (doc_id,)
    ).fetchone()
    assert row is None


# --- extracted_fields: user_confirmed 게이트 ---

def test_extracted_field_defaults_to_unconfirmed(conn: sqlite3.Connection) -> None:
    """정책 02 §5: AI 추출값은 기본적으로 미확인 상태로 저장."""
    user_id = db.insert_user(conn)
    retention = db.utcnow_iso()
    now = db.utcnow_iso()
    doc_id = db.new_id()
    field_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO documents (document_id, user_id, document_type, "
            "original_filename, original_path, retention_until, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, "electricity_bill", "bill.pdf",
             "/storage/originals/x.bin", retention, now, now),
        )
        conn.execute(
            "INSERT INTO extracted_fields (field_id, document_id, key, label, "
            "value, confidence, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (field_id, doc_id, "usage_kwh", "사용량", "245", 0.9, now, now),
        )

    row = conn.execute(
        "SELECT user_confirmed, needs_user_confirmation "
        "FROM extracted_fields WHERE field_id = ?",
        (field_id,),
    ).fetchone()
    assert row["user_confirmed"] == 0
    assert row["needs_user_confirmation"] == 1


def test_confidence_constraint(conn: sqlite3.Connection) -> None:
    """confidence는 [0,1] 범위 강제."""
    user_id = db.insert_user(conn)
    retention = db.utcnow_iso()
    now = db.utcnow_iso()
    doc_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO documents (document_id, user_id, document_type, "
            "original_filename, original_path, retention_until, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, "electricity_bill", "bill.pdf",
             "/storage/originals/x.bin", retention, now, now),
        )

    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO extracted_fields (field_id, document_id, key, "
                "label, confidence, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (db.new_id(), doc_id, "usage_kwh", "사용량", 1.5, now, now),
            )


# --- passport_scores ---

def test_score_range_constraint(conn: sqlite3.Connection) -> None:
    """total_score는 0~100 범위 강제."""
    user_id = db.insert_user(conn)
    now = db.utcnow_iso()
    with pytest.raises(sqlite3.IntegrityError):
        with db.transaction(conn):
            conn.execute(
                "INSERT INTO passport_scores (score_id, user_id, total_score, "
                "created_at) VALUES (?, ?, ?, ?)",
                (db.new_id(), user_id, 150, now),
            )
