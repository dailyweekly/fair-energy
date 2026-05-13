"""금지어 가드레일 테스트.

출시 게이트 G4 「법률 판단 금지어 필터 구현·통과」 직접 검증.
정책: docs/policies/01_output_language_policy.md
"""

from __future__ import annotations

import pytest

from core.guardrails import (
    SAFE_LABELS,
    STATIC_SAFE_DISCLAIMER_PHRASES,
    UnsafeOutputError,
    assert_safe_output,
    assert_safe_output_relaxed,
    get_safe_label,
    is_safe_output,
    is_safe_output_relaxed,
    scan_forbidden,
)


# --- 금지 표현은 반드시 검출되어야 한다 ---

FORBIDDEN_SAMPLES = [
    "임대인이 위반한 사항입니다.",
    "이것은 불법 청구입니다.",
    "부당청구입니다.",
    "부당 청구가 의심됩니다.",
    "부당 부과로 보입니다.",
    "임대인이 사기를 친 것입니다.",
    "환급 가능합니다.",
    "환급받을 수 있습니다.",
    "전액 돌려받을 수 있습니다.",
    "이 금액을 받을 수 있습니다.",
    "승소 가능성이 높습니다.",
    "고소를 진행하세요.",
    "고발하실 수 있습니다.",
    "한전에 신고하세요.",
    "소송하세요.",
    "소장을 작성해드립니다.",
    "내용증명을 발송합니다.",
    "내용 증명 예시입니다.",
    "법적으로 문제가 있는 청구입니다.",
    "임대인이 잘못한 경우입니다.",
    "임대인이 위법한 행위를 한 것입니다.",
    "로봇 변호사가 도와드립니다.",
    "가스라이팅으로 보입니다.",
    # 2026-05-13 외부 자문 반영 — 신규 금지 표현 6종
    "과다 청구로 보입니다.",
    "과다청구 가능성이 있습니다.",
    "법적 조치를 검토하세요.",
    "법적조치 안내드립니다.",
    "보상받을 수 있습니다.",
    "보상 가능합니다.",
    "부당이득 반환 청구가 가능합니다.",
    "반환해 주십시오.",
    "반환을 요구하세요.",
    "증거 패키지를 다운로드하세요.",
    "증거패키지 PDF를 생성합니다.",
]


@pytest.mark.parametrize("text", FORBIDDEN_SAMPLES)
def test_forbidden_text_is_detected(text: str) -> None:
    """금지 표현이 포함된 텍스트는 검출되어야 한다."""
    assert not is_safe_output(text), f"Expected forbidden, but passed: {text}"
    with pytest.raises(UnsafeOutputError):
        assert_safe_output(text)


# --- 허용 표현은 통과되어야 한다 ---

SAFE_SAMPLES = [
    "공식 산식과 큰 차이가 확인되지 않았습니다.",
    "공식 산식 기준 계산값과 사용자 청구액 사이에 차이가 확인됩니다.",
    "검산에 필요한 근거 자료가 부족합니다.",
    "AI 추출값에 사용자 확인이 필요합니다.",
    "현재 자료만으로는 검산할 수 없습니다.",
    "추가 자료가 필요합니다.",
    "산식 차이가 발생합니다.",
    "정산 재확인이 필요할 수 있습니다.",
    "검산 불가 / 근거 요청 필요 / 예비 검산 가능 / 공식 산식 비교 가능",
    "임대차계약서 사본이 필요합니다.",
    "검침 일자가 누락되어 있습니다.",
]


@pytest.mark.parametrize("text", SAFE_SAMPLES)
def test_safe_text_passes(text: str) -> None:
    """허용 표현은 가드레일을 통과해야 한다."""
    assert is_safe_output(text), f"Expected safe, but blocked: {text}"
    assert_safe_output(text)  # 예외 없이 통과


# --- SAFE_LABELS 자체 회귀 ---

