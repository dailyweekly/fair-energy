"""원본 파일 암호화 저장.

정책 04 §1·§5에 따라 원본은 Fernet(대칭키)으로 암호화하여 `storage/originals/`에 저장한다.
마스킹된 표시용 사본은 별도 경로에 저장한다 (PDF/이미지 시각 마스킹은 후속 단계).

키 관리:
- 환경변수 `APP_SECRET_KEY`에 Fernet 키(URL-safe base64 32바이트)를 둔다.
- 키가 없으면 개발 모드에서 1회용 키를 생성하지만, 그 경우 다시 열 수 없으므로 경고한다.
"""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from . import db


# ---------------------------------------------------------------------------
# 키 관리
# ---------------------------------------------------------------------------


class StorageKeyError(RuntimeError):
    """Fernet 키가 누락되거나 형식이 잘못되었을 때."""


class RRNDetectedError(ValueError):
    """업로드 파일에서 주민등록번호가 감지되었을 때 (2026-05-13).

    정책 04 §9 — 마스킹 후 보관이 아니라 업로드 자체를 거부하고,
    사용자에게 "해당 부분을 가린 후 다시 업로드해 주세요" 안내를 표시.
    텍스트 추출 가능한 파일(txt·docx 등)에 대해서만 사전 스캔 가능.
    이미지·PDF는 OCR 단계의 PII detection으로 감지된다.
    """


def load_or_generate_key(secret_key: Optional[str], *, allow_generate: bool) -> bytes:
    """환경변수의 키를 검증하거나, 개발 모드에서만 새 키를 만든다.

    프로덕션(`allow_generate=False`)에서 키가 없으면 StorageKeyError.
    """
    if secret_key:
        try:
            # Fernet 생성 자체가 키 검증 역할.
            Fernet(secret_key.encode())
            return secret_key.encode()
        except Exception as exc:
            raise StorageKeyError(
                "APP_SECRET_KEY is set but not a valid Fernet key. "
                "Generate one with Fernet.generate_key()."
            ) from exc

    if not allow_generate:
        raise StorageKeyError("APP_SECRET_KEY is required outside demo/development.")

    return Fernet.generate_key()


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _retention_until(months: int, now: Optional[datetime] = None) -> datetime:
    """보관 만료일 계산. 30일/개월 근사를 쓰지 않고 정확한 캘린더 일수를 쓴다."""
    base = now or datetime.now(timezone.utc)
    # 단순 일수 환산 — 정책 04 §6의 6/12/36은 일수 기준이 모호하므로 30일/개월로 일관 처리.
    return base + timedelta(days=30 * months)


@dataclass(frozen=True)
class StoredDocument:
    document_id: str
    original_path: Path
    masked_path: Optional[Path]
    file_hash: str
    size_bytes: int
    retention_until: datetime


