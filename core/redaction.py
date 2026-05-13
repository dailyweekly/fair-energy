"""시각 마스킹 (Visual Redaction) — 2026-05-13 외부 자문 반영.

보수적 접근:
  원본 이미지·PDF를 픽셀 단위로 redact 하지 않는다.
  대신 사용자가 직접 확인한 추출 필드만으로 「텍스트 요약본」을 재생성하여
  마스킹본(`documents.masked_path`)으로 저장한다.

이 방식의 장점:
  - 원본의 시각 정보(임대인 서명·도장·계좌·주소 사진·QR 등)가 마스킹본에 포함되지 않음
  - OCR 좌표 정보 없이도 안전한 마스킹본 생성 가능
  - OCR 정확도·사각지대에 의존하지 않음 (false negative 마스킹 없음)

이 방식의 한계:
  - 원본의 진본성을 보여주는 시각 자료(계량기 사진의 숫자 등)는 마스킹본에서 사라짐
  - 분쟁기관 제출 시에는 별도 동의로 원본을 제공해야 함 (정책 04 §7)

대안 (heavy_blur_image):
  계량기 사진처럼 시각 자체가 본질인 경우, 보수적 전체 블러를 적용한
  이미지를 마스킹본에 함께 첨부할 수 있다 (현재 MVP에서는 사용 안 함).

PDF 렌더링:
  Phase 8 Round 3에서는 Markdown 텍스트로 마스킹본을 저장한다.
  Phase 9에서 PyMuPDF로 PDF 렌더링하면 동일 내용을 PDF로도 제공한다.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional

from . import db


# ---------------------------------------------------------------------------
# 문구 상수 — 가드레일 통과 검증된 표현만 사용
# ---------------------------------------------------------------------------

MASKED_DOC_TITLE = "에너지 청구 자료 요약본 (마스킹 사본)"

MASKED_FOOTER = (
    "본 사본은 원본의 시각 정보(서명·도장·이미지·계좌·연락처 등)를 포함하지 않습니다.\n"
    "사용자가 직접 확인한 필드만 표시됩니다.\n"
    "원본 접근은 사용자 본인의 재동의가 있을 때만 허용됩니다.\n"
    "본 문서는 법률 자문이 아니며, 분쟁 결과를 판단하지 않습니다."
)


# ---------------------------------------------------------------------------
# 텍스트 요약본 생성
# ---------------------------------------------------------------------------


def build_text_summary(
    *,
    document_id: str,
    document_type: str,
    original_filename: str,
    fields: Iterable[dict],
    additional_notes: Optional[list[str]] = None,
) -> str:
    """확인된 필드만으로 Markdown 요약본을 생성한다.

    `source_text`(원문 인용)는 포함하지 않는다 — PII 유출 가능성 차단.
    `value`와 `label`만 사용한다.
    """
    lines: list[str] = []
    lines.append(f"# {MASKED_DOC_TITLE}")
    lines.append("")
    lines.append(f"- **문서 유형**: `{document_type}`")
    lines.append(f"- **문서 ID**: `{document_id[:8]}…`")
    lines.append(f"- **원본 파일명**: {original_filename}")
    lines.append(
        f"- **요약본 생성일 (UTC)**: "
        f"{datetime.now(timezone.utc).isoformat(timespec='seconds')}"
    )
    lines.append("")
    lines.append("## 사용자 확인 완료 필드")
    lines.append("")

    field_list = list(fields)
    if not field_list:
        lines.append("> 아직 사용자가 확인한 필드가 없습니다.")
    else:
        for f in field_list:
            label = f.get("label") or f.get("key", "(이름 없음)")
            value = f.get("value", "")
            unit = f.get("unit") or ""
            display_value = f"{value} {unit}".strip() if unit else value
            lines.append(f"- **{label}**: {display_value}")

    if additional_notes:
        lines.append("")
        lines.append("## 안내")
        for note in additional_notes:
            lines.append(f"- {note}")

    lines.append("")
    lines.append("---")
    lines.append("")
    for footer_line in MASKED_FOOTER.split("\n"):
        lines.append(footer_line)

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# 마스킹본 재생성 — DB와 디스크 동기
# ---------------------------------------------------------------------------


def regenerate_masked_view(
    conn: sqlite3.Connection,
    *,
    document_id: str,
    masked_dir: Path,
) -> Optional[Path]:
    """단일 문서의 마스킹본을 재생성한다.

    반환:
      - 생성된 마스킹본 파일 경로
      - 사용자 확인 필드가 0개면 None (마스킹본 없음)
      - 수동 입력 문서(`original_path IS NULL`)도 None
        (원본이 없으므로 추가 마스킹본 불필요)
    """
    doc_row = conn.execute(
        "SELECT * FROM documents WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    if not doc_row:
        raise ValueError(f"Document not found: {document_id}")

    # 수동 입력 문서는 원본이 없으므로 마스킹본도 불필요.
    if doc_row["original_path"] is None:
        return None

    # 사용자 확인된 필드만 가져온다 — source_text는 의도적으로 select 제외.
    field_rows = conn.execute(
        "SELECT key, label, value, unit FROM extracted_fields "
        "WHERE document_id = ? AND user_confirmed = 1 "
        "ORDER BY created_at",
        (document_id,),
    ).fetchall()

    if not field_rows:
        return None

    fields = [
        {"key": r["key"], "label": r["label"], "value": r["value"],
         "unit": r["unit"]}
        for r in field_rows
    ]

    md = build_text_summary(
        document_id=document_id,
        document_type=doc_row["document_type"],
        original_filename=doc_row["original_filename"],
        fields=fields,
    )

    user_dir = Path(masked_dir) / doc_row["user_id"]
    user_dir.mkdir(parents=True, exist_ok=True)
    masked_path = user_dir / f"{document_id}.md"
    masked_path.write_text(md, encoding="utf-8")

    with db.transaction(conn):
        conn.execute(
            "UPDATE documents SET masked_path = ?, updated_at = ? "
            "WHERE document_id = ?",
            (str(masked_path), db.utcnow_iso(), document_id),
        )

    return masked_path


def regenerate_all_masked_views(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    masked_dir: Path,
) -> int:
    """사용자의 모든 문서 중 확인된 필드가 있는 것의 마스킹본을 재생성.

    반환: 생성된 마스킹본 파일 수.
    수동 입력 문서, 확인 필드가 없는 문서는 건너뜀.
    """
    rows = conn.execute(
        """
        SELECT DISTINCT d.document_id
        FROM documents d
        JOIN extracted_fields f ON f.document_id = d.document_id
        WHERE d.user_id = ?
          AND d.original_path IS NOT NULL
          AND f.user_confirmed = 1
        ORDER BY d.created_at
        """,
        (user_id,),
    ).fetchall()

    count = 0
    for row in rows:
        result = regenerate_masked_view(
            conn,
            document_id=row["document_id"],
            masked_dir=masked_dir,
        )
        if result is not None:
            count += 1
    return count


# ---------------------------------------------------------------------------
# 보조 유틸 — 이미지 전체 블러 (현재 MVP에서는 사용 안 함)
# ---------------------------------------------------------------------------


def heavy_blur_image(image_bytes: bytes, *, blur_radius: int = 30) -> bytes:
    """전체 이미지를 가우시안 블러 처리한 바이트를 반환.

    OCR 좌표 없이 안전한 마스킹이 필요할 때의 보수적 폴백.
    현재 MVP에서는 기본 마스킹 전략(텍스트 요약)이 사용되며, 본 함수는
    Phase 9 이후 특수 케이스(예: 계량기 사진 시각 자체가 본질)에 활용 가능.
    """
    try:
        from PIL import Image, ImageFilter
    except ImportError as exc:  # pragma: no cover — Pillow는 requirements에 있음
        raise RuntimeError(
            "Pillow is required for heavy_blur_image. Run: pip install Pillow"
        ) from exc

    img = Image.open(BytesIO(image_bytes))
    blurred = img.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    output = BytesIO()
    fmt = (img.format or "PNG").upper()
    if fmt == "JPEG":
        blurred = blurred.convert("RGB")
    blurred.save(output, format=fmt)
    return output.getvalue()
