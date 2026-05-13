"""자료 요약본 PDF 생성 — Phase 9 Round 2.

Phase 8 Round 3의 텍스트 요약본 방침을 그대로 따라, 사용자가 확인한 필드만으로
PDF를 렌더링한다. 원본 이미지·source_text는 포함하지 않는다.

PyMuPDF의 built-in CJK 폰트(`fontname="korea"`)를 사용한다.

⚠ 한계 사항 (LIMITATION):
- 명칭은 「에너지 청구 자료 요약본 (사용자 보관용)」 — 분쟁용 문서가 아님을 표지·푸터에 명시.
- 폰트 렌더링은 일부 특수문자에서 시스템에 따라 차이가 있을 수 있다.
- 외부 자문(2026-05-13) 권고에 따라 본 PDF는 「증거 패키지」가 아닌 「자료 요약본」.
"""

from __future__ import annotations

import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# 폰트·레이아웃 상수
# ---------------------------------------------------------------------------

FONT_ALIAS = "kr"   # 문서 내 폰트 별칭.
FONT_SIZE_TITLE = 18
FONT_SIZE_HEADING = 14
FONT_SIZE_BODY = 11
FONT_SIZE_FOOTER = 9

PAGE_WIDTH = 595   # A4 portrait points
PAGE_HEIGHT = 842
MARGIN_LEFT = 50
MARGIN_RIGHT = 50
MARGIN_TOP = 50
MARGIN_BOTTOM = 50


# 한글 텍스트가 추출 가능한 형태로 PDF에 임베드되려면 실제 TTF/OTF 폰트를 써야 한다.
# PyMuPDF built-in CJK는 시각 표시는 되지만 text extraction에서 깨질 수 있다.
KOREAN_FONT_CANDIDATES: tuple[str, ...] = (
    # Windows 기본
    r"C:\Windows\Fonts\malgun.ttf",
    r"C:\Windows\Fonts\malgunbd.ttf",
    r"C:\Windows\Fonts\gulim.ttc",
    # macOS 기본
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    # Linux Noto·NanumGothic (Streamlit Community Cloud의 packages.txt가 설치)
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)


def _resolve_korean_font() -> Optional[str]:
    """시스템에서 사용 가능한 한국어 TTF 폰트 경로를 반환한다.

    찾지 못하면 None (호출 측이 폴백 또는 경고 처리).
    """
    for path in KOREAN_FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return None


_KOREAN_FONT_PATH = _resolve_korean_font()


class KoreanFontNotAvailableError(RuntimeError):
    """시스템에서 한국어 폰트를 찾을 수 없을 때.

    PDF가 PyMuPDF built-in CJK로 렌더링되면 시각은 보이나 text extraction이
    깨질 수 있으므로, 베타 환경에서는 한국어 폰트 설치 후 다시 시도하도록 안내한다.
    """


# ---------------------------------------------------------------------------
# 안내 문구
# ---------------------------------------------------------------------------

PDF_TITLE = "에너지 청구 자료 요약본"
PDF_SUBTITLE = "사용자 보관용 자료 (분쟁용 문서 아님)"