def test_all_safe_labels_pass_guardrail() -> None:
    """SAFE_LABELS의 모든 라벨이 자기 자신의 가드레일을 통과해야 한다."""
    for key in SAFE_LABELS:
        # get_safe_label 내부에서 assert_safe_output을 호출하므로
        # 예외가 나오지 않는 것 자체가 검증.
        label = get_safe_label(key)
        assert label  # non-empty


# --- 부분 일치 안전성 ---

def test_partial_match_does_not_overshoot() -> None:
    """일반 단어 일부가 우연히 금지어와 겹치는 케이스에 대한 회귀.

    예: '소장'은 금지어, '소장료'(=수수료)는 의미가 달라 차단되면 안 됨.
    """
    # 소장이라는 단어 자체는 차단되어야 한다.
    assert not is_safe_output("소장 작성")
    # 가드레일이 '소장료' 단독은 차단하지 않도록 negative lookahead 처리되어 있다.
    assert is_safe_output("법원 인지액 및 소장료 안내")


def test_scan_returns_all_hits() -> None:
    """여러 금지어가 한 문장에 있으면 모두 검출."""
    hits = scan_forbidden("이는 부당청구이며 환급 가능합니다.")
    reasons = {h.reason for h in hits}
    assert "부당성 단정 표현" in reasons
    assert "환급 가능성 단정" in reasons


# ===========================================================================
# Round 4 — 완화 모드 (정적 면책 문구·정책 인용용)
# ===========================================================================


def test_relaxed_passes_disclaimer_negation() -> None:
    """정책 01 §4의 면책 문구는 relaxed 모드에서 통과해야 한다."""
    text = (
        "본 서비스는 법률 자문, 법률 의견, 소송 전략, "
        "환급 가능성 판단을 제공하지 않습니다."
    )
    assert is_safe_output_relaxed(text)
    assert_safe_output_relaxed(text)


def test_relaxed_still_blocks_real_forbidden_phrase() -> None:
    """relaxed 모드라도 화이트리스트에 없는 금지어는 차단해야 한다."""
    text = (
        "환급 가능성 판단을 제공하지 않습니다. "  # 화이트리스트
        "임대인이 위법한 청구를 하였습니다."           # 진짜 금지어
    )
    assert is_safe_output_relaxed(text) is False
    with pytest.raises(UnsafeOutputError):
        assert_safe_output_relaxed(text)


def test_relaxed_blocks_when_disclaimer_phrase_modified() -> None:
    """화이트리스트는 어휘 정확 일치만 허용 — 변형되면 차단."""
    # '환급 가능성을 판단합니다' 같은 긍정형은 통과되면 안 된다.
    text = "환급 가능성을 판단합니다."
    assert is_safe_output_relaxed(text) is False


def test_strict_mode_still_blocks_disclaimer_phrase() -> None:
    """엄격 모드는 면책 문구도 차단 (의도된 동작)."""
    text = "환급 가능성 판단을 제공하지 않습니다."
    assert is_safe_output(text) is False


def test_relaxed_passes_clean_text_unchanged() -> None:
    """완화 모드와 엄격 모드가 안전한 텍스트에서는 동일하게 통과."""
    text = "공식 산식 기준 계산값과 사용자 청구액 사이에 차이가 확인됩니다."
    assert is_safe_output(text) is True
    assert is_safe_output_relaxed(text) is True


def test_static_safe_phrases_are_negation_only() -> None:
    """화이트리스트의 모든 phrase는 그 자체로 금지어를 포함해야 한다.

    회귀 차단 — 누군가 화이트리스트에 안전한 일반 phrase를 넣으면
    실제 가드레일 효과가 떨어지므로, 위험한 phrase만 화이트리스트에 있는지 검증.
    """
    for phrase in STATIC_SAFE_DISCLAIMER_PHRASES:
        # 화이트리스트의 phrase는 엄격 모드에서 반드시 차단되어야 한다.
        # 그렇지 않으면 가드레일이 적용되는 일반 phrase를 우회시키는 셈.
        assert is_safe_output(phrase) is False, (
            f"화이트리스트 phrase가 일반 텍스트에서 차단되지 않음: {phrase}"
        )


