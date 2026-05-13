"""consent 모듈 테스트 — 정책 04 §3·§6·§7."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from core import consent, db


def _new_user(conn: sqlite3.Connection) -> str:
    return db.insert_user(conn)


# --- 필수 동의 강제 ---

def test_service_required(conn: sqlite3.Connection) -> None:
    user_id = _new_user(conn)
    request = consent.ConsentRequest(
        consent_service=False,
        consent_personal_info=True,
        consent_ai_processing=True,
        consent_storage_months=6,
    )
    with pytest.raises(consent.ConsentValidationError):
        consent.record_consent(conn, user_id=user_id, request=request)


def test_personal_info_required(conn: sqlite3.Connection) -> None:
    user_id = _new_user(conn)
    request = consent.ConsentRequest(
        consent_service=True,
        consent_personal_info=False,
        consent_ai_processing=True,
        consent_storage_months=6,
    )
    with pytest.raises(consent.ConsentValidationError):
        consent.record_consent(conn, user_id=user_id, request=request)


def test_ai_processing_required(conn: sqlite3.Connection) -> None:
    user_id = _new_user(conn)
    request = consent.ConsentRequest(
        consent_service=True,
        consent_personal_info=True,
        consent_ai_processing=False,
        consent_storage_months=6,
    )
    with pytest.raises(consent.ConsentValidationError):
        consent.record_consent(conn, user_id=user_id, request=request)


def test_invalid_storage_months_raises(conn: sqlite3.Connection) -> None:
    user_id = _new_user(conn)
    request = consent.ConsentRequest(
        consent_service=True,
        consent_personal_info=True,
        consent_ai_processing=True,
        consent_storage_months=24,  # 허용 범위 외
    )
    with pytest.raises(consent.ConsentValidationError):
        consent.record_consent(conn, user_id=user_id, request=request)


def test_valid_request_creates_consent(conn: sqlite3.Connection) -> None:
    user_id = _new_user(conn)
    request = consent.ConsentRequest(
        consent_service=True,
        consent_personal_info=True,
        consent_ai_processing=True,
        consent_storage_months=12,
        consent_ngo_share=True,
    )
    consent_id = consent.record_consent(conn, user_id=user_id, request=request)
    row = conn.execute(
        "SELECT consent_ngo_share, consent_storage_months "
        "FROM consents WHERE consent_id = ?",
        (consent_id,),
    ).fetchone()
    assert row["consent_ngo_share"] == 1
    assert row["consent_storage_months"] == 12


# --- 외부 제출 (건별·기관별 별도 동의) ---

def test_external_submission_requires_fields(conn: sqlite3.Connection) -> None:
    user_id = _new_user(conn)
    with pytest.raises(consent.ConsentValidationError):
        consent.record_external_submission_consent(
            conn,
            user_id=user_id,
            request=consent.ExternalSubmissionRequest(
                target_organization="",  # 누락
                document_scope=("doc1",),
                purpose="x",
            ),
            consent_storage_months=6,
        )

    with pytest.raises(consent.ConsentValidationError):
        consent.record_external_submission_consent(
            conn,
            user_id=user_id,
            request=consent.ExternalSubmissionRequest(
                target_organization="조정위",
                document_scope=(),  # 누락
                purpose="x",
            ),
            consent_storage_months=6,
        )


def test_external_submission_records_target_metadata(conn: sqlite3.Connection) -> None:
    user_id = _new_user(conn)
    consent_id = consent.record_external_submission_consent(
        conn,
        user_id=user_id,
        request=consent.ExternalSubmissionRequest(
            target_organization="주택임대차분쟁조정위",
            document_scope=("doc-1", "doc-2"),
            purpose="검산 자료 제출",
        ),
        consent_storage_months=12,
    )

    row = conn.execute(
        "SELECT consent_external_submission, external_target "
        "FROM consents WHERE consent_id = ?",
        (consent_id,),
    ).fetchone()
    assert row["consent_external_submission"] == 1
    payload = json.loads(row["external_target"])
    assert payload["organization"] == "주택임대차분쟁조정위"
    assert payload["documents"] == ["doc-1", "doc-2"]


# --- 보관기간 계산 ---

def test_retention_deadline_6_months() -> None:
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    deadline = consent.retention_deadline(6, now=now)
    assert deadline == now + timedelta(days=180)


def test_retention_invalid_months() -> None:
    with pytest.raises(consent.ConsentValidationError):
        consent.retention_deadline(24)


def test_is_expiring_soon_true() -> None:
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    deadline = now + timedelta(days=10)
    assert consent.is_expiring_soon(deadline, now=now, warning_days=30) is True


def test_is_expiring_soon_false() -> None:
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    deadline = now + timedelta(days=60)
    assert consent.is_expiring_soon(deadline, now=now, warning_days=30) is False


def test_is_expiring_soon_excludes_already_expired() -> None:
    """이미 지난 만료일은 곧 만료 예정이 아니라 만료 완료."""
    now = datetime(2026, 5, 14, tzinfo=timezone.utc)
    deadline = now - timedelta(days=1)
    assert consent.is_expiring_soon(deadline, now=now) is False


# --- 최신 동의 조회 ---

def test_latest_consent_excludes_external_submissions(conn: sqlite3.Connection) -> None:
    """latest_consent는 일반 동의만 가져온다(외부 제출 동의는 별도)."""
    user_id = _new_user(conn)
    base = consent.record_consent(
        conn,
        user_id=user_id,
        request=consent.ConsentRequest(
            consent_service=True,
            consent_personal_info=True,
            consent_ai_processing=True,
            consent_storage_months=6,
        ),
    )
    consent.record_external_submission_consent(
        conn,
        user_id=user_id,
        request=consent.ExternalSubmissionRequest(
            target_organization="조정위",
            document_scope=("d1",),
            purpose="제출",
        ),
        consent_storage_months=6,
    )
    row = consent.latest_consent(conn, user_id=user_id)
    assert row is not None
    assert row["consent_id"] == base
    assert row["consent_external_submission"] == 0
