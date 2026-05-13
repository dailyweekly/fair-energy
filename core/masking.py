"""개인정보 마스킹.

정책 04 §4 규칙의 단일 구현. 표시용 사본·LLM 추출 결과·UI 노출 텍스트 모두 본 모듈로 통일.

원본 텍스트(파일 내용)에는 마스킹을 적용하지 않는다 — 원본/마스킹본 분리(정책 04 §1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 패턴 — 정책 04 §4
# ---------------------------------------------------------------------------

# 주민등록번호: YYMMDD-NNNNNNN (하이픈/공백 허용)
RRN_PATTERN = re.compile(r"\b(\d{6})[-\s]?(\d{7})\b")


def detect_rrn(text: str) -> bool:
    """텍스트에 주민등록번호 패턴이 포함되어 있는지 감지.

    정책 04 §9 (2026-05-13 외부 자문 반영) — 감지 시 업로드를 거부하고
    사용자에게 "해당 부분을 가린 후 다시 업로드해 주세요" 안내를 표시한다.
    """
    if not text:
        return False
    return RRN_PATTERN.search(text) is not None

# 휴대전화: 01X-NNNN-NNNN (하이픈/공백/없음 허용)
PHONE_PATTERN = re.compile(r"\b(01[016789])[-\s]?(\d{3,4})[-\s]?(\d{4})\b")

# 일반 전화: 0X(X)-NNN(N)-NNNN
LANDLINE_PATTERN = re.compile(r"\b(0\d{1,2})[-\s]?(\d{3,4})[-\s]?(\d{4})\b")

# 계좌번호: 3~6 / 2~6 / 5~9 자리 (-구분). 길이가 너무 짧으면 매치 안 함.
ACCOUNT_PATTERN = re.compile(r"\b(\d{2,6})-(\d{2,6})-(\d{5,9})\b")

# 이메일: 단순 패턴.
EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9_.+-])([A-Za-z0-9_.+-]*)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

# 한글 이름: 2~5자. 앞뒤가 한글이 아닐 때만 매치(부분어 보호).
NAME_PATTERN = re.compile(r"(?<![가-힣])([가-힣]{2,5})(?![가-힣])")

# 주소: '시'/'도' + '구'/'군' + 이후 상세. 시·구 단위는 보존, 그 이후 마스킹.
ADDRESS_PATTERN = re.compile(
    r"((?:서울특별시|서울시|서울|부산광역시|부산|대구광역시|대구|"
    r"인천광역시|인천|광주광역시|광주|대전광역시|대전|울산광역시|울산|"
    r"세종특별자치시|세종|경기도|경기|강원특별자치도|강원도|강원|"
    r"충청북도|충북|충청남도|충남|전북특별자치도|전라북도|전북|전라남도|전남|"
    r"경상북도|경북|경상남도|경남|제주특별자치도|제주)\s*"
    r"[가-힣]+(?:구|군|시))"
    r"(\s+[^\n,]+)"
)


# 한국에 흔한 성씨(이름 마스킹의 오탐을 줄이는 보조 — 화이트리스트 아님).
# 너무 일반적인 단어가 이름으로 잡히지 않도록 NAME_PATTERN 적용 전에
# `mask_name`에서 별도 필터를 둘 수도 있으나, 정책 04 §4는 일률 마스킹.
# 본 모듈에서는 NAME_PATTERN 호출은 `mask_name`을 명시적으로 부르는 경로에서만 사용한다.


# ---------------------------------------------------------------------------
# 마스킹 헬퍼
# ---------------------------------------------------------------------------


def _mask_korean_name(name: str) -> str:
    """한글 이름 마스킹: 첫 글자만 노출, 나머지 *.

    홍길 → 홍*, 홍길동 → 홍**, 홍길동민 → 홍***
    """
    if not name:
        return name
    return name[0] + "*" * (len(name) - 1)


def mask_rrn(text: str) -> str:
    """주민등록번호 전체 마스킹: 900101-1234567 → ******-*******"""
    return RRN_PATTERN.sub(lambda m: "*" * len(m.group(1)) + "-" + "*" * len(m.group(2)), text)


def mask_phone(text: str) -> str:
    """휴대전화: 가운데 번호만 마스킹.

    010-1234-5678 → 010-****-5678, 01012345678 → 010-****-5678
    """
    def _sub(m: re.Match[str]) -> str:
        prefix, middle, last = m.group(1), m.group(2), m.group(3)
        return f"{prefix}-{'*' * len(middle)}-{last}"

    return PHONE_PATTERN.sub(_sub, text)


def mask_account(text: str) -> str:
    """계좌번호: 가운데와 마지막 영역의 숫자를 마스킹.

    123-45-67890 → 123-**-*****
    """
    def _sub(m: re.Match[str]) -> str:
        a, b, c = m.group(1), m.group(2), m.group(3)
        return f"{a}-{'*' * len(b)}-{'*' * len(c)}"

    return ACCOUNT_PATTERN.sub(_sub, text)


def mask_email(text: str) -> str:
    """이메일: 로컬파트의 첫 글자만 노출.

    abcde@example.com → a****@example.com
    """
    def _sub(m: re.Match[str]) -> str:
        first, rest, domain = m.group(1), m.group(2), m.group(3)
        return f"{first}{'*' * max(2, len(rest))}@{domain}"

    return EMAIL_PATTERN.sub(_sub, text)


def mask_address(text: str) -> str:
    """주소: 시/도 + 구/군까지만 보존, 이후는 ***로 대체.

    서울시 관악구 봉천동 123-45 → 서울시 관악구 ***
    """
    return ADDRESS_PATTERN.sub(lambda m: f"{m.group(1)} ***", text)


def mask_name(text: str, names: list[str] | None = None) -> str:
    """한글 이름 마스킹.

    `names`가 주어지면 그 이름만 정확히 치환한다(권장 사용법: 컨텍스트에서 알려진 이름).
    `names`가 없으면 한글 2~5자 패턴을 일률 마스킹한다 — 오탐 가능성에 유의.
    """
    if names:
        result = text
        for n in names:
            if not n:
                continue
            result = result.replace(n, _mask_korean_name(n))
        return result

    return NAME_PATTERN.sub(lambda m: _mask_korean_name(m.group(1)), text)


# ---------------------------------------------------------------------------
# 통합 진입점
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaskingOptions:
    rrn: bool = True
    phone: bool = True
    account: bool = True
    email: bool = True
    address: bool = True
    names: tuple[str, ...] = ()  # 알려진 이름(임차인·임대인)이 있으면 전달


DEFAULT_OPTIONS = MaskingOptions()


def mask_text(text: str, options: MaskingOptions = DEFAULT_OPTIONS) -> str:
    """모든 규칙을 순서대로 적용한 마스킹 결과를 반환한다.

    RRN을 가장 먼저 처리해 13자리 숫자가 전화·계좌 패턴에 잡히는 것을 막는다.
    """
    if not text:
        return text

    result = text
    if options.rrn:
        result = mask_rrn(result)
    if options.account:
        result = mask_account(result)
    if options.phone:
        result = mask_phone(result)
    if options.email:
        result = mask_email(result)
    if options.address:
        result = mask_address(result)
    if options.names:
        result = mask_name(result, names=list(options.names))

    return result
