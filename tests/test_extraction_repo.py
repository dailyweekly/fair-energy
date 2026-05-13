"""Phase 4 추출 결과 저장소 헬퍼 테스트.

list/find/update/confirm/auto-extract 회귀를 검증한다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from core import db, extraction, storage
from core.llm_client import DemoLLMClient


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> storage.DocumentStorage:
    return storage.DocumentStorage(
        key=Fernet.generate_key(),
        originals_dir=tmp_path / "originals",
        masked_dir=tmp_path / "masked",
    )


def _upload(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    user_id: str,
    *,
    doc_type: str = "electricity_bill",
    filename: str = "bill.png",
    payload: bytes = b"FAKE PAYLOAD",
) -> str:
    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type=doc_type,
        original_filename=filename,
        original_bytes=payload,
        retention_months=6,
    )
    return stored.document_id


# ---------------------------------------------------------------------------
# list_user_documents_with_fields
# ---------------------------------------------------------------------------


def test_list_returns_empty_when_no_documents(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    assert extraction.list_user_documents_with_fields(conn, user_id=user_id) == []


def test_list_returns_docs_with_their_fields(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    doc_id = _upload(conn, store, user_id)

    # 추출 실행.
    extraction.auto_extract_pending(
        conn, user_id=user_id,
        llm_client=DemoLLMClient(), storage=store,
    )

    result = extraction.list_user_documents_with_fields(conn, user_id=user_id)
    assert len(result) == 1
    entry = result[0]
    assert entry["document"]["document_id"] == doc_id
    assert len(entry["fields"]) > 0
    # 모든 필드는 미확인 상태로 시작.
    assert all(f["user_confirmed"] == 0 for f in entry["fields"])


# ---------------------------------------------------------------------------
# find_documents_pending_extraction
# ---------------------------------------------------------------------------


def test_pending_returns_only_unextracted(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    doc1 = _upload(conn, store, user_id, filename="a.png")
    doc2 = _upload(conn, store, user_id, filename="b.png")

    # doc1만 추출.
    extraction.extract_and_save(
        conn,
        document_id=doc1,
        document_type="electricity_bill",
        original_filename="a.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )

    pending = extraction.find_documents_pending_extraction(conn, user_id=user_id)
    pending_ids = {row["document_id"] for row in pending}
    assert pending_ids == {doc2}


def test_pending_excludes_purged_documents(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    doc_id = _upload(conn, store, user_id)
    # 강제로 파기 상태.
    with db.transaction(conn):
        conn.execute(
            "UPDATE documents SET original_path = NULL, purged_at = ? "
            "WHERE document_id = ?",
            (db.utcnow_iso(), doc_id),
        )

    assert extraction.find_documents_pending_extraction(
        conn, user_id=user_id
    ) == []


# ---------------------------------------------------------------------------
# update_field_value / confirm_field
# ---------------------------------------------------------------------------


def _extract_one(
    conn: sqlite3.Connection, store: storage.DocumentStorage, user_id: str
) -> list[sqlite3.Row]:
    _upload(conn, store, user_id)
    extraction.auto_extract_pending(
        conn, user_id=user_id,
        llm_client=DemoLLMClient(), storage=store,
    )
    return conn.execute(
        "SELECT f.* FROM extracted_fields f "
        "JOIN documents d ON d.document_id = f.document_id "
        "WHERE d.user_id = ?",
        (user_id,),
    ).fetchall()


def test_update_field_value_changes_value(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    fields = _extract_one(conn, store, user_id)
    target = fields[0]

    extraction.update_field_value(
        conn, field_id=target["field_id"], value="MODIFIED"
    )

    after = conn.execute(
        "SELECT value, user_confirmed FROM extracted_fields WHERE field_id = ?",
        (target["field_id"],),
    ).fetchone()
    assert after["value"] == "MODIFIED"
    # 값 수정만으로는 user_confirmed가 자동 변경되지 않는다.
    assert after["user_confirmed"] == 0


def test_confirm_field_flips_flag(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    fields = _extract_one(conn, store, user_id)
    target = fields[0]

    extraction.confirm_field(conn, field_id=target["field_id"], confirmed=True)
    row = conn.execute(
        "SELECT user_confirmed FROM extracted_fields WHERE field_id = ?",
        (target["field_id"],),
    ).fetchone()
    assert row["user_confirmed"] == 1

    # 해제도 가능.
    extraction.confirm_field(conn, field_id=target["field_id"], confirmed=False)
    row = conn.execute(
        "SELECT user_confirmed FROM extracted_fields WHERE field_id = ?",
        (target["field_id"],),
    ).fetchone()
    assert row["user_confirmed"] == 0


def test_confirm_bulk_affects_multiple(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    fields = _extract_one(conn, store, user_id)
    ids = [f["field_id"] for f in fields]

    affected = extraction.confirm_fields_bulk(
        conn, field_ids=ids, confirmed=True
    )
    assert affected == len(ids)

    confirmed = conn.execute(
        "SELECT COUNT(*) AS c FROM extracted_fields "
        "WHERE field_id IN (" + ",".join("?" * len(ids)) + ") AND user_confirmed = 1",
        ids,
    ).fetchone()["c"]
    assert confirmed == len(ids)


def test_confirm_bulk_with_empty_list_is_noop(conn: sqlite3.Connection) -> None:
    assert extraction.confirm_fields_bulk(conn, field_ids=[]) == 0


# ---------------------------------------------------------------------------
# auto_extract_pending
# ---------------------------------------------------------------------------


def test_auto_extract_processes_all_pending(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    _upload(conn, store, user_id, filename="a.png", doc_type="electricity_bill")
    _upload(conn, store, user_id, filename="b.png", doc_type="lease_contract")

    count = extraction.auto_extract_pending(
        conn, user_id=user_id,
        llm_client=DemoLLMClient(), storage=store,
    )
    assert count == 2

    # 두 번 호출해도 새로 처리되는 문서는 없다(idempotent).
    count2 = extraction.auto_extract_pending(
        conn, user_id=user_id,
        llm_client=DemoLLMClient(), storage=store,
    )
    assert count2 == 0


def test_auto_extract_skips_missing_files(
    conn: sqlite3.Connection, store: storage.DocumentStorage, tmp_path: Path
) -> None:
    user_id = db.insert_user(conn)
    doc_id = _upload(conn, store, user_id)
    # 디스크에서 파일만 삭제하고 DB는 그대로.
    row = conn.execute(
        "SELECT original_path FROM documents WHERE document_id = ?",
        (doc_id,),
    ).fetchone()
    Path(row["original_path"]).unlink()

    count = extraction.auto_extract_pending(
        conn, user_id=user_id,
        llm_client=DemoLLMClient(), storage=store,
    )
    assert count == 0  # 파일 없으니 건너뜀.


# ---------------------------------------------------------------------------
# confirmation_status
# ---------------------------------------------------------------------------


def test_status_reflects_progress(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    fields = _extract_one(conn, store, user_id)

    before = extraction.confirmation_status(conn, user_id=user_id)
    assert before["total"] == len(fields)
    assert before["confirmed"] == 0
    assert before["all_confirmed"] is False

    # 절반 확인.
    half = [f["field_id"] for f in fields[: len(fields) // 2]]
    extraction.confirm_fields_bulk(conn, field_ids=half, confirmed=True)

    mid = extraction.confirmation_status(conn, user_id=user_id)
    assert mid["confirmed"] == len(half)
    assert mid["all_confirmed"] is False

    # 전체 확인.
    extraction.confirm_fields_bulk(
        conn, field_ids=[f["field_id"] for f in fields], confirmed=True
    )
    full = extraction.confirmation_status(conn, user_id=user_id)
    assert full["all_confirmed"] is True


def test_status_counts_low_confidence(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    _upload(conn, store, user_id, doc_type="meter_photo", filename="m.jpg")
    extraction.auto_extract_pending(
        conn, user_id=user_id,
        llm_client=DemoLLMClient(), storage=store,
    )
    status = extraction.confirmation_status(conn, user_id=user_id)
    # meter_photo 데모 fixture에는 0.65, 0.72 등 저신뢰도 필드가 있다.
    assert status["low_confidence"] >= 1
