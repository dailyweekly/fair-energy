"""LLM 시스템 프롬프트가 정책 01 §5의 필수 문구를 보유하는지 검증.

이 회귀가 깨지면 G4(법률 판단 금지어 필터) 출시 게이트의 LLM 측 보호가 사라진다.
"""

from __future__ import annotations

from core import prompts
from core.guardrails import is_safe_output


def test_system_prompt_contains_all_mandatory_phrases() -> None:
    missing = prompts.validate_prompt_has_mandatory_phrases(prompts.OCR_SYSTEM_PROMPT)
    assert missing == [], f"Mandatory phrases missing from system prompt: {missing}"


def test_system_prompt_explicitly_forbids_legal_judgment() -> None:
    """프롬프트 자체가 LLM에게 위반·환급 등을 출력하지 말라고 지시해야 한다."""
    for term in prompts.FORBIDDEN_OUTPUT_TERMS:
        assert term in prompts.OCR_SYSTEM_PROMPT, (
            f"Forbidden term not declared in prompt: {term}"
        )


def test_user_prompt_with_hint() -> None:
    text = prompts.build_user_prompt("electricity_bill", hint="해상도 낮음")
    assert "electricity_bill" in text
    assert "해상도 낮음" in text


def test_user_prompt_without_hint() -> None:
    text = prompts.build_user_prompt("lease_contract")
    assert "lease_contract" in text


def test_mandatory_phrases_constant_not_emptied() -> None:
    """누군가 MANDATORY_PHRASES를 빈 튜플로 만들면 가드가 무력화된다 — 회귀 차단."""
    assert len(prompts.MANDATORY_PHRASES) >= 5
    # 핵심 키워드가 들어있는지 표면 검사.
    joined = "|".join(prompts.MANDATORY_PHRASES)
    assert "법률 판단" in joined
    assert "JSON" in joined
