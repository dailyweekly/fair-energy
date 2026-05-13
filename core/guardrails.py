"""금지어 가드레일.

출시 게이트 G4 「법률 판단 금지어 필터 구현·통과」를 직접 통과시킨다.
정책: docs/policies/01_output_language_policy.md
"""

from __future__ import annotations

import re
from dataclasses import dataclass


class UnsafeOutputError(ValueError):
    """사용자 노출 텍스트에서 금지 표현이 검출되었을 때."""


@dataclass(frozen=True)
class GuardrailHit:
    pattern: str
    reason: str
    matched_text: str


# 정책 01_output_language_policy.md §2와 일치.
# 각 패턴은 (compiled_regex, 사람이 읽을 수 있는 이유) 쌍.
FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"위반"), "위법성 판단 표현"),
    (re.compile(r"불법"), "위법성 판단 표현"),
    (re.compile(r"부당\s*청구|부당청구"), "부당성 단정 표현"),
    (re.compile(r"부당\s*부과|부당부과"), "부당성 단정 표현"),
    (re.compile(r"부당\s*이득|부당이득"), "형사·민사 책임 단정 (2026-05-13)"),
    (re.compile(r"과다\s*청구|과다청구"), "부당성 단정 표현 (2026-05-13)"),
    (re.compile(r"반환[\s을를은이의]*요구|반환해|반환[\s을를]*하[세시]"), "분쟁 행동 유도 (2026-05-13)"),
    (re.compile(r"법적\s*조치|법적조치"), "분쟁 행동 단정 (2026-05-13)"),
    (re.compile(r"보상\s*가능|보상받을\s*수\s*있"), "결과 단정 (2026-05-13)"),
    (re.compile(r"사기"), "형사 책임 암시"),
    (re.compile(r"가스라이팅"), "단정 표현 (명예훼손 소지)"),
    (re.compile(r"환급\s*가능|환급받을\s*수\s*있"), "환급 가능성 단정"),
    (re.compile(r"돌려받을\s*수\s*있"), "결과 단정"),
    (re.compile(r"받을\s*수\s*있습니다"), "결과 단정"),
    (re.compile(r"승소"), "소송 결과 판단"),
    (re.compile(r"고소|고발"), "형사절차 유도"),
    (re.compile(r"신고하세요|신고하시"), "행동 단정"),
    (re.compile(r"소송하세요|소송하시"), "분쟁 행동 단정"),
    (re.compile(r"소장(?!료)"), "법률문서 작성 리스크"),  # '소장료'는 다른 의미라 제외
    (re.compile(r"내용\s*증명|내용증명"), "법률문서 작성 리스크"),
    (re.compile(r"증거\s*패키지|증거패키지"), "분쟁용 문서 오인 (2026-05-13)"),
    (re.compile(r"법적으로\s*문제"), "법률평가 표현"),
    (re.compile(r"임대인이\s*잘못"), "책임 단정"),
    (re.compile(r"임대인이\s*위법"), "위법성 단정"),
    (re.compile(r"위법한"), "위법성 단정 (2026-05-13 자문 반영)"),
    (re.compile(r"로봇\s*변호사"), "DoNotPay FTC 제재 사례 회피"),
]


def scan_forbidden(text: str) -> list[GuardrailHit]:
    """텍스트를 스캔하고 검출된 모든 금지 패턴을 반환한다."""
    hits: list[GuardrailHit] = []
    for pattern, reason in FORBIDDEN_PATTERNS:
        match = pattern.search(text)
        if match:
            hits.append(
                GuardrailHit(
                    pattern=pattern.pattern,
                    reason=reason,
                    matched_text=match.group(0),
                )
            )
    return hits


def is_safe_output(text: str) -> bool:
    """검출된 패턴이 없으면 True (엄격 모드).

    동적 LLM 출력·사용자 노출 텍스트 모두 본 함수로 검증해야 한다.
    예외: 정적 면책 문구처럼 부정 문맥에서 의도적으로 사용되는 표현은
    `is_safe_output_relaxed()`를 사용해야 한다.
    """
    return len(scan_forbidden(text)) == 0


def assert_safe_output(text: str) -> None:
    """검출 시 UnsafeOutputError를 발생시킨다 (엄격 모드).

    사용자에게 노출되는 모든 동적 텍스트는 이 함수를 통과해야 한다.
    """
    hits = scan_forbidden(text)
    if hits:
        details = ", ".join(f"{h.matched_text}({h.reason})" for h in hits)
        raise UnsafeOutputError(f"Unsafe output detected: {details}")


# ---------------------------------------------------------------------------
# 정적 면책 문구 화이트리스트 — Round 4 (2026-05-13)
# ---------------------------------------------------------------------------

