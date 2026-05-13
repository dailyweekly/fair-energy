"""storage 모듈 테스트 — Fernet 암호화·저장·만료 처리."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from core import db, storage


# --- fixture ---

@pytest.fixture
def storage_dirs(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "originals", tmp_path / "masked"


@pytest.fixture
def store(storage_dirs: tuple[Path, Path]) -> storage.DocumentStorage:
    originals, masked = storage_dirs
    key = Fernet.generate_key()
    return storage.DocumentStorage(key=key, originals_dir=originals, masked_dir=masked)


# --- 키 관리 ---

def test_load_existing_key_passes() -> None:
    key = Fernet.generate_key().decode()
    loaded = storage.load_or_generate_key(key, allow_generate=False)
    assert loaded == key.encode()


def test_invalid_key_raises() -> None:
    with pytest.raises(storage.StorageKeyError):
        storage.load_or_generate_key("not-a-fernet-key", allow_generate=False)


def test_missing_key_in_prod_raises() -> None:
    with pytest.raises(storage.StorageKeyError):
        storage.load_or_generate_key(None, allow_generate=False)


def test_missing_key_in_dev_generates() -> None:
    key = storage.load_or_generate_key(None, allow_generate=True)
    # 생성된 키는 Fernet으로 사용 가능해야 한다.
    Fernet(key).encrypt(b"hello")


# --- 저장과 복호화 ---

def test_save_document_creates_encrypted_file(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    payload = b"PDF DOC BYTES"

    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type="electricity_bill",
        original_filename="bill.pdf",
        original_bytes=payload,
        retention_months=6,
    )

    # 파일 존재 + 평문이 아님(암호화됨).
    assert stored.original_path.exists()
    cipher = stored.original_path.read_bytes()
    assert payload not in cipher

    # 해시·크기 정확.
    assert stored.size_bytes == len(payload)

    # 복호화하면 원본과 동일.
    assert store.load_original(stored.original_path) == payload


def test_save_document_registers_row(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type="lease_contract",
        original_filename="lease.docx",
        original_bytes=b"abc",
        retention_months=12,
    )

    row = conn.execute(
        "SELECT * FROM documents WHERE document_id = ?", (stored.document_id,)
    ).fetchone()
    assert row is not None
    assert row["original_path"] == str(stored.original_path)
    assert row["document_type"] == "lease_contract"


def test_save_document_invalid_retention_raises(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    with pytest.raises(ValueError):
        store.save_document(
            conn,
            user_id=user_id,
            document_type="x",
            original_filename="a",
            original_bytes=b"",
            retention_months=24,
        )


def test_load_with_wrong_key_raises(
    conn: sqlite3.Connection, storage_dirs: tuple[Path, Path]
) -> None:
    originals, masked = storage_dirs
    key1 = Fernet.generate_key()
    key2 = Fernet.generate_key()
    store1 = storage.DocumentStorage(key=key1, originals_dir=originals, masked_dir=masked)
    user_id = db.insert_user(conn)
    stored = store1.save_document(
        conn,
        user_id=user_id,
        document_type="x",
        original_filename="a",
        original_bytes=b"secret",
        retention_months=6,
    )

    store2 = storage.DocumentStorage(key=key2, originals_dir=originals, masked_dir=masked)
    with pytest.raises(storage.StorageKeyError):
        store2.load_original(stored.original_path)


# --- 만료 처리 ---

def test_purge_expired_removes_only_past_retention(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    fresh = store.save_document(
        conn,
        user_id=user_id,
        document_type="x",
        original_filename="a",
        original_bytes=b"fresh",
        retention_months=36,
    )
    old = store.save_document(
        conn,
        user_id=user_id,
        document_type="x",
        original_filename="b",
        original_bytes=b"old",
        retention_months=6,
    )

    # `old`의 retention_until을 강제로 과거로 옮긴다.
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    with db.transaction(conn):
        conn.execute(
            "UPDATE documents SET retention_until = ? WHERE document_id = ?",
            (past, old.document_id),
        )

    purged = store.purge_expired(conn)
    assert purged == 1

    # old의 원본 파일은 사라지고, 원본 경로는 NULL.
    assert not old.original_path.exists()
    row = conn.execute(
        "SELECT original_path FROM documents WHERE document_id = ?",
        (old.document_id,),
    ).fetchone()
    assert row["original_path"] is None

    # fresh는 그대로.
    assert fresh.original_path.exists()