PDF_DISCLAIMER = (
    "본 자료 요약본은 사용자가 직접 확인한 자료를 기반으로 생성된 보관용 문서입니다. "
    "본 서비스는 법률 자문이 아니며, 임대인의 위법성·환급·분쟁 결과를 판단하지 않습니다. "
    "원본의 시각 정보(서명·도장·이미지·계좌·연락처 등)는 본 PDF에 포함되지 않습니다. "
    "본 PDF는 분쟁용 문서가 아닌 사용자 보관용 자료 요약입니다. "
    "외부 기관에 제출이 필요한 경우 별도 동의 절차가 필요합니다."
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_page(doc: fitz.Document) -> fitz.Page:
    return doc.new_page(width=PAGE_WIDTH, height=PAGE_HEIGHT)


def _insert_textbox(
    page: fitz.Page,
    text: str,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    fontsize: int = FONT_SIZE_BODY,
    align: int = 0,  # 0=left, 1=center, 2=right, 3=justify
) -> None:
    rect = fitz.Rect(x, y, x + width, y + height)
    kwargs: dict = {
        "fontsize": fontsize,
        "align": align,
    }
    if _KOREAN_FONT_PATH:
        kwargs["fontname"] = FONT_ALIAS
        kwargs["fontfile"] = _KOREAN_FONT_PATH
    else:
        # 폴백: PyMuPDF built-in CJK. 시각은 보이나 text extraction은 깨질 수 있음.
        kwargs["fontname"] = "china-s"
    page.insert_textbox(rect, text, **kwargs)


# ---------------------------------------------------------------------------
# 페이지 빌더
# ---------------------------------------------------------------------------


def _build_cover_page(doc: fitz.Document, user_id: str) -> None:
    page = _new_page(doc)
    content_w = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    y = MARGIN_TOP + 80

    _insert_textbox(
        page, PDF_TITLE,
        x=MARGIN_LEFT, y=y, width=content_w, height=40,
        fontsize=FONT_SIZE_TITLE, align=1,
    )
    y += 50

    _insert_textbox(
        page, PDF_SUBTITLE,
        x=MARGIN_LEFT, y=y, width=content_w, height=25,
        fontsize=FONT_SIZE_HEADING, align=1,
    )
    y += 60

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    meta = (
        f"생성일 (UTC): {now}\n"
        f"사용자 ID: {user_id[:8]}…\n"
        "발행: 공정에너지 (Energy Bill Passport)"
    )
    _insert_textbox(
        page, meta,
        x=MARGIN_LEFT, y=y, width=content_w, height=80,
        fontsize=FONT_SIZE_BODY,
    )
    y += 100

    _insert_textbox(
        page, PDF_DISCLAIMER,
        x=MARGIN_LEFT, y=y,
        width=content_w, height=PAGE_HEIGHT - y - MARGIN_BOTTOM,
        fontsize=FONT_SIZE_FOOTER, align=3,
    )


def _build_score_page(doc: fitz.Document, score_row: sqlite3.Row) -> None:
    page = _new_page(doc)
    content_w = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    y = MARGIN_TOP

    _insert_textbox(
        page, "자료 완결성 점수",
        x=MARGIN_LEFT, y=y, width=content_w, height=30,
        fontsize=FONT_SIZE_HEADING,
    )
    y += 40

    total = score_row["total_score"]
    summary = (
        f"총점: {total} / 100\n\n"
        f"임대차계약서:           {score_row['lease_contract']} / 15\n"
        f"관리비 항목별 내역:     {score_row['itemized_fee_notice']} / 15\n"
        f"계량기 사진·검침일:     {score_row['meter_photo_with_date']} / 15\n"
        f"한전·임대인 원고지서:   {score_row['original_electricity_bill']} / 25\n"
        f"세대별 배분 산식:       {score_row['allocation_formula']} / 20\n"
        f"납부내역·계좌이체:      {score_row['payment_proof']} / 10"
    )
    _insert_textbox(
        page, summary,
        x=MARGIN_LEFT, y=y, width=content_w, height=250,
        fontsize=FONT_SIZE_BODY,
    )
    y += 270

    note = (
        "본 점수는 사용자가 업로드·확인한 자료를 기준으로 산정됩니다. "
        "검산 가능성 분류(검산 불가 / 근거 요청 필요 / 예비 검산 가능 / 공식 산식 비교 가능 / "
        "정액 관리비 케이스)는 점수와 필수 필드 확인 여부를 함께 고려해 결정됩니다."
    )
    _insert_textbox(
        page, note,
        x=MARGIN_LEFT, y=y, width=content_w, height=120,
        fontsize=FONT_SIZE_FOOTER, align=3,
    )


def _build_document_pages(
    doc: fitz.Document, conn: sqlite3.Connection, user_id: str,
) -> int:
    """확인 필드가 있는 문서별 페이지. 반환: 페이지 수."""
    doc_rows = conn.execute(
        """
        SELECT d.document_id, d.document_type, d.original_filename,
               d.created_at, COUNT(f.field_id) AS confirmed_count
        FROM documents d
        JOIN extracted_fields f ON f.document_id = d.document_id
        WHERE d.user_id = ? AND f.user_confirmed = 1
        GROUP BY d.document_id
        ORDER BY d.created_at
        """,
        (user_id,),
    ).fetchall()

    content_w = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    count = 0

    for row in doc_rows:
        fields = conn.execute(
            "SELECT key, label, value, unit FROM extracted_fields "
            "WHERE document_id = ? AND user_confirmed = 1 ORDER BY created_at",
            (row["document_id"],),
        ).fetchall()

        page = _new_page(doc)
        y = MARGIN_TOP

        _insert_textbox(
            page, f"문서: {row['original_filename']}",
            x=MARGIN_LEFT, y=y, width=content_w, height=25,
            fontsize=FONT_SIZE_HEADING,
        )
        y += 30

        meta = (
            f"유형: {row['document_type']}\n"
            f"문서 ID: {row['document_id'][:8]}…\n"
            f"확인 필드 수: {row['confirmed_count']}"
        )
        _insert_textbox(
            page, meta,
            x=MARGIN_LEFT, y=y, width=content_w, height=60,
            fontsize=FONT_SIZE_BODY,
        )
        y += 70

        _insert_textbox(
            page, "사용자 확인 완료 필드",
            x=MARGIN_LEFT, y=y, width=content_w, height=22,
            fontsize=FONT_SIZE_BODY + 1,
        )
        y += 25

        lines = []
        for f in fields:
            label = f["label"] or f["key"]
            value = f["value"] or ""
            unit = f["unit"] or ""
            line = f"• {label}: {value} {unit}".rstrip()
            lines.append(line)

        _insert_textbox(
            page, "\n".join(lines),
            x=MARGIN_LEFT, y=y, width=content_w,
            height=PAGE_HEIGHT - y - MARGIN_BOTTOM - 30,
            fontsize=FONT_SIZE_BODY,
        )

        # 페이지 푸터.
        _insert_textbox(
            page,
            "본 페이지는 사용자 확인 필드만 표시합니다. "
            "원본의 시각 정보(서명·도장·계좌·연락처 등)는 포함되지 않습니다.",
            x=MARGIN_LEFT, y=PAGE_HEIGHT - MARGIN_BOTTOM,
            width=content_w, height=20,
            fontsize=FONT_SIZE_FOOTER, align=3,
        )
        count += 1

    return count


def _build_footer_page(doc: fitz.Document) -> None:
    page = _new_page(doc)
    content_w = PAGE_WIDTH - MARGIN_LEFT - MARGIN_RIGHT
    y = MARGIN_TOP

    _insert_textbox(
        page, "안내 및 면책",
        x=MARGIN_LEFT, y=y, width=content_w, height=30,
        fontsize=FONT_SIZE_HEADING,
    )
    y += 40

    _insert_textbox(
        page, PDF_DISCLAIMER,
        x=MARGIN_LEFT, y=y, width=content_w, height=300,
        fontsize=FONT_SIZE_BODY, align=3,
    )
    y += 320

    extra = (
        "외부 자문(2026-05-13) 권고에 따라, 본 PDF는 다음 원칙을 따릅니다.\n\n"
        "1. 분쟁용 문서가 아닙니다. 사용자 보관용 자료 요약본입니다.\n"
        "2. 원본 시각 정보를 포함하지 않습니다.\n"
        "3. 본 서비스는 분쟁 행동을 권유하지 않습니다.\n"
        "4. 본인의 결정으로 외부 기관·상담기관에 자료를 공유할 수 있으며, 그 경우 "
        "건별·기관별 별도 동의 절차가 적용됩니다."
    )
    _insert_textbox(
        page, extra,
        x=MARGIN_LEFT, y=y, width=content_w,
        height=PAGE_HEIGHT - y - MARGIN_BOTTOM,
        fontsize=FONT_SIZE_FOOTER, align=3,
    )


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------


def build_summary_pdf(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> bytes:
    """사용자 전체 자료 요약본을 PDF 바이트로 반환.

    내용:
      1. 표지 (제목·생성일·면책)
      2. 점수 페이지 (최신 스냅샷이 있을 때)
      3. 문서별 페이지 (확인된 필드만)
      4. 면책 푸터 페이지
    """
    doc = fitz.open()

    _build_cover_page(doc, user_id)

    score_row = conn.execute(
        "SELECT * FROM passport_scores WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
    if score_row:
        _build_score_page(doc, score_row)

    _build_document_pages(doc, conn, user_id)

    _build_footer_page(doc)

    output = io.BytesIO()
    doc.save(output)
    doc.close()
    return output.getvalue()


def suggested_filename(user_id: str) -> str:
    """다운로드 시 권장 파일명."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"energy_bill_summary_{user_id[:8]}_{stamp}.pdf"
