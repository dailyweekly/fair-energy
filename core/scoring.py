"""Energy Bill Completeness Score.

정책 02 §2 배점 (총 100점):
  - 임대차계약서 보유                15
  - 관리비 항목별 내역 보유          15
  - 계량기 사진·검침일 보유          15
  - 한전 원고지서 또는 임대인 원고지서 25
  - 임대인의 세대별 배분 산식 보유   20
  - 납부내역·계좌이체 기록 보유      10

추가 게이트(정책 02 §4):
  - 점수만으로 OFFICIAL_COMPARISON 보장 X.
  - 필수 필드(usage/dates/amount/contract)가 confirmed 상태여야 함.

본 모듈은 "점수 계산"과 "TariffInput 빌더"만 담당한다.
실제 케이스 분류는 core/classification.classify_case가 수행한다.
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from typing import Optional

from . import db, extraction
from .models import (
    CaseClassification,
    CompletenessScore,
    DocumentType,
    TariffInput,
)


# ---------------------------------------------------------------------------
# 배점 상수 — 정책 02 §2
# ---------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "lease_contract": 15,
    "itemized_fee_notice": 15,
    "meter_photo_with_date": 15,
    "original_electricity_bill": 25,
    "allocation_formula": 20,
    "payment_proof": 10,
}
assert sum(SCORE_WEIGHTS.values()) == 100  # 회귀 차단


ALLOCATION_KEYS = ("allocation_method", "allocation_formula", "household_count")

# "사실상 정보 없음"을 의미하는 값 — allocation에서 점수 차감 트리거.
NEGATIVE_VALUES = {"미기재", "없음", "미상", "없습니다", "모름", ""}


# 룰 엔진 호출에 필요한 키 — 필드 게이트.
REQUIRED_TARIFF_FIELD_KEYS = (
    "usage_kwh",
    "billing_start_date",
    "billing_end_date",
    "total_amount",       # → TariffInput.user_charged_amount
    "contract_type",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _index_by_doc_type(docs: list[dict]) -> dict[str, list[dict]]:
    """문서 유형별로 entry를 묶는다."""
    idx: dict[str, list[dict]] = defaultdict(list)
    for entry in docs:
        idx[entry["document"]["document_type"]].append(entry)
    return idx


def _confirmed_value(field: sqlite3.Row) -> Optional[str]:
    """user_confirmed=1이고 의미 있는 value면 반환, 그 외 None."""
    if not field["user_confirmed"]:
        return None
    value = field["value"]
    if value is None or value in NEGATIVE_VALUES:
        return None
    return value


def _has_confirmed_field(entries: list[dict], *, keys: tuple[str, ...]) -> bool:
    for entry in entries:
        for field in entry["fields"]:
            if field["key"] in keys and _confirmed_value(field) is not None:
                return True
    return False


def _has_confirmed_allocation_anywhere(docs: list[dict]) -> bool:
    for entry in docs:
        for field in entry["fields"]:
            if field["key"] in ALLOCATION_KEYS and _confirmed_value(field) is not None:
                return True
    return False


def _kv_confirmed(docs: list[dict]) -> dict[str, str]:
    """모든 문서에서 user_confirmed=1인 필드를 key → value 맵으로."""
    kv: dict[str, str] = {}
    for entry in docs:
        for field in entry["fields"]:
            value = _confirmed_value(field)
            if value is not None:
                kv[field["key"]] = value
    return kv


# ---------------------------------------------------------------------------
# 점수 계산
# ---------------------------------------------------------------------------


def compute_completeness_score(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> CompletenessScore:
    """6개 카테고리 배점을 합산해 CompletenessScore를 반환."""
    docs = extraction.list_user_documents_with_fields(conn, user_id=user_id)
    by_type = _index_by_doc_type(docs)

    breakdown = dict.fromkeys(SCORE_WEIGHTS.keys(), 0)
    missing: list[str] = []

    # 1) 임대차계약서 (15)
    if DocumentType.LEASE_CONTRACT.value in by_type:
        breakdown["lease_contract"] = SCORE_WEIGHTS["lease_contract"]
    else:
        missing.append("임대차계약서")

    # 2) 관리비 항목별 내역 (15)
    if DocumentType.MANAGEMENT_FEE_NOTICE.value in by_type:
        breakdown["itemized_fee_notice"] = SCORE_WEIGHTS["itemized_fee_notice"]
    else:
        missing.append("관리비 항목별 내역")

    # 3) 계량기 사진·검침일 (15)
    if DocumentType.METER_PHOTO.value in by_type:
        has_date = _has_confirmed_field(
            by_type[DocumentType.METER_PHOTO.value],
            keys=("photo_date", "meter_reading"),
        )
        if has_date:
            breakdown["meter_photo_with_date"] = SCORE_WEIGHTS["meter_photo_with_date"]
        else:
            missing.append(
                "계량기 사진의 검침일·숫자를 사용자가 확인해주세요"
            )
    else:
        missing.append("계량기 사진 (검침일 포함)")

    # 4) 원고지서 (25) — 한전 또는 임대인 측 원고지서
    if (DocumentType.ELECTRICITY_BILL.value in by_type
            or DocumentType.LANDLORD_NOTICE.value in by_type):
        breakdown["original_electricity_bill"] = SCORE_WEIGHTS["original_electricity_bill"]
    else:
        missing.append("한전 또는 임대인 측 원고지서 사본")

    # 5) 세대별 배분 산식 (20)
    if _has_confirmed_allocation_anywhere(docs):
        breakdown["allocation_formula"] = SCORE_WEIGHTS["allocation_formula"]
    else:
        missing.append("임대인의 세대별 배분 산식")

    # 6) 납부내역 (10)
    if DocumentType.PAYMENT_PROOF.value in by_type:
        breakdown["payment_proof"] = SCORE_WEIGHTS["payment_proof"]
    else:
        missing.append("납부내역 또는 계좌이체 기록")

    total = sum(breakdown.values())
    actions = _build_actions(total, missing)

    return CompletenessScore(
        **breakdown,
        total_score=total,
        missing_items=missing,
        available_actions=actions,
    )


def _build_actions(total: int, missing: list[str]) -> list[str]:
    """점수 구간별 가능한 다음 액션 목록.

    정책 02 §3 4구간과 정렬된다.
    """
    actions: list[str] = []

    if missing:
        actions.append("부족한 자료를 추가 업로드")

    if total < 40:
        actions.append("자료 체크리스트를 먼저 확보하세요")
    elif total < 70:
        actions.append("임대인에게 보낼 자료요청 메시지 예시 확인")
    elif total < 90:
        actions.append("예비 검산 결과 확인 (필수 필드 누락 시 결과 달라질 수 있음)")
    else:
        actions.append("공식 산식 비교 결과 확인 (필수 필드 모두 확인 시)")

    actions.append("에너지 청구 자료 요약본 PDF 다운로드 (다음 단계에서 활성화)")
    return actions


# ---------------------------------------------------------------------------
# TariffInput 빌더 — 룰 엔진 호출 직전 단계
# ---------------------------------------------------------------------------


def build_tariff_input(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> TariffInput:
    """user_confirmed=True 필드만 모아 TariffInput을 만든다.

    필수 필드(REQUIRED_TARIFF_FIELD_KEYS)가 모두 확인되어 있으면
    `user_confirmed=True`로 반환되어, 분류 단계에서 OFFICIAL_COMPARISON
    경로가 열린다.
    """
    docs = extraction.list_user_documents_with_fields(conn, user_id=user_id)
    kv = _kv_confirmed(docs)

    def _as_float(key: str) -> Optional[float]:
        if key not in kv:
            return None
        try:
            return float(str(kv[key]).replace(",", ""))
        except ValueError:
            return None

    def _as_int(key: str) -> Optional[int]:
        v = _as_float(key)
        return int(v) if v is not None else None

    all_required_present = all(k in kv for k in REQUIRED_TARIFF_FIELD_KEYS)

    return TariffInput(
        usage_kwh=_as_float("usage_kwh"),
        billing_start_date=kv.get("billing_start_date"),
        billing_end_date=kv.get("billing_end_date"),
        contract_type=kv.get("contract_type"),
        household_count=_as_int("household_count"),
        user_charged_amount=_as_int("total_amount"),
        allocation_formula=kv.get("allocation_method") or kv.get("allocation_formula"),
        user_confirmed=all_required_present,
    )


# ---------------------------------------------------------------------------
# 정액 관리비 케이스 감지 — 정책 02 §3
# ---------------------------------------------------------------------------


def detect_fixed_fee(conn: sqlite3.Connection, *, user_id: str) -> bool:
    """전기료가 관리비에 포함된 정액 케이스인지 감지.

    감지 신호:
      - lease_contract의 electricity_separate=='포함' 또는 'included'
      - lease_contract의 management_fee가 있고 electricity_separate가 빈 경우는 미감지(보수적).
    사용자가 명시적으로 확인한 필드만 신호로 사용한다.
    """
    docs = extraction.list_user_documents_with_fields(conn, user_id=user_id)
    for entry in docs:
        if entry["document"]["document_type"] != DocumentType.LEASE_CONTRACT.value:
            continue
        for field in entry["fields"]:
            if field["key"] != "electricity_separate":
                continue
            value = _confirmed_value(field)
            if value is None:
                continue
            if value.strip().lower() in {"포함", "included", "yes", "true"}:
                return True
    return False


# ---------------------------------------------------------------------------
# 스냅샷 저장
# ---------------------------------------------------------------------------


def save_score_snapshot(
    conn: sqlite3.Connection,
    *,
    user_id: str,
    score: CompletenessScore,
) -> str:
    """점수를 passport_scores 테이블에 한 행으로 보관."""
    score_id = db.new_id()
    now = db.utcnow_iso()
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO passport_scores (
                score_id, user_id,
                lease_contract, itemized_fee_notice, meter_photo_with_date,
                original_electricity_bill, allocation_formula, payment_proof,
                total_score, missing_items_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                score_id, user_id,
                score.lease_contract, score.itemized_fee_notice,
                score.meter_photo_with_date, score.original_electricity_bill,
                score.allocation_formula, score.payment_proof,
                score.total_score,
                json.dumps(score.missing_items, ensure_ascii=False),
                now,
            ),
        )
    return score_id


def latest_score(
    conn: sqlite3.Connection,
    *,
    user_id: str,
) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM passport_scores WHERE user_id = ? "
        "ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()
