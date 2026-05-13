"""문서 추출 오케스트레이션.

순서:
  1. LLM 호출 (live or demo)
  2. JSON 스키마 검증 (extraction_schema)
  3. ExtractedDocument 모델로 매핑
  4. DB의 extracted_fields 테이블에 user_confirmed=False로 저장

정책 02 §5 — AI 추출값은 사용자 확인 전 계산에 사용 금지.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from . import db
from .extraction_schema import LLMOutputDocument, parse_llm_output
from .llm_client import ExtractionRequest, LLMClient
from .models import DocumentType, ExtractedDocument, ExtractedField


# 신뢰도 임계값 — 미만이면 UI에서 "수정 필요"로 표시.
CONFIDENCE_LOW_THRESHOLD = 0.7


def _mime_from_filename(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip(".")
    return {
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "pdf": "application/pdf",
        "docx": ("application/vnd.openxmlformats-officedocument."
                 "wordprocessingml.document"),
        "txt": "text/plain",
    }.get(ext, "application/octet-stream")


def _to_extracted_document(
    document_id: str,
    document_type_value: str,
    original_filename: str,
    raw: LLMOutputDocument,
) -> ExtractedDocument:
    """LLM 출력 → 내부 모델 변환.

    confidence가 임계 미만이면 needs_user_confirmation을 True로 강제.
    user_confirmed는 항상 False로 시작한다(정책 02 §5).
    """
    try:
        doc_type = DocumentType(raw.document_type)
    except ValueError:
        doc_type = DocumentType.UNKNOWN

    # raw가 doc_type=unknown으로 분류했어도 호출자가 알려준 타입을 우선 사용.
    if document_type_value:
        try:
            doc_type = DocumentType(document_type_value)
        except ValueError:
            pass

    fields: list[ExtractedField] = []
    for f in raw.fields:
        needs_confirm = f.needs_user_confirmation or f.confidence < CONFIDENCE_LOW_THRESHOLD
        fields.append(
            ExtractedField(
                key=f.key,
                label=f.label,
                value=f.value,
                unit=f.unit,
                confidence=f.confidence,
                source_document_id=document_id,
                source_text=f.source_text,
                needs_user_confirmation=needs_confirm,
                user_confirmed=False,
            )
        )

    return ExtractedDocument(
        document_id=document_id,
        document_type=doc_type,
        original_filename=original_filename,
        extracted_fields=fields,
        extraction_summary=raw.extraction_summary,
        warnings=list(raw.warnings),
    )


def extract_document(
    *,
    document_id: str,
    document_type: str,
    original_filename: str,
    document_bytes: bytes,
    llm_client: LLMClient,
    hint: Optional[str] = None,
) -> ExtractedDocument:
    """단일 문서를 추출한다 (DB 저장 없이).

    호출자가 평문 바이트를 전달해야 한다 — 암호화된 원본은
    `storage.DocumentStorage.load_original()`로 먼저 복호화할 것.
    """
    request = ExtractionRequest(
        document_bytes=document_bytes,
        document_type=document_type,
        mime_type=_mime_from_filename(original_filename),
        filename=original_filename,
        hint=hint,
    )
    raw_response = llm_client.extract(request)
    validated = parse_llm_output(raw_response)
    return _to_extracted_document(
        document_id=document_id,
        document_type_value=document_type,
        original_filename=original_filename,
        raw=validated,
    )


def save_extracted_fields(
    conn: sqlite3.Connection,
    *,
    document: ExtractedDocument,
) -> list[str]:
    """ExtractedDocument의 필드를 extracted_fields 테이블에 INSERT.

    user_confirmed는 무조건 0으로 저장한다.
    """
    inserted_ids: list[str] = []
    now = db.utcnow_iso()
    with db.transaction(conn):
        for field in document.extracted_fields:
            field_id = db.new_id()
            conn.execute(
                """
                INSERT INTO extracted_fields (
                    field_id, document_id, key, label, value, unit,
                    confidence, source_text,
                    needs_user_confirmation, user_confirmed,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?)
                """,
                (
                    field_id, document.document_id,
                    field.key, field.label, field.value, field.unit,
                    field.confidence, field.source_text,
                    int(field.needs_user_confirmation),
                    now, now,
                ),
            )
            inserted_ids.append(field_id)
    return inserted_ids


def extract_and_save(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    document_type: str,
    original_filename: str,
    document_bytes: bytes,
    llm_client: LLMClient,
    hint: Optional[str] = None,
) -> tuple[ExtractedDocument, list[str]]:
    """추출 + 저장 한 번에 — Streamlit 페이지에서 사용."""
    document = extract_document(
        document_id=document_id,
        document_type=document_type,
        original_filename=original_filename,
        document_bytes=document_bytes,
        llm_client=llm_client,
        hint=hint,
    )
    inserted_ids = save_extracted_fields(conn, document=document)
    return document, inserted_ids


# ---------------------------------------------------------------------------
# Phase 4 — 추출 결과 조회·수정·확인
# ---------------------------------------------------------------------------


def list_user_documents_with_fields(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> list[dict]:
    """사용자별 문서와 그 추출 필드를 묶어 반환한다.

    각 항목은 {"document": Row, "fields": list[Row]} 형식.
    Streamlit 페이지가 직접 렌더링한다.
    """
    docs = conn.execute(
        "SELECT * FROM documents WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    ).fetchall()

    result: list[dict] = []
    for d in docs:
        fields = conn.execute(
            "SELECT * FROM extracted_fields WHERE document_id = ? "
            "ORDER BY created_at",
            (d["document_id"],),
        ).fetchall()
        result.append({"document": d, "fields": list(fields)})
    return result


def find_documents_pending_extraction(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> list[sqlite3.Row]:
    """추출이 아직 안 된(extracted_fields가 비어있는) 문서들.

    파기된 문서(`original_path IS NULL`)는 제외한다.
    """
    return list(
        conn.execute(
            """
            SELECT d.* FROM documents d
            LEFT JOIN extracted_fields f ON f.document_id = d.document_id
            WHERE d.user_id = ?
              AND d.original_path IS NOT NULL
            GROUP BY d.document_id
            HAVING COUNT(f.field_id) = 0
            ORDER BY d.created_at
            """,
            (user_id,),
        ).fetchall()
    )


def update_field_value(
    conn: sqlite3.Connection,
    *,
    field_id: str,
    value: Optional[str],
    unit: Optional[str] = None,
) -> None:
    """사용자가 수정한 값을 저장한다. user_confirmed는 별도 함수에서 처리.

    값을 수정하면 needs_user_confirmation은 자동으로 False가 되지 않는다 —
    사용자가 명시적으로 확인 체크를 해야만 user_confirmed=True로 바뀐다.
    """
    with db.transaction(conn):
        if unit is None:
            conn.execute(
                "UPDATE extracted_fields SET value = ?, updated_at = ? "
                "WHERE field_id = ?",
                (value, db.utcnow_iso(), field_id),
            )
        else:
            conn.execute(
                "UPDATE extracted_fields SET value = ?, unit = ?, updated_at = ? "
                "WHERE field_id = ?",
                (value, unit, db.utcnow_iso(), field_id),
            )


def confirm_field(
    conn: sqlite3.Connection,
    *,
    field_id: str,
    confirmed: bool = True,
) -> None:
    """단일 필드의 확인 플래그를 설정."""
    with db.transaction(conn):
        conn.execute(
            "UPDATE extracted_fields SET user_confirmed = ?, updated_at = ? "
            "WHERE field_id = ?",
            (int(confirmed), db.utcnow_iso(), field_id),
        )


def confirm_fields_bulk(
    conn: sqlite3.Connection,
    *,
    field_ids: list[str],
    confirmed: bool = True,
) -> int:
    """여러 필드를 한 번에 확인. rowcount를 반환."""
    if not field_ids:
        return 0
    placeholders = ",".join("?" * len(field_ids))
    with db.transaction(conn):
        cursor = conn.execute(
            f"UPDATE extracted_fields "
            f"SET user_confirmed = ?, updated_at = ? "
            f"WHERE field_id IN ({placeholders})",
            (int(confirmed), db.utcnow_iso(), *field_ids),
        )
    return cursor.rowcount


def auto_extract_pending(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    llm_client: LLMClient,
    storage,  # core.storage.DocumentStorage — 순환 import 방지 위해 forward ref
) -> int:
    """미추출 문서를 자동 추출한다.

    이미 추출된 문서는 자연스럽게 건너뛴다(idempotent).
    원본이 파기된 문서는 처리되지 않는다.
    반환값: 새로 추출된 문서 수.
    """
    pending = find_documents_pending_extraction(conn, user_id=user_id)
    count = 0
    for row in pending:
        path = Path(row["original_path"])
        if not path.exists():
            continue
        plaintext = storage.load_original(path)
        extract_and_save(
            conn,
            document_id=row["document_id"],
            document_type=row["document_type"],
            original_filename=row["original_filename"],
            document_bytes=plaintext,
            llm_client=llm_client,
        )
        count += 1
    return count


def confirmation_status(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> dict:
    """사용자 전체 필드의 확인 진행도를 요약."""
    row = conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(user_confirmed) AS confirmed,
               SUM(CASE WHEN confidence < ? THEN 1 ELSE 0 END) AS low_confidence
        FROM extracted_fields f
        JOIN documents d ON d.document_id = f.document_id
        WHERE d.user_id = ?
        """,
        (CONFIDENCE_LOW_THRESHOLD, user_id),
    ).fetchone()
    total = row["total"] or 0
    confirmed = row["confirmed"] or 0
    low = row["low_confidence"] or 0
    return {
        "total": total,
        "confirmed": confirmed,
        "low_confidence": low,
        "all_confirmed": total > 0 and total == confirmed,
    }


