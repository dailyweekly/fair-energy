"""Visual redaction 테스트 (Phase 8 Round 3).

정책 04 §5 — 마스킹본은 원본의 시각 정보를 포함하지 않고,
사용자가 직접 확인한 필드만으로 재생성된다.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from PIL import Image

from core import db, extraction, redaction, storage
from core.llm_client import DemoLLMClient


# ---------------------------------------------------------------------------
# fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> storage.DocumentStorage:
    return storage.DocumentStorage(
        key=Fernet.generate_key(),
        originals_dir=tmp_path / "originals",
        masked_dir=tmp_path / "masked",
    )


@pytest.fixture
def masked_dir(tmp_path: Path) -> Path:
    d = tmp_path / "masked"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _setup_with_confirmed_fields(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    *,
    doc_type: str = "electricity_bill",
) -> tuple[str, str]:
    """사용자·문서 생성 + OCR + 모든 필드 user_confirmed=1로 만든다."""
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
    # 모든 필드 확인.
    field_ids = [
        r["field_id"]
        for r in conn.execute(
            "SELECT field_id FROM extracted_fields WHERE document_id = ?",
            (stored.document_id,),
        )
    ]
    extraction.confirm_fields_bulk(conn, field_ids=field_ids)
    return user_id, stored.document_id


# ---------------------------------------------------------------------------
# build_text_summary
# ---------------------------------------------------------------------------


def test_summary_includes_title_and_metadata() -> None:
    md = redaction.build_text_summary(
        document_id="doc-xxxxxxxxxxxx",
        document_type="electricity_bill",
        original_filename="bill.png",
        fields=[],
    )
    assert "에너지 청구 자료 요약본" in md
    assert "electricity_bill" in md
    assert "bill.png" in md


def test_summary_lists_confirmed_fields() -> None:
    md = redaction.build_text_summary(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.png",
        fields=[
            {"key": "usage_kwh", "label": "사용량", "value": "245", "unit": "kWh"},
            {"key": "total_amount", "label": "청구액", "value": "38000",
             "unit": "KRW"},
        ],
    )
    assert "사용량" in md
    assert "245 kWh" in md
    assert "청구액" in md
    assert "38000 KRW" in md


def test_summary_excludes_source_text() -> None:
    """source_text는 절대 마스킹본에 포함되면 안 된다 (PII 유출 차단)."""
    # 일부러 fields dict에 source_text를 끼워 넣어도 무시되어야 한다.
    md = redaction.build_text_summary(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.png",
        fields=[
            {
                "key": "usage_kwh",
                "label": "사용량",
                "value": "245",
                "unit": "kWh",
                # 다음 필드는 build_text_summary가 무시해야 한다.
                "source_text": "임대인 홍길동(010-1234-5678) 명의 고지서",
            },
        ],
    )
    assert "홍길동" not in md
    assert "010-1234-5678" not in md
    assert "임대인" not in md  # source_text 영역 미포함


def test_summary_handles_empty_fields() -> None:
    md = redaction.build_text_summary(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.png",
        fields=[],
    )
    assert "아직 사용자가 확인한 필드가 없습니다" in md


def test_summary_includes_footer_disclaimer() -> None:
    md = redaction.build_text_summary(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.png",
        fields=[],
    )
    assert "시각 정보" in md
    assert "원본 접근" in md
    assert "법률 자문이 아니며" in md


# ---------------------------------------------------------------------------
# regenerate_masked_view
# ---------------------------------------------------------------------------


def test_regenerate_creates_file_and_updates_db(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    masked_dir: Path,
) -> None:
    user_id, doc_id = _setup_with_confirmed_fields(conn, store)

    masked_path = redaction.regenerate_masked_view(
        conn, document_id=doc_id, masked_dir=masked_dir,
    )
    assert masked_path is not None
    assert masked_path.exists()
    assert masked_path.suffix == ".md"

    row = conn.execute(
        "SELECT masked_path FROM documents WHERE document_id = ?", (doc_id,),
    ).fetchone()
    assert row["masked_path"] == str(masked_path)


def test_regenerate_returns_none_for_unconfirmed_fields(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    masked_dir: Path,
) -> None:
    """확인 안 된 필드만 있으면 마스킹본을 생성하지 않는다."""
    user_id = db.insert_user(conn)
    stored = store.save_document(
        conn,
        user_id=user_id,
        document_type="electricity_bill",
        original_filename="bill.png",
        original_bytes=b"FAKE",
        retention_months=6,
    )
    extraction.extract_and_save(
        conn,
        document_id=stored.document_id,
        document_type="electricity_bill",
        original_filename="bill.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    # 확인 안 함.

    result = redaction.regenerate_masked_view(
        conn, document_id=stored.document_id, masked_dir=masked_dir,
    )
    assert result is None


def test_regenerate_skips_manual_input_documents(
    conn: sqlite3.Connection,
    masked_dir: Path,
) -> None:
    """수동 입력 문서(original_path=NULL)는 마스킹본을 생성하지 않는다."""
    user_id = db.insert_user(conn)
    doc_id, _ = extraction.create_manual_document(
        conn,
        user_id=user_id,
        document_type="electricity_bill",
        fields={"usage_kwh": "245"},
    )

    result = redaction.regenerate_masked_view(
        conn, document_id=doc_id, masked_dir=masked_dir,
    )
    assert result is None


def test_regenerate_invalid_document_raises(
    conn: sqlite3.Connection, masked_dir: Path,
) -> None:
    with pytest.raises(ValueError):
        redaction.regenerate_masked_view(
            conn, document_id="nonexistent", masked_dir=masked_dir,
        )


def test_regenerate_content_has_no_source_text(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    masked_dir: Path,
) -> None:
    """저장된 source_text가 마스킹본 파일에 들어가지 않는다."""
    user_id, doc_id = _setup_with_confirmed_fields(conn, store)

    # demo fixture의 source_text 중 하나를 가져와 확인.
    source_texts = [
        r["source_text"]
        for r in conn.execute(
            "SELECT source_text FROM extracted_fields "
            "WHERE document_id = ? AND source_text IS NOT NULL",
            (doc_id,),
        )
        if r["source_text"]
    ]
    assert source_texts, "fixture에 source_text가 있어야 한다"

    masked_path = redaction.regenerate_masked_view(
        conn, document_id=doc_id, masked_dir=masked_dir,
    )
    content = masked_path.read_text(encoding="utf-8")
    for st in source_texts:
        assert st not in content, f"source_text leaked: {st}"


# ---------------------------------------------------------------------------
# regenerate_all_masked_views
# ---------------------------------------------------------------------------


def test_regenerate_all_processes_multiple_docs(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    masked_dir: Path,
) -> None:
    user_id, _ = _setup_with_confirmed_fields(conn, store)
    # 추가 문서 + 확인.
    stored2 = store.save_document(
        conn,
        user_id=user_id,
        document_type="lease_contract",
        original_filename="lease.png",
        original_bytes=b"FAKE",
        retention_months=6,
    )
    extraction.extract_and_save(
        conn,
        document_id=stored2.document_id,
        document_type="lease_contract",
        original_filename="lease.png",
        document_bytes=b"FAKE",
        llm_client=DemoLLMClient(),
    )
    rows = conn.execute(
        "SELECT field_id FROM extracted_fields WHERE document_id = ?",
        (stored2.document_id,),
    ).fetchall()
    extraction.confirm_fields_bulk(
        conn, field_ids=[r["field_id"] for r in rows],
    )

    count = redaction.regenerate_all_masked_views(
        conn, user_id=user_id, masked_dir=masked_dir,
    )
    assert count == 2


def test_regenerate_all_skips_no_confirmed(
    conn: sqlite3.Connection,
    store: storage.DocumentStorage,
    masked_dir: Path,
) -> None:
    user_id = db.insert_user(conn)
    # 업로드만, 확인 없음.
    store.save_document(
        conn,
        user_id=user_id,
        document_type="electricity_bill",
        original_filename="bill.png",
        original_bytes=b"FAKE",
        retention_months=6,
    )
    count = redaction.regenerate_all_masked_views(
        conn, user_id=user_id, masked_dir=masked_dir,
    )
    assert count == 0


# ---------------------------------------------------------------------------
# heavy_blur_image
# ---------------------------------------------------------------------------


def _make_png_bytes(color=(255, 0, 0), size=(40, 40)) -> bytes:
    from io import BytesIO

    img = Image.new("RGB", size, color)
    output = BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()


def test_heavy_blur_produces_valid_image() -> None:
    original = _make_png_bytes()
    blurred = redaction.heavy_blur_image(original, blur_radius=5)
    # Pillow가 다시 열 수 있어야 한다.
    from io import BytesIO

    img = Image.open(BytesIO(blurred))
    assert img.size == (40, 40)


def test_heavy_blur_changes_bytes() -> None:
    """블러 처리 후 바이트가 원본과 달라야 한다.

    단색 이미지는 블러해도 변화가 없으므로, 검은 사각형이 들어간
    이미지로 픽셀 변화를 보장한다.
    """
    from io import BytesIO

    img = Image.new("RGB", (40, 40), color=(255, 255, 255))
    # 한가운데 검은 사각형 → 블러 시 경계가 흐려짐.
    for x in range(15, 25):
        for y in range(15, 25):
            img.putpixel((x, y), (0, 0, 0))
    output = BytesIO()
    img.save(output, format="PNG")
    original = output.getvalue()

    blurred = redaction.heavy_blur_image(original, blur_radius=10)
    assert blurred != original