# ===========================================================================
# Round 4 — 동적 출력 생성기 회귀
# ===========================================================================


def test_safety_disclaimers_pass_relaxed() -> None:
    """core/safety.py의 면책 문구가 relaxed 모드를 통과해야 한다."""
    from core import safety

    assert is_safe_output_relaxed(safety.DEFAULT_DISCLAIMER)
    assert is_safe_output_relaxed(safety.HIGH_RISK_DISCLAIMER)
    assert is_safe_output_relaxed(safety.VERY_HIGH_RISK_DISCLAIMER)


def test_ocr_system_prompt_is_exempt_from_guardrails() -> None:
    """OCR 시스템 프롬프트는 LLM 입력이지 사용자 출력이 아니므로 가드레일 면제.

    정책 01 §6 단서: 프롬프트는 LLM에게 금지를 지시하기 위해 금지어를
    명시적으로 인용해야 하므로, 가드레일 검증 대상에 포함하지 않는다.
    프롬프트는 별도의 `tests/test_prompts.py`에서 필수 문구 포함 여부만 검증한다.
    """
    from core.prompts import OCR_SYSTEM_PROMPT, MANDATORY_PHRASES

    # 필수 문구 5개가 포함되어 있음을 회귀 검증 (test_prompts.py와 별개 검증).
    for phrase in MANDATORY_PHRASES:
        assert phrase in OCR_SYSTEM_PROMPT


def test_case_descriptors_all_pass_strict() -> None:
    """모든 분류 디스크립터는 엄격 모드를 통과해야 한다."""
    from core.classification import CASE_DESCRIPTORS

    for case, descriptor in CASE_DESCRIPTORS.items():
        full_text = (
            f"{descriptor.headline}\n{descriptor.explanation}\n"
            + "\n".join(descriptor.next_actions)
        )
        assert is_safe_output(full_text), (
            f"디스크립터 가드레일 실패: {case.value}"
        )


def test_scoring_actions_pass_strict_for_all_tiers() -> None:
    """scoring._build_actions 결과가 모든 점수 구간에서 엄격 모드 통과."""
    from core.scoring import _build_actions

    # 4구간 + 빈/누락 케이스 조합 모두 점검.
    test_cases = [
        (0, ["임대차계약서"]),       # NOT_CALCULABLE
        (40, ["관리비"]),            # NEEDS_BASIS_REQUEST
        (70, ["배분 산식"]),         # PRELIMINARY
        (90, []),                    # OFFICIAL (누락 없음)
        (95, []),                    # OFFICIAL
    ]
    for total, missing in test_cases:
        actions = _build_actions(total, missing)
        joined = "\n".join(actions)
        assert is_safe_output(joined), (
            f"점수 {total}의 actions에서 가드레일 실패: {actions}"
        )


def test_redaction_text_summary_passes_strict() -> None:
    """build_text_summary가 안전한 입력에서 엄격 모드 통과."""
    from core.redaction import build_text_summary

    text = build_text_summary(
        document_id="doc-1",
        document_type="electricity_bill",
        original_filename="bill.pdf",
        fields=[
            {"key": "usage_kwh", "label": "사용량", "value": "245", "unit": "kWh"},
            {"key": "total_amount", "label": "청구액", "value": "38000",
             "unit": "KRW"},
        ],
    )
    assert is_safe_output(text), "마스킹본 텍스트가 가드레일 실패"


def test_safe_labels_strict_mode() -> None:
    """SAFE_LABELS 모든 값이 엄격 모드 통과."""
    for key, label in SAFE_LABELS.items():
        assert is_safe_output(label), f"SAFE_LABELS[{key}] 가드레일 실패: {label}"
