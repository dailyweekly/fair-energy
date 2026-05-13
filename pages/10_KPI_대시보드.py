"""10. KPI 대시보드 — 관리자/운영자용.

PoC 진행 현황을 한 화면에서 확인. `ENABLE_ADMIN=true`인 경우에만 동작.
정책 06_poc_metrics_policy.md §2-A의 새 KPI 계층을 그대로 표시한다.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core import demo, metrics, ui
from core.auth import require_password
from core.models import CaseClassification


require_password()

st.set_page_config(
    page_title="KPI 대시보드 · 공정에너지",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed",
)

ui.inject_theme()

st.title("10. KPI 대시보드")


# ---------------------------------------------------------------------------
# 관리자 게이트
# ---------------------------------------------------------------------------

try:
    from app import app_config, conn  # type: ignore[attr-defined]
except Exception:
    st.error("앱 컨텍스트가 초기화되지 않았습니다.")
    st.stop()

if not app_config.enable_admin:
    st.warning(
        "관리자 모드가 비활성화되어 있습니다. "
        "`.env`에 `ENABLE_ADMIN=true`를 설정한 뒤 다시 실행해주세요."
    )
    st.caption(
        "본 대시보드는 운영자·NGO 케이스워커·심사위원 시연용입니다. "
        "익명·집계 통계만 표시되며, 임대인·임차인 식별정보는 노출되지 않습니다."
    )
    st.stop()


# ---------------------------------------------------------------------------
# 보고서 계산
# ---------------------------------------------------------------------------

report = metrics.compute_full_report(conn)

st.caption(
    "본 페이지는 익명·집계 KPI만 표시합니다. "
    "개인 식별정보는 노출되지 않습니다 (정책 04 §8)."
)


# ---------------------------------------------------------------------------
# 상단 요약
# ---------------------------------------------------------------------------

c1, c2, c3 = st.columns(3)
c1.metric("등록 사용자", report["summary"]["total_users_registered"])
c2.metric("누적 이벤트", report["summary"]["total_events"])
c3.metric(
    "Bill Passport 개설률",
    f"{report['secondary_kpis']['Bill_Passport_개설률']:.1%}",
)


# ---------------------------------------------------------------------------
# 1차 KPI (정책 06 §2-A)
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("1차 KPI — 사용자가 검산 가능한 상태에 가까워졌는가")

primary = report["primary_kpis"]
p1, p2, p3 = st.columns(3)
p1.metric(
    "완결성 점수 개선률 (평균)",
    f"{primary['1차_완결성_점수_개선률_평균_pct']:.1f}%",
)
p2.metric(
    "메시지 복사율 (근거 요청 케이스)",
    f"{primary['2차_메시지_복사율']:.1%}",
)
p3.metric(
    "재업로드율 (30일)",
    f"{primary['3차_재업로드율_30일']:.1%}",
)

st.caption(
    f"분석 대상 사용자: {primary['1차_분석_대상_사용자수']}명 · "
    f"개선: {primary['1차_개선_사용자수']}명 · "
    f"하락: {primary['1차_점수_하락_사용자수']}명 · "
    f"중앙값 개선률: {primary['1차_완결성_점수_개선률_중앙값_pct']:.1f}%"
)


# ---------------------------------------------------------------------------
# 보조 KPI
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("보조 KPI")

s1, s2 = st.columns(2)
s1.metric(
    "수동 입력 모드 사용률",
    f"{report['secondary_kpis']['수동_입력_모드_사용률']:.1%}",
)
s2.metric(
    "HIGH/VERY_HIGH 메시지 차단 횟수",
    report["secondary_kpis"]["HIGH_VERY_HIGH_차단_횟수"],
)
st.caption(
    "수동 입력 모드 사용률은 외부 LLM API 미동의 사용자 비율을 추적합니다. "
    "차단 횟수는 안전 설계가 실제로 작동했음을 의미합니다."
)


# ---------------------------------------------------------------------------
# 분류 분포 (정책 06 §6 목표 대비)
# ---------------------------------------------------------------------------

st.markdown("---")
st.subheader("분류 분포 — 정책 06 §6 기대값과 비교")

dist = report["classification_distribution"]
expected = {
    CaseClassification.NOT_CALCULABLE.value: 0.20,
    CaseClassification.NEEDS_BASIS_REQUEST.value: 0.60,
    CaseClassification.PRELIMINARY_CALCULATION.value: 0.15,
    CaseClassification.OFFICIAL_COMPARISON.value: 0.05,
    CaseClassification.FIXED_MANAGEMENT_FEE.value: 0.10,  # 별도 카운트
}

rows = []
for cls, expected_ratio in expected.items():
    count = dist["counts"].get(cls, 0)
    ratio = count / dist["total"] if dist["total"] else 0.0
    rows.append({
        "분류": cls,
        "실측 건수": count,
        "실측 비율": f"{ratio:.1%}",
        "기대 비율": f"{expected_ratio:.0%}",
    })
df = pd.DataFrame(rows)
st.dataframe(df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# 최근 이벤트 (디버그·운영용)
# ---------------------------------------------------------------------------

st.markdown("---")
with st.expander("최근 이벤트 50건 (운영 진단용)"):
    rows = metrics.list_events(conn, limit=50)
    if not rows:
        st.info("이벤트가 없습니다.")
    else:
        events_df = pd.DataFrame([dict(r) for r in rows])
        # 개인 식별성을 줄이기 위해 user_id 앞 6자만 노출.
        if "user_id" in events_df.columns:
            events_df["user_id"] = events_df["user_id"].fillna("").str.slice(0, 6) + "…"
        st.dataframe(events_df, use_container_width=True, hide_index=True)


# ---------------------------------------------------------------------------
# Export 안내
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption(
    "CSV·JSON export는 `python scripts/export_metrics.py --out reports/...` 명령으로 수행합니다. "
    "데모 데이터 생성은 `python scripts/create_demo_data.py --users 30 --reset`."
)
