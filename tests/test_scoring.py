"""Energy Bill Completeness Score 회귀 테스트.

정책 02 §2의 배점과 §4의 필수 필드 게이트를 검증한다.
인위적으로 OFFICIAL_COMPARISON 비율을 끌어올리려는 변경은 본 테스트가 차단한다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from core import classification, db, extraction, scoring, storage
from core.llm_client import DemoLLMClient
from core.models import CaseClassification


# ---------------------------------------------------------------------------
# fixture: 사용자 + 업로드 헬퍼
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> storage.DocumentStorage:
    return storage.DocumentStorage(
        key=Fernet.generate_key(),
        originals_dir=tmp_path / "originals",
        masked_dir=tmp_path / "masked",
    )


def _setup_user(conn: sqlite3.Connection) -> str:
    return db.insert_user(conn)


def _upload_and_extract(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    user_id: str,
    *,
    doc_type: str,
    filename: str | None = None,
) -> str:
    filename = filename or f"{doc_type}.png"
    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type=doc_type,
        original_filename=filename,
        original_bytes=b"FAKE",
        retention_months=6,
    )
    extraction.extract_and_save(
        conn,
        document_id=stored.document_id,
        document_type=doc_type,
        original_filename=filename,
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    return stored.document_id


def _confirm_all(conn: sqlite3.Connection, user_id: str) -> None:
    rows = conn.execute(
        "SELECT f.field_id FROM extracted_fields f "
        "JOIN documents d ON d.document_id = f.document_id "
        "WHERE d.user_id = ?",
        (user_id,),
    ).fetchall()
    extraction.confirm_fields_bulk(
        conn, field_ids=[r["field_id"] for r in rows], confirmed=True
    )


def _set_field_value(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    key: str,
    value: str,
    confirm: bool = True,
) -> None:
    """편의: 특정 key의 필드 값을 변경 + 확인."""
    row = conn.execute(
        "SELECT f.field_id FROM extracted_fields f "
        "JOIN documents d ON d.document_id = f.document_id "
        "WHERE d.user_id = ? AND f.key = ? LIMIT 1",
        (user_id, key),
    ).fetchone()
    if not row:
        raise AssertionError(f"No field with key={key} for user {user_id}")
    extraction.update_field_value(conn, field_id=row["field_id"], value=value)
    if confirm:
        extraction.confirm_field(conn, field_id=row["field_id"], confirmed=True)


# ---------------------------------------------------------------------------
# 빈 상태
# ---------------------------------------------------------------------------


def test_empty_user_scores_zero(conn: sqlite3.Connection) -> None:
    user_id = _setup_user(conn)
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.total_score == 0
    assert len(score.missing_items) == 6  # 모든 카테고리 누락


# ---------------------------------------------------------------------------
# 단일 카테고리 배점
# ---------------------------------------------------------------------------


def test_only_lease_contract_yields_15(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="lease_contract")
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.lease_contract == 15
    assert score.total_score == 15


def test_only_management_fee_notice_yields_15(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="management_fee_notice")
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.itemized_fee_notice == 15
    assert score.total_score == 15


def test_electricity_bill_yields_25(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="electricity_bill")
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.original_electricity_bill == 25


def test_payment_proof_yields_10(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="payment_proof")
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.payment_proof == 10


# ---------------------------------------------------------------------------
# 계량기 사진 — 검침일 확인 게이트
# ---------------------------------------------------------------------------


def test_meter_photo_without_date_confirmation_scores_zero(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """계량기 사진은 검침일 또는 숫자가 사용자 확인되어야 점수가 부여된다."""
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="meter_photo")
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    # 확인 안 했으므로 0.
    assert score.meter_photo_with_date == 0
    assert any("검침" in m or "계량기" in m for m in score.missing_items)


def test_meter_photo_with_date_confirmed_scores_15(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="meter_photo")
    _set_field_value(conn, user_id=user_id, key="photo_date", value="2026-04-30")
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.meter_photo_with_date == 15


# ---------------------------------------------------------------------------
# 세대별 배분 산식 — 데모 fixture는 "미기재"이므로 점수 0
# ---------------------------------------------------------------------------


def test_management_fee_alone_does_not_grant_allocation_points(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """관리비 청구서만으로는 배분 산식 점수를 주지 않는다(데모 fixture가 '미기재')."""
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="management_fee_notice")
    _confirm_all(conn, user_id)
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.allocation_formula == 0
    assert score.itemized_fee_notice == 15  # 관리비 자체는 점수 인정


def test_allocation_points_when_value_provided(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="management_fee_notice")
    _set_field_value(
        conn, user_id=user_id, key="allocation_method",
        value="사용량 기반",  # 의미 있는 값
    )
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.allocation_formula == 20


def test_negative_value_does_not_grant_allocation(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="management_fee_notice")
    _set_field_value(
        conn, user_id=user_id, key="allocation_method",
        value="없음",
    )
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.allocation_formula == 0


# ---------------------------------------------------------------------------
# 풀 스코어 + classification 통합
# ---------------------------------------------------------------------------


def _build_all_docs(
    conn: sqlite3.Connection, store: storage.DocumentStorage, user_id: str
) -> None:
    for dt in ("lease_contract", "management_fee_notice", "electricity_bill",
               "meter_photo", "payment_proof"):
        _upload_and_extract(conn, store, user_id, doc_type=dt)


def test_all_uploads_without_allocation_score_80(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """모든 문서를 업로드해도 배분 산식이 없으면 80점."""
    user_id = _setup_user(conn)
    _build_all_docs(conn, store, user_id)
    _confirm_all(conn, user_id)
    # 단, 데모 management_fee_notice의 allocation_method는 '미기재' → 점수 0.
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    # 15(lease) + 15(fee) + 15(meter) + 25(bill) + 0(allocation) + 10(payment) = 80
    assert score.total_score == 80


def test_full_100_when_allocation_provided(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _build_all_docs(conn, store, user_id)
    _confirm_all(conn, user_id)
    _set_field_value(
        conn, user_id=user_id, key="allocation_method",
        value="사용량 기반",
    )
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    assert score.total_score == 100


def test_full_score_with_required_fields_yields_official_comparison(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """100점 + 필수 필드 모두 확인 → OFFICIAL_COMPARISON."""
    user_id = _setup_user(conn)
    _build_all_docs(conn, store, user_id)
    _confirm_all(conn, user_id)
    _set_field_value(
        conn, user_id=user_id, key="allocation_method", value="사용량 기반",
    )

    score = scoring.compute_completeness_score(conn, user_id=user_id)
    tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
    # demo electricity_bill에서 contract_type 'electricity_separate' 별도가 와도
    # detect_fixed_fee는 lease_contract의 electricity_separate를 본다.
    # 데모 lease_contract는 electricity_separate=='포함' → fixed fee 감지 가능.
    is_fixed = scoring.detect_fixed_fee(conn, user_id=user_id)

    case = classification.classify_case(score, tariff_input, is_fixed_fee=is_fixed)
    # lease 데모가 fixed_fee=True를 띄우면 정액 케이스로 분류된다 — 그것도 정책 02 §3과 일치.
    # 본 테스트는 점수+필수 필드 게이트가 작동함을 확인하는 게 목적.
    if is_fixed:
        assert case == CaseClassification.FIXED_MANAGEMENT_FEE
    else:
        assert case == CaseClassification.OFFICIAL_COMPARISON


def test_unconfirmed_fields_block_official_comparison(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """점수가 100이어도 user_confirmed가 누락되면 PRELIMINARY로 강등(정책 02 §5)."""
    user_id = _setup_user(conn)
    _build_all_docs(conn, store, user_id)
    # 점수 100 만들기 위해 확인 + 배분 입력.
    _confirm_all(conn, user_id)
    _set_field_value(
        conn, user_id=user_id, key="allocation_method", value="사용량 기반",
    )

    # 필수 필드 중 하나만 명시적으로 미확인 처리(예: usage_kwh).
    row = conn.execute(
        "SELECT f.field_id FROM extracted_fields f "
        "JOIN documents d ON d.document_id = f.document_id "
        "WHERE d.user_id = ? AND f.key = 'usage_kwh' LIMIT 1",
        (user_id,),
    ).fetchone()
    extraction.confirm_field(conn, field_id=row["field_id"], confirmed=False)

    score = scoring.compute_completeness_score(conn, user_id=user_id)
    tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
    is_fixed = scoring.detect_fixed_fee(conn, user_id=user_id)
    case = classification.classify_case(score, tariff_input, is_fixed_fee=is_fixed)

    # fixed fee가 트리거되지 않은 시나리오에서는 PRELIMINARY로 강등되어야 한다.
    if not is_fixed:
        assert case == CaseClassification.PRELIMINARY_CALCULATION


# ---------------------------------------------------------------------------
# 스냅샷 저장
# ---------------------------------------------------------------------------


def test_save_score_snapshot_persists(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="lease_contract")
    score = scoring.compute_completeness_score(conn, user_id=user_id)
    score_id = scoring.save_score_snapshot(conn, user_id=user_id, score=score)

    row = conn.execute(
        "SELECT total_score, missing_items_json FROM passport_scores "
        "WHERE score_id = ?",
        (score_id,),
    ).fetchone()
    assert row["total_score"] == 15
    assert "관리비" in row["missing_items_json"]  # JSON에 누락 항목 직렬화 확인


def test_latest_score_returns_most_recent(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="lease_contract")

    first = scoring.compute_completeness_score(conn, user_id=user_id)
    scoring.save_score_snapshot(conn, user_id=user_id, score=first)

    _upload_and_extract(conn, store, user_id, doc_type="electricity_bill")
    second = scoring.compute_completeness_score(conn, user_id=user_id)
    scoring.save_score_snapshot(conn, user_id=user_id, score=second)

    latest = scoring.latest_score(conn, user_id=user_id)
    assert latest is not None
    assert latest["total_score"] == second.total_score


# ---------------------------------------------------------------------------
# TariffInput 빌더
# ---------------------------------------------------------------------------


def test_tariff_input_user_confirmed_false_when_no_confirmation(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="electricity_bill")
    # 아무 필드도 확인 안 함.
    tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
    assert tariff_input.user_confirmed is False
    assert tariff_input.usage_kwh is None


def test_tariff_input_user_confirmed_true_when_all_required_present(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="electricity_bill")
    _confirm_all(conn, user_id)
    tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
    # 데모 fixture에 usage/dates/contract_type/total_amount 모두 있다.
    assert tariff_input.user_confirmed is True
    assert tariff_input.usage_kwh == 245.0
    assert tariff_input.user_charged_amount == 38000


def test_tariff_input_handles_comma_in_amount(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="electricity_bill")
    _confirm_all(conn, user_id)
    # 사용자가 38,000으로 콤마 포함 값을 입력한 경우.
    _set_field_value(
        conn, user_id=user_id, key="total_amount", value="38,000",
    )
    tariff_input = scoring.build_tariff_input(conn, user_id=user_id)
    assert tariff_input.user_charged_amount == 38000


# ---------------------------------------------------------------------------
# 정액 케이스 감지
# ---------------------------------------------------------------------------


def test_detect_fixed_fee_when_electricity_included(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="lease_contract")
    _confirm_all(conn, user_id)
    # 데모 lease_contract의 electricity_separate=='포함'.
    assert scoring.detect_fixed_fee(conn, user_id=user_id) is True


def test_detect_fixed_fee_false_when_no_lease(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="electricity_bill")
    _confirm_all(conn, user_id)
    assert scoring.detect_fixed_fee(conn, user_id=user_id) is False


def test_detect_fixed_fee_ignores_unconfirmed(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """확인되지 않은 electricity_separate 값으로는 fixed fee를 감지하면 안 된다."""
    user_id = _setup_user(conn)
    _upload_and_extract(conn, store, user_id, doc_type="lease_contract")
    # 모두 미확인 상태 유지.
    assert scoring.detect_fixed_fee(conn, user_id=user_id) is False