# ---------------------------------------------------------------------------
# Phase 8 Round 2 — 수동 입력 모드 (2026-05-13 외부 자문 반영)
# ---------------------------------------------------------------------------


# 수동 입력 모드는 외부 LLM API에 원본을 송신하지 않으려는 사용자를 위한 경로다.
# 이 경로에서 생성된 문서는 documents.original_path = NULL.
MANUAL_INPUT_FILENAME = "수동 입력"


def create_manual_document(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    document_type: str,
    fields: dict[str, str],
    field_labels: Optional[dict[str, str]] = None,
    field_units: Optional[dict[str, str]] = None,
    retention_months: int = 6,
) -> tuple[str, list[str]]:
    """원본 파일 없이 사용자가 직접 입력한 필드만으로 문서를 생성.

    OCR·외부 API를 거치지 않으므로 국외 이전 동의가 없는 사용자도 사용 가능.
    모든 필드는 `user_confirmed=True`, `confidence=1.0`으로 저장된다 —
    사용자가 직접 타이핑한 값은 OCR 추출값보다 신뢰도가 높다.

    반환: (document_id, [field_id, ...])
    """
    from datetime import datetime, timedelta, timezone

    if retention_months not in (6, 12, 36):
        raise ValueError("retention_months must be one of 6, 12, 36")
    if not fields:
        raise ValueError("fields must contain at least one entry")

    document_id = db.new_id()
    now = db.utcnow_iso()
    retention_until = (
        datetime.now(timezone.utc) + timedelta(days=30 * retention_months)
    ).isoformat(timespec="seconds")
    labels = field_labels or {}
    units = field_units or {}

    inserted_ids: list[str] = []
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO documents (
                document_id, user_id, document_type, original_filename,
                original_path, masked_path, file_hash, size_bytes,
                retention_until, created_at, updated_at
            ) VALUES (?, ?, ?, ?, NULL, NULL, NULL, 0, ?, ?, ?)
            """,
            (document_id, user_id, document_type, MANUAL_INPUT_FILENAME,
             retention_until, now, now),
        )

        for key, value in fields.items():
            if value is None or str(value).strip() == "":
                continue
            field_id = db.new_id()
            conn.execute(
                """
                INSERT INTO extracted_fields (
                    field_id, document_id, key, label, value, unit,
                    confidence, source_text,
                    needs_user_confirmation, user_confirmed,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1.0, NULL, 0, 1, ?, ?)
                """,
                (
                    field_id, document_id, key,
                    labels.get(key, key),
                    str(value),
                    units.get(key),
                    now, now,
                ),
            )
            inserted_ids.append(field_id)

    return document_id, inserted_ids