# 부정/제한 문맥에서만 출현하며, 가드레일 완화 모드에서 차감되는 정적 phrase.
# 이 목록에 추가하려면 다음 조건을 모두 충족해야 한다:
#   1. 한 phrase 단위로 어휘적으로 일치해야 함 (변형·자유 작성 금지).
#   2. 부정/제한 문맥 안에서만 의미를 가져야 함 ("…하지 않습니다", "제공하지 않습니다" 등).
#   3. **그 자체가 엄격 모드 가드레일에 차단되는 표현이어야 함**.
#      (가드레일에 안 잡히는 일반 phrase가 들어 있으면 화이트리스트 의미가 사라짐)
#   4. 정적 상수 또는 정책 문서 인용 텍스트에만 사용. 동적 LLM 출력은 금지.
#
# 본 목록은 정책 01_output_language_policy.md §4(면책 문구)와 §6(가드레일 적용 의무)를
# 코드 차원에서 운영하기 위한 화이트리스트다.
#
# OCR 시스템 프롬프트(`core/prompts.OCR_SYSTEM_PROMPT`)는 LLM 입력이지 사용자 노출
# 출력이 아니므로 본 가드레일의 검증 대상이 아니다(정책 01 §6 단서 참조).
STATIC_SAFE_DISCLAIMER_PHRASES: tuple[str, ...] = (
    # DEFAULT_DISCLAIMER (정책 01 §4)
    "환급 가능성 판단을 제공하지 않습니다",
    "환급 가능성, 분쟁 결과는 판단하지 않습니다",
    "환급 가능성을 판단하지 않습니다",
    "위법성 여부, 환급 가능성",
    # HIGH/VERY_HIGH 디스크립터에 잠재적으로 등장 가능
    "환급 가능성을 제공하지 않습니다",
    # 정책 본문 인용 — Streamlit 페이지에 그대로 노출되는 경우
    "위법성·환급 가능성·분쟁 결과를 판단하지 않습니다",
    # 외부 자문 권고를 정책에 인용하는 경우 (정책 07 등)
    "위법, 부당, 환급 가능성, 승소 가능성, 신고 필요성을 판단하지 마세요",
    "위법, 부당, 환급 가능성, 승소 가능성, 신고 필요성, 분쟁 결과를 판단하지 마세요",
)


def is_safe_output_relaxed(text: str) -> bool:
    """정적 면책 문구·정책 인용용 완화 검사.

    `STATIC_SAFE_DISCLAIMER_PHRASES`에 포함된 phrase를 텍스트에서 먼저 제거하고
    남은 부분에 가드레일을 적용한다. 부정/제한 문맥에서만 출현하는 안전 표현을
    어휘 일치로 허용하여 false positive를 줄인다.

    동적 LLM 출력·사용자 자유 입력에는 절대 사용하지 말 것 — `is_safe_output()` 사용.
    """
    cleaned = text
    for phrase in STATIC_SAFE_DISCLAIMER_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    return is_safe_output(cleaned)


def assert_safe_output_relaxed(text: str) -> None:
    """`is_safe_output_relaxed()` 실패 시 UnsafeOutputError 발생.

    정적 면책 문구·정책 인용 텍스트의 회귀 검증용. 동적 출력에는 사용 금지.
    """
    cleaned = text
    for phrase in STATIC_SAFE_DISCLAIMER_PHRASES:
        cleaned = cleaned.replace(phrase, "")
    assert_safe_output(cleaned)


# 사용자 노출 라벨 단일 출처.
# 정책 01_output_language_policy.md §3과 일치.
SAFE_LABELS: dict[str, str] = {
    "MATCHED": "공식 산식과 큰 차이가 확인되지 않았습니다.",
    "DIFFERENCE_FOUND": "공식 산식 기준 계산값과 사용자 청구액 사이에 차이가 확인됩니다.",
    "INSUFFICIENT_BASIS": "검산에 필요한 근거 자료가 부족합니다.",
    "NEEDS_USER_CONFIRMATION": "AI 추출값에 사용자 확인이 필요합니다.",
    "NOT_CALCULABLE": "현재 자료만으로는 검산할 수 없습니다.",
    "PRELIMINARY_NOTICE": "이 결과는 일부 입력값이 누락된 상태에서의 예비 추정입니다.",
    "FIXED_FEE_NOTICE": "정액 관리비 케이스로 분류되어 산식 비교가 수행되지 않습니다.",
}


def get_safe_label(key: str) -> str:
    """SAFE_LABELS에서 키로 가져오되, assert_safe_output을 한 번 더 통과시킨다."""
    label = SAFE_LABELS[key]
    assert_safe_output(label)  # 라벨 자체가 향후 수정될 때 회귀 차단
    return label