class DocumentStorage:
    """원본 암호화 + DB 등록을 담당한다.

    Phase 2에서 마스킹된 표시용 사본은 「원본과 동일한 파일을 평문 사본으로」 저장한다.
    실제 시각 마스킹(PDF redaction·이미지 블러)은 후속 단계.
    """

    def __init__(
        self,
        *,
        key: bytes,
        originals_dir: Path,
        masked_dir: Path,
    ) -> None:
        self._fernet = Fernet(key)
        self._originals_dir = Path(originals_dir)
        self._masked_dir = Path(masked_dir)
        self._originals_dir.mkdir(parents=True, exist_ok=True)
        self._masked_dir.mkdir(parents=True, exist_ok=True)

    # --- 저장 ---

    def save_document(
        self,
        conn: sqlite3.Connection,
        *,
        user_id: str,
        document_type: str,
        original_filename: str,
        original_bytes: bytes,
        retention_months: int,
        masked_bytes: Optional[bytes] = None,
        scan_text_for_rrn: bool = True,
    ) -> StoredDocument:
        """원본 암호화 저장 + DB 등록.

        `masked_bytes`가 주어지면 그 파일을 마스킹 경로에 저장한다.
        주어지지 않으면 마스킹 경로는 None — 추후 OCR 단계에서 채워진다.

        `scan_text_for_rrn=True`이면 텍스트 추출 가능한 파일(.txt 등)을
        사전 스캔하여 주민등록번호 감지 시 `RRNDetectedError`를 발생시킨다.
        이미지·PDF는 OCR 단계의 PII detection으로 감지된다(정책 04 §9, 2026-05-13).
        """
        from . import masking  # 순환 import 회피

        if retention_months not in (6, 12, 36):
            raise ValueError("retention_months must be one of 6, 12, 36")

        # 텍스트 파일 사전 스캔 — 이미지·PDF는 OCR 후 감지.
        if scan_text_for_rrn and original_filename.lower().endswith(
            (".txt", ".md", ".csv")
        ):
            try:
                text = original_bytes.decode("utf-8", "ignore")
            except Exception:
                text = ""
            if masking.detect_rrn(text):
                raise RRNDetectedError(
                    "주민등록번호로 보이는 패턴이 감지되었습니다. "
                    "해당 부분을 가린 후 다시 업로드해 주세요."
                )

        document_id = db.new_id()
        user_originals = self._originals_dir / user_id
        user_masked = self._masked_dir / user_id
        user_originals.mkdir(parents=True, exist_ok=True)
        user_masked.mkdir(parents=True, exist_ok=True)

        # 파일 쓰기 — 원본은 암호화, 마스킹본은 평문.
        original_path = user_originals / f"{document_id}.bin"
        token = self._fernet.encrypt(original_bytes)
        original_path.write_bytes(token)

        masked_path: Optional[Path] = None
        if masked_bytes is not None:
            masked_path = user_masked / f"{document_id}.bin"
            masked_path.write_bytes(masked_bytes)

        file_hash = _sha256(original_bytes)
        size = len(original_bytes)
        retention_until = _retention_until(retention_months)
        now = db.utcnow_iso()

        with db.transaction(conn):
            conn.execute(
                """
                INSERT INTO documents (
                    document_id, user_id, document_type, original_filename,
                    original_path, masked_path, file_hash, size_bytes,
                    retention_until, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id, user_id, document_type, original_filename,
                    str(original_path),
                    str(masked_path) if masked_path else None,
                    file_hash, size,
                    retention_until.isoformat(timespec="seconds"),
                    now, now,
                ),
            )

        return StoredDocument(
            document_id=document_id,
            original_path=original_path,
            masked_path=masked_path,
            file_hash=file_hash,
            size_bytes=size,
            retention_until=retention_until,
        )

    # --- 읽기 ---

    def load_original(self, path: Path) -> bytes:
        """암호화된 원본을 복호화하여 평문 바이트로 반환."""
        token = Path(path).read_bytes()
        try:
            return self._fernet.decrypt(token)
        except InvalidToken as exc:
            raise StorageKeyError(
                "Failed to decrypt original file — wrong APP_SECRET_KEY?"
            ) from exc

    # --- 만료 처리 ---

    def expired_documents(
        self,
        conn: sqlite3.Connection,
        *,
        now: Optional[datetime] = None,
    ) -> list[sqlite3.Row]:
        cutoff = (now or datetime.now(timezone.utc)).isoformat(timespec="seconds")
        rows = conn.execute(
            "SELECT * FROM documents WHERE retention_until <= ?",
            (cutoff,),
        ).fetchall()
        return list(rows)

    def purge_expired(
        self,
        conn: sqlite3.Connection,
        *,
        now: Optional[datetime] = None,
    ) -> int:
        """만료 원본 파일을 디스크에서 삭제하고 DB의 original_path를 NULL로 표시.

        documents 행 자체는 보존하되 원본 경로만 비우는 형태.
        마스킹본은 정책 04 §6 「만료 후 처리」에 따라 유지 옵션을 가질 수 있다.
        """
        expired = self.expired_documents(conn, now=now)
        purged = 0
        purge_ts = db.utcnow_iso()
        with db.transaction(conn):
            for row in expired:
                if row["original_path"]:
                    p = Path(row["original_path"])
                    if p.exists():
                        p.unlink()
                    conn.execute(
                        "UPDATE documents "
                        "SET original_path = NULL, purged_at = ?, updated_at = ? "
                        "WHERE document_id = ?",
                        (purge_ts, purge_ts, row["document_id"]),
                    )
                    purged += 1
        return purged
