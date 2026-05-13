"""RRN 감지·거부 가드 테스트 (Phase 8 Round 1).

정책 04 §9 — 주민등록번호 포함 텍스트 업로드는 거부해야 한다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from core import db, masking, storage


@pytest.fixture
def store(tmp_path: Path) -> storage.DocumentStorage:
    return storage.DocumentStorage(
        key=Fernet.generate_key(),
        originals_dir=tmp_path / "originals",
        masked_dir=tmp_path / "masked",
    )


# --- detect_rrn 헬퍼 ---

def test_detect_rrn_basic() -> None:
    assert masking.detect_rrn("주민번호 900101-1234567") is True


def test_detect_rrn_no_hyphen() -> None:
    assert masking.detect_rrn("주민번호 9001011234567") is True


def test_detect_rrn_empty() -> None:
    assert masking.detect_rrn("") is False


def test_detect_rrn_clean_text() -> None:
    assert masking.detect_rrn("임대인 이름: 홍길동") is False


# --- storage가 RRN 포함 텍스트 업로드 거부 ---

def test_storage_rejects_txt_with_rrn(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    payload = "임대차계약서\n임대인 주민번호 900101-1234567\n".encode("utf-8")

    with pytest.raises(storage.RRNDetectedError) as exc:
        store.save_document(
            conn,
            user_id=user_id,
            document_type="lease_contract",
            original_filename="contract.txt",
            original_bytes=payload,
            retention_months=6,
        )
    # 사용자 안내 문구가 예외 메시지에 포함된다.
    assert "가린 후 다시 업로드" in str(exc.value)


def test_storage_allows_txt_without_rrn(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    user_id = db.insert_user(conn)
    payload = "임대차계약서\n임대인: 홍길동\n월세 350000원\n".encode("utf-8")

    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type="lease_contract",
        original_filename="contract.txt",
        original_bytes=payload,
        retention_months=6,
    )
    assert stored.original_path.exists()


def test_storage_does_not_scan_images(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """이미지·PDF는 사전 스캔 대상이 아니다 (OCR 단계에서 처리)."""
    user_id = db.insert_user(conn)
    # 이미지처럼 보이는 바이트지만 안에 RRN 문자열이 우연히 들어 있어도
    # .png 확장자라면 사전 스캔하지 않는다.
    payload = b"\x89PNG\r\n\x1a\n900101-1234567 in bytes"

    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type="meter_photo",
        original_filename="meter.png",
        original_bytes=payload,
        retention_months=6,
    )
    assert stored.original_path.exists()  # 정상 저장 — OCR 후 별도 처리


def test_scan_can_be_disabled(
    conn: sqlite3.Connection, store: storage.DocumentStorage
) -> None:
    """`scan_text_for_rrn=False`이면 강제로 저장된다 (관리자 도구 등)."""
    user_id = db.insert_user(conn)
    payload = "주민번호 900101-1234567".encode("utf-8")

    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type="lease_contract",
        original_filename="contract.txt",
        original_bytes=payload,
        retention_months=6,
        scan_text_for_rrn=False,
    )
    assert stored.original_path.exists()
