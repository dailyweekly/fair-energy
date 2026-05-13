"""extraction 모듈 통합 테스트.

데모 클라이언트를 사용해 추출→스키마 검증→DB 저장 전 파이프라인을 검증한다.
정책 02 §5의 user_confirmed=False invariant를 회귀 차단한다.
"""

from __future__ import annotations

import sqlite3

import pytest

from core import db, extraction
from core.llm_client import DemoLLMClient
from core.models import DocumentType


def test_extract_returns_extracted_document() -> None:
    document = extraction.extract_document(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    assert document.document_id == "doc-1"
    assert document.document_type == DocumentType.ELECTRICITY_BILL
    assert len(document.extracted_fields) > 0


def test_all_fields_start_unconfirmed() -> None:
    """정책 02 §5: AI 추출값은 user_confirmed=False로 저장되어야 한다."""
    document = extraction.extract_document(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    assert all(not f.user_confirmed for f in document.extracted_fields)


def test_low_confidence_forces_user_confirmation() -> None:
    """confidence < 0.7면 needs_user_confirmation을 True로 강제."""
    document = extraction.extract_document(
        document_id="doc-1",
        document_type="meter_photo",  # demo fixture에 0.65 confidence 필드 포함
        original_filename="meter.jpg",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    low_confidence_fields = [
        f for f in document.extracted_fields if f.confidence < 0.7
    ]
    assert low_confidence_fields, "fixture에 저신뢰도 필드가 있어야 한다"
    assert all(f.needs_user_confirmation for f in low_confidence_fields)


def test_mime_type_inferred_from_filename() -> None:
    """다양한 확장자에 대해 LLM 호출이 깨지지 않아야 한다."""
    for fname in ["bill.pdf", "meter.jpg", "lease.docx", "note.png"]:
        document = extraction.extract_document(
            document_id="doc-1",
            document_type="electricity_bill",
            original_filename=fname,
            document_bytes=b"FAKE",
            llm_client=DemoLLMClient(),
        )
        assert document is not None


def test_save_extracted_fields_writes_unconfirmed_rows(
    conn: sqlite3.Connection,
) -> None:
    user_id = db.insert_user(conn)
    retention = db.utcnow_iso()
    now = db.utcnow_iso()
    doc_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO documents (document_id, user_id, document_type, "
            "original_filename, original_path, retention_until, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, "electricity_bill", "bill.png",
             "/storage/originals/x.bin", retention, now, now),
        )

    document = extraction.extract_document(
        document_id=doc_id,
        document_type="electricity_bill",
        original_filename="bill.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    inserted_ids = extraction.save_extracted_fields(conn, document=document)
    assert len(inserted_ids) == len(document.extracted_fields)

    rows = conn.execute(
        "SELECT user_confirmed FROM extracted_fields WHERE document_id = ?",
        (doc_id,),
    ).fetchall()
    assert rows, "필드가 저장되어야 한다"
    assert all(row["user_confirmed"] == 0 for row in rows)


def test_extract_and_save_round_trip(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    retention = db.utcnow_iso()
    now = db.utcnow_iso()
    doc_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            "INSERT INTO documents (document_id, user_id, document_type, "
            "original_filename, original_path, retention_until, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (doc_id, user_id, "lease_contract", "lease.png",
             "/storage/originals/x.bin", retention, now, now),
        )

    document, inserted_ids = extraction.extract_and_save(
        conn,
        document_id=doc_id,
        document_type="lease_contract",
        original_filename="lease.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    assert document.document_type == DocumentType.LEASE_CONTRACT
    assert len(inserted_ids) > 0


def test_extracted_field_confidence_preserved() -> None:
    document = extraction.extract_document(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    usage = next(f for f in document.extracted_fields if f.key == "usage_kwh")
    assert 0.0 <= usage.confidence <= 1.0
