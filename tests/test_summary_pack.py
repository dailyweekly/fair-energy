"""자료 요약본 PDF 생성 테스트 (Phase 9 Round 2)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import fitz
import pytest
from cryptography.fernet import Fernet

from core import db, extraction, scoring, storage, summary_pack
from core.llm_client import DemoLLMClient


@pytest.fixture
def store(tmp_path: Path) -> storage.DocumentStorage:
    return storage.DocumentStorage(
        key=Fernet.generate_key(),
        originals_dir=tmp_path / "originals",
        masked_dir=tmp_path / "masked",
    )


def _setup_user_with_confirmed_data(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
    *, doc_type: str = "electricity_bill",
) -> str:
    user_id = db.insert_user(conn)
    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type=doc_type,
        original_filename=f"{doc_type}.png",
        original_bytes=b"FAKE",
        retention_months=6,
    )
    extraction.extract_and_save(
        conn,
        document_id=stored.document_id,
        document_type=doc_type,
        original_filename=f"{doc_type}.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    field_ids = [
        r["field_id"]
        for r in conn.execute(
            "SELECT field_id FROM extracted_fields WHERE document_id = ?",
            (stored.document_id,),
        )
    ]
    extraction.confirm_fields_bulk(conn, field_ids=field_ids)

    score = scoring.compute_completeness_score(conn, user_id=user_id)
    scoring.save_score_snapshot(conn, user_id=user_id, score=score)
    return user_id


# ---------------------------------------------------------------------------
# PDF 구조
# ---------------------------------------------------------------------------


def test_pdf_is_valid_pdf(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    user_id = _setup_user_with_confirmed_data(conn, store)
    pdf_bytes = summary_pack.build_summary_pdf(conn, user_id=user_id)
    # PDF magic.
    assert pdf_bytes[:5] == b"%PDF-"


def test_pdf_can_be_reopened(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    user_id = _setup_user_with_confirmed_data(conn, store)
    pdf_bytes = summary_pack.build_summary_pdf(conn, user_id=user_id)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        # 표지 + 점수 + 문서 + 푸터 = 최소 4 페이지.
        assert doc.page_count >= 3
    finally:
        doc.close()


def test_pdf_with_no_confirmed_fields_still_renders(
    conn: sqlite3.Connection,
) -> None:
    """확인 필드 없는 사용자도 PDF 생성 — 표지 + 푸터."""
    user_id = db.insert_user(conn)
    pdf_bytes = summary_pack.build_summary_pdf(conn, user_id=user_id)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        assert doc.page_count >= 2  # 표지 + 푸터.
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# 내용 회귀 — 핵심 문구·제목 포함
# ---------------------------------------------------------------------------


def _all_text(pdf_bytes: bytes) -> str:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_pdf_includes_title(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    user_id = _setup_user_with_confirmed_data(conn, store)
    text = _all_text(summary_pack.build_summary_pdf(conn, user_id=user_id))
    assert summary_pack.PDF_TITLE in text


def test_pdf_includes_score_section(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    user_id = _setup_user_with_confirmed_data(conn, store)
    text = _all_text(summary_pack.build_summary_pdf(conn, user_id=user_id))
    assert "자료 완결성 점수" in text
    assert "/ 100" in text


def test_pdf_includes_disclaimer(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    user_id = _setup_user_with_confirmed_data(conn, store)
    text = _all_text(summary_pack.build_summary_pdf(conn, user_id=user_id))
    # 「보관용」·「법률 자문이 아니며」 등 면책 핵심.
    assert "보관용" in text
    assert "법률 자문이 아니" in text


# ---------------------------------------------------------------------------
# 정책 04 §5 — source_text 절대 미포함 (PII 누출 차단)
# ---------------------------------------------------------------------------


def test_pdf_does_not_include_source_text(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    """확장 추출의 source_text는 PDF에 절대 포함되지 않아야 한다."""
    user_id = _setup_user_with_confirmed_data(conn, store)
    source_texts = [
        r["source_text"]
        for r in conn.execute(
            """
            SELECT source_text FROM extracted_fields f
            JOIN documents d ON d.document_id = f.document_id
            WHERE d.user_id = ? AND source_text IS NOT NULL AND source_text != ''
            """,
            (user_id,),
        )
        if r["source_text"]
    ]
    assert source_texts, "fixture에 source_text가 있어야 한다"

    text = _all_text(summary_pack.build_summary_pdf(conn, user_id=user_id))
    for st_quote in source_texts:
        assert st_quote not in text, f"source_text 누출: {st_quote}"


# ---------------------------------------------------------------------------
# 다중 문서 처리
# ---------------------------------------------------------------------------


def test_pdf_with_multiple_documents(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    user_id = db.insert_user(conn)
    for doc_type in ("electricity_bill", "lease_contract"):
        stored = store.save_document(
            conn, user_id=user_id, document_type=doc_type,
            original_filename=f"{doc_type}.png",
            original_bytes=b"FAKE", retention_months=6,
        )
        extraction.extract_and_save(
            conn, document_id=stored.document_id,
            document_type=doc_type, original_filename=f"{doc_type}.png",
            document_bytes=b"FAKE", llm_client=DemoLLMClient(),
        )
        rows = conn.execute(
            "SELECT field_id FROM extracted_fields WHERE document_id = ?",
            (stored.document_id,),
        ).fetchall()
        extraction.confirm_fields_bulk(
            conn, field_ids=[r["field_id"] for r in rows],
        )

    pdf_bytes = summary_pack.build_summary_pdf(conn, user_id=user_id)
    text = _all_text(pdf_bytes)
    assert "electricity_bill" in text
    assert "lease_contract" in text


def test_pdf_skips_unconfirmed_documents(
    conn: sqlite3.Connection, store: storage.DocumentStorage,
) -> None:
    """확인되지 않은 문서는 PDF에서 제외."""
    user_id = db.insert_user(conn)
    # 문서 1: 모두 확인.
    stored1 = store.save_document(
        conn, user_id=user_id, document_type="electricity_bill",
        original_filename="confirmed.png",
        original_bytes=b"FAKE", retention_months=6,
    )
    extraction.extract_and_save(
        conn, document_id=stored1.document_id,
        document_type="electricity_bill",
        original_filename="confirmed.png",
        document_bytes=b"FAKE", llm_client=DemoLLMClient(),
    )
    rows = conn.execute(
        "SELECT field_id FROM extracted_fields WHERE document_id = ?",
        (stored1.document_id,),
    ).fetchall()
    extraction.confirm_fields_bulk(
        conn, field_ids=[r["field_id"] for r in rows],
    )

    # 문서 2: 확인 안 함.
    store.save_document(
        conn, user_id=user_id, document_type="meter_photo",
        original_filename="unconfirmed.png",
        original_bytes=b"FAKE", retention_months=6,
    )

    text = _all_text(summary_pack.build_summary_pdf(conn, user_id=user_id))
    assert "confirmed.png" in text
    assert "unconfirmed.png" not in text


# ---------------------------------------------------------------------------
# 파일명
# ---------------------------------------------------------------------------


def test_suggested_filename_format() -> None:
    name = summary_pack.suggested_filename("abcdef1234567890")
    assert name.startswith("energy_bill_summary_abcdef12_")
    assert name.endswith(".pdf")
