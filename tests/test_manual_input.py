"""수동 입력 모드 테스트 (Phase 8 Round 2).

`create_manual_document`가 user_confirmed=True 필드를 생성하고,
원본 경로 없이 점수·분류·TariffInput 빌더와 자연스럽게 연동되는지 검증한다.
"""

from __future__ import annotations

import sqlite3

import pytest

from core import classification, db, extraction, scoring
from core.models import CaseClassification, DocumentType


# --- 기본 동작 ---

def test_creates_document_with_null_original_path(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    document_id, field_ids = extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={"usage_kwh": "245"},
    )
    assert document_id
    assert len(field_ids) == 1

    row = conn.execute(
        "SELECT original_path, original_filename FROM documents WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    assert row["original_path"] is None
    assert row["original_filename"] == extraction.MANUAL_INPUT_FILENAME


def test_fields_default_to_confirmed(conn: sqlite3.Connection) -> None:
    """수동 입력 필드는 user_confirmed=1, confidence=1.0으로 저장된다."""
    user_id = db.insert_user(conn)
    _, field_ids = extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={"usage_kwh": "245", "total_amount": "38000"},
    )
    rows = conn.execute(
        "SELECT user_confirmed, confidence "
        "FROM extracted_fields WHERE field_id IN (?, ?)",
        tuple(field_ids),
    ).fetchall()
    for r in rows:
        assert r["user_confirmed"] == 1
        assert r["confidence"] == 1.0


def test_empty_values_skipped(conn: sqlite3.Connection) -> None:
    """빈 문자열·None 값은 필드로 저장되지 않는다."""
    user_id = db.insert_user(conn)
    _, field_ids = extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={
            "usage_kwh": "245",
            "billing_start_date": "",      # skip
            "billing_end_date": None,      # skip
            "total_amount": "38000",
        },
    )
    assert len(field_ids) == 2  # usage_kwh + total_amount


def test_labels_and_units_applied(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    _, _ = extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={"usage_kwh": "245"},
        field_labels={"usage_kwh": "사용량"},
        field_units={"usage_kwh": "kWh"},
    )
    row = conn.execute(
        "SELECT label, unit FROM extracted_fields LIMIT 1"
    ).fetchone()
    assert row["label"] == "사용량"
    assert row["unit"] == "kWh"


def test_no_fields_raises(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    with pytest.raises(ValueError):
        extraction.create_manual_document(
            conn,
            user_id=user_id,
            document_type=DocumentType.ELECTRICITY_BILL.value,
            fields={},
        )


def test_invalid_retention_raises(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    with pytest.raises(ValueError):
        extraction.create_manual_document(
            conn,
            user_id=user_id,
            document_type=DocumentType.ELECTRICITY_BILL.value,
            fields={"usage_kwh": "245"},
            retention_months=24,
        )


# --- scoring·classification 통합 ---

def test_manual_input_feeds_tariff_input(conn: sqlite3.Connection) -> None:
    user_id = db.insert_user(conn)
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={
            "usage_kwh": "245",
            "billing_start_date": "2026-04-01",
            "billing_end_date": "2026-04-30",
            "contract_type": "주택용 저압",
            "total_amount": "38000",
        },
    )

    tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
    # 수동 입력은 모두 user_confirmed=1로 들어가므로 필수 필드 게이트 통과.
    assert tariff_input.user_confirmed is True
    assert tariff_input.usage_kwh == 245.0
    assert tariff_input.user_charged_amount == 38000


def test_manual_input_does_not_grant_meter_photo_points(
    conn: sqlite3.Connection,
) -> None:
    """수동 입력은 electricity_bill 타입이라 meter_photo 점수는 부여되지 않는다."""
    user_id = db.insert_user(conn)
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={"usage_kwh": "245", "total_amount": "38000"},
    )
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.meter_photo_with_date == 0
    assert score.original_electricity_bill == 25  # bill 점수는 부여


def test_manual_input_can_reach_preliminary_calculation(
    conn: sqlite3.Connection,
) -> None:
    """수동 입력만으로 PRELIMINARY 또는 NEEDS_BASIS_REQUEST에 도달.

    실제 OFFICIAL이 되려면 점수 90+가 필요하므로 다른 자료도 함께 있어야 한다.
    """
    user_id = db.insert_user(conn)
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={
            "usage_kwh": "245",
            "billing_start_date": "2026-04-01",
            "billing_end_date": "2026-04-30",
            "contract_type": "주택용 저압",
            "total_amount": "38000",
        },
    )

    score = scoring.compute_completeness_score(conn, user_id=user_id)
    tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
    case = classification.classify_case(score, tariff_input)
    # electricity_bill 단독 → 25점 → NOT_CALCULABLE.
    assert score.total_score == 25
    assert case == CaseClassification.NOT_CALCULABLE


def test_extraction_skipped_for_manual_documents(conn: sqlite3.Connection) -> None:
    """수동 입력 문서는 find_documents_pending_extraction에서 제외된다.

    original_path가 NULL이라 pending 쿼리가 자연스럽게 제외한다.
    """
    user_id = db.insert_user(conn)
    extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type=DocumentType.ELECTRICITY_BILL.value,
        fields={"usage_kwh": "245"},
    )
    pending = extraction.find_documents_pending_extraction(conn, user_id=user_id)
    assert pending == []
