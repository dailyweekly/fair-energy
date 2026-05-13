"""데모 데이터 생성 — Phase 10.

PoC 시연·KPI 대시보드 미리보기용.
실제 사용자 데이터가 없는 환경에서 분포 ·트렌드를 시각화할 수 있도록 한다.

실행:
  python scripts/create_demo_data.py [--users 30] [--reset]

`--reset`이면 기존 events·passport_scores·calculation_results 데이터를 삭제하고 새로 생성.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import config, db, metrics  # noqa: E402
from core.models import CaseClassification  # noqa: E402


# 정책 06 §6의 기대 분포에 가깝게 데모 데이터 생성.
COHORT_DISTRIBUTION = (("ngo", 0.4), ("general", 0.6))

CLASSIFICATION_DISTRIBUTION = (
    (CaseClassification.NOT_CALCULABLE.value, 0.20),
    (CaseClassification.NEEDS_BASIS_REQUEST.value, 0.55),
    (CaseClassification.PRELIMINARY_CALCULATION.value, 0.15),
    (CaseClassification.OFFICIAL_COMPARISON.value, 0.05),
    (CaseClassification.FIXED_MANAGEMENT_FEE.value, 0.05),
)


def _weighted_choice(items, rng: random.Random) -> str:
    r = rng.random()
    acc = 0.0
    for value, weight in items:
        acc += weight
        if r <= acc:
            return value
    return items[-1][0]


def _ts(offset_days: float, rng: random.Random) -> str:
    jitter = rng.uniform(-0.5, 0.5)
    return (
        datetime.now(timezone.utc) + timedelta(days=offset_days + jitter)
    ).isoformat(timespec="seconds")


def reset_demo_data(conn) -> None:
    """events·passport_scores·calculation_results의 데모 사용자 데이터를 삭제."""
    with db.transaction(conn):
        conn.execute("DELETE FROM events")
        conn.execute("DELETE FROM calculation_results")
        conn.execute("DELETE FROM passport_scores")
        # documents·users·consents는 보존(스토리지 데이터는 별도).


def create_demo_user(conn, *, rng: random.Random, days_ago: float) -> str:
    cohort = _weighted_choice(COHORT_DISTRIBUTION, rng)
    user_id = db.insert_user(conn, cohort=cohort)
    metrics.log_event(
        conn, event_name=metrics.EVENT_USER_REGISTERED,
        user_id=user_id, metadata={"cohort": cohort},
        timestamp=_ts(-days_ago, rng),
    )
    return user_id


def simulate_user_journey(
    conn, *, user_id: str, rng: random.Random, days_ago: float,
) -> None:
    """단일 사용자의 시뮬레이션 이벤트 + 점수 스냅샷 생성."""
    # 동의·안전 체크.
    metrics.log_event(
        conn, event_name=metrics.EVENT_CONSENT_COMPLETED,
        user_id=user_id, timestamp=_ts(-days_ago + 0.1, rng),
        metadata={"storage_months": rng.choice([6, 12, 36])},
    )
    safety_level = rng.choices(
        ["LOW", "MEDIUM", "HIGH", "VERY_HIGH"],
        weights=[0.55, 0.25, 0.15, 0.05], k=1,
    )[0]
    metrics.log_event(
        conn, event_name=metrics.EVENT_SAFETY_CHECK_COMPLETED,
        user_id=user_id, timestamp=_ts(-days_ago + 0.15, rng),
        metadata={"safety_level": safety_level},
    )

    # 첫 문서 업로드 (또는 수동 입력).
    use_manual = rng.random() < 0.15  # 15%는 수동 입력 모드.
    if use_manual:
        metrics.log_event(
            conn, event_name=metrics.EVENT_MANUAL_INPUT_USED,
            user_id=user_id, timestamp=_ts(-days_ago + 0.2, rng),
            metadata={"document_type": "electricity_bill"},
        )
    else:
        doc_count = rng.randint(1, 4)
        for _ in range(doc_count):
            metrics.log_event(
                conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED,
                user_id=user_id, timestamp=_ts(-days_ago + 0.2, rng),
                metadata={
                    "document_type": rng.choice([
                        "electricity_bill", "lease_contract",
                        "management_fee_notice", "meter_photo", "payment_proof",
                    ]),
                    "file_size": rng.randint(50_000, 800_000),
                },
            )

    # 분류.
    classification = _weighted_choice(CLASSIFICATION_DISTRIBUTION, rng)

    # 첫 점수 스냅샷.
    first_score = _initial_score_for_classification(classification, rng)
    _insert_score(conn, user_id, total=first_score,
                  ts=_ts(-days_ago + 0.3, rng))
    metrics.log_event(
        conn, event_name=metrics.EVENT_PASSPORT_CREATED,
        user_id=user_id, timestamp=_ts(-days_ago + 0.3, rng),
        metadata={"initial_score": first_score},
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_SCORE_CALCULATED,
        user_id=user_id, timestamp=_ts(-days_ago + 0.3, rng),
        metadata={"score": first_score, "missing_count": 0},
    )
    metrics.log_event(
        conn, event_name=metrics.EVENT_CASE_CLASSIFIED,
        user_id=user_id, timestamp=_ts(-days_ago + 0.3, rng),
        metadata={"classification": classification, "score": first_score},
    )

    # NEEDS_BASIS_REQUEST 사용자의 60%는 메시지 복사.
    if classification == CaseClassification.NEEDS_BASIS_REQUEST.value:
        if rng.random() < 0.6:
            metrics.log_event(
                conn, event_name=metrics.EVENT_REQUEST_TEMPLATE_COPIED,
                user_id=user_id, timestamp=_ts(-days_ago + 0.5, rng),
                metadata={"safety_level": safety_level},
            )

    # HIGH·VERY_HIGH 등급의 30%는 복사 차단 이벤트.
    if safety_level in ("HIGH", "VERY_HIGH"):
        if rng.random() < 0.3:
            metrics.log_event(
                conn, event_name=metrics.EVENT_HIGH_RISK_TEMPLATE_COPY_BLOCKED,
                user_id=user_id, timestamp=_ts(-days_ago + 0.5, rng),
                metadata={"safety_level": safety_level},
            )

    # 35%는 재업로드 + 점수 개선.
    if rng.random() < 0.35:
        days_later = rng.randint(3, min(28, max(3, int(days_ago) - 1)))
        improvement = rng.randint(10, 35)
        new_score = min(100, first_score + improvement)
        metrics.log_event(
            conn, event_name=metrics.EVENT_DOCUMENT_UPLOADED,
            user_id=user_id, timestamp=_ts(-days_ago + days_later, rng),
            metadata={"document_type": "electricity_bill",
                      "file_size": 200_000},
        )
        _insert_score(conn, user_id, total=new_score,
                      ts=_ts(-days_ago + days_later + 0.1, rng))
        metrics.log_event(
            conn, event_name=metrics.EVENT_SCORE_CALCULATED,
            user_id=user_id, timestamp=_ts(-days_ago + days_later + 0.1, rng),
            metadata={"score": new_score},
        )


def _initial_score_for_classification(
    classification: str, rng: random.Random,
) -> int:
    """분류값과 정합하는 시작 점수."""
    if classification == CaseClassification.NOT_CALCULABLE.value:
        return rng.randint(0, 39)
    if classification == CaseClassification.NEEDS_BASIS_REQUEST.value:
        return rng.randint(40, 69)
    if classification == CaseClassification.PRELIMINARY_CALCULATION.value:
        return rng.randint(70, 89)
    if classification == CaseClassification.OFFICIAL_COMPARISON.value:
        return rng.randint(90, 100)
    # FIXED_MANAGEMENT_FEE는 점수 무관 — 중간값 사용.
    return rng.randint(30, 70)


def _insert_score(conn, user_id: str, *, total: int, ts: str) -> None:
    score_id = db.new_id()
    with db.transaction(conn):
        conn.execute(
            """
            INSERT INTO passport_scores (
                score_id, user_id, total_score, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (score_id, user_id, total, ts),
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate demo KPI data.")
    parser.add_argument("--users", type=int, default=30,
                        help="Number of demo users to create (default: 30).")
    parser.add_argument("--reset", action="store_true",
                        help="Clear existing events/scores before generating.")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility.")
    parser.add_argument("--db", type=str, default=None,
                        help="Override DB path.")
    args = parser.parse_args()

    cfg = config.load_config()
    db_path = Path(args.db) if args.db else cfg.db_path
    conn = db.init_db(db_path)

    if args.reset:
        reset_demo_data(conn)
        print(f"[reset] events/scores cleared in {db_path}")

    rng = random.Random(args.seed)
    for i in range(args.users):
        days_ago = rng.uniform(1, 89)  # 최근 3개월에 걸쳐 분포.
        user_id = create_demo_user(conn, rng=rng, days_ago=days_ago)
        simulate_user_journey(conn, user_id=user_id, rng=rng,
                              days_ago=days_ago)
    print(f"[done] generated {args.users} demo users in {db_path}")

    # 간단 요약.
    report = metrics.compute_full_report(conn)
    print("\n=== Summary ===")
    print(f"Registered users: {report['summary']['total_users_registered']}")
    print(f"Total events: {report['summary']['total_events']}")
    print("\n=== Primary KPIs ===")
    for k, v in report["primary_kpis"].items():
        print(f"  {k}: {v}")
    print("\n=== Classification distribution ===")
    for cls, c in report["classification_distribution"]["counts"].items():
        print(f"  {cls}: {c}")


if __name__ == "__main__":
    main()
