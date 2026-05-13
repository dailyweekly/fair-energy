"""마스킹 모듈 테스트 — 정책 04 §4."""

from __future__ import annotations

from core import masking


# --- RRN ---

def test_rrn_with_hyphen() -> None:
    assert masking.mask_rrn("900101-1234567") == "******-*******"


def test_rrn_without_hyphen() -> None:
    assert masking.mask_rrn("9001011234567") == "******-*******"


def test_rrn_in_sentence() -> None:
    out = masking.mask_rrn("주민번호는 900101-1234567 입니다.")
    assert "900101" not in out
    assert "1234567" not in out


# --- 전화 ---

def test_phone_hyphenated() -> None:
    assert masking.mask_phone("010-1234-5678") == "010-****-5678"


def test_phone_no_separator() -> None:
    assert masking.mask_phone("01012345678") == "010-****-5678"


def test_phone_with_spaces() -> None:
    assert masking.mask_phone("010 1234 5678") == "010-****-5678"


def test_phone_in_sentence() -> None:
    out = masking.mask_phone("연락처: 010-1234-5678")
    assert "1234" not in out
    assert "5678" in out


# --- 계좌 ---

def test_account_basic() -> None:
    assert masking.mask_account("123-45-67890") == "123-**-*****"


def test_account_longer() -> None:
    assert masking.mask_account("110-123-456789") == "110-***-******"


def test_account_too_short_not_masked() -> None:
    """1자리·1자리 같은 너무 짧은 패턴은 계좌로 보지 않는다."""
    assert masking.mask_account("1-2-3") == "1-2-3"


# --- 이메일 ---

def test_email_basic() -> None:
    out = masking.mask_email("abcde@example.com")
    assert out.startswith("a")
    assert "@example.com" in out
    assert "bcde" not in out


def test_email_short_local() -> None:
    """로컬파트가 짧아도 최소 2개의 ***은 들어간다."""
    out = masking.mask_email("ab@example.com")
    assert out == "a**@example.com"


# --- 주소 ---

def test_address_keeps_city_district() -> None:
    out = masking.mask_address("서울시 관악구 봉천동 123-45")
    assert out == "서울시 관악구 ***"


def test_address_with_special_city() -> None:
    out = masking.mask_address("부산광역시 해운대구 우동 1234")
    assert "부산광역시 해운대구" in out
    assert "우동" not in out
    assert "1234" not in out


def test_address_in_sentence() -> None:
    out = masking.mask_address(
        "주소는 경기도 성남시 분당구 정자동 123-45 입니다."
    )
    assert "정자동" not in out


# --- 한글 이름 ---

def test_mask_name_with_known_names() -> None:
    """알려진 이름이 주어지면 정확히 그 이름만 마스킹."""
    out = masking.mask_name("임차인 홍길동과 임대인 김철수", names=["홍길동", "김철수"])
    assert "홍**" in out
    assert "김**" in out
    assert "홍길동" not in out
    assert "김철수" not in out


def test_mask_name_2_chars() -> None:
    assert masking.mask_name("홍길", names=["홍길"]) == "홍*"


def test_mask_name_4_chars() -> None:
    assert masking.mask_name("홍길동민", names=["홍길동민"]) == "홍***"


# --- 통합 ---

def test_mask_text_combines_all() -> None:
    raw = (
        "임차인 홍길동(010-1234-5678, hong@example.com)이 "
        "서울시 관악구 봉천동 100-1에 거주, "
        "계좌 110-123-456789, 주민번호 900101-1234567."
    )
    out = masking.mask_text(
        raw,
        options=masking.MaskingOptions(names=("홍길동",)),
    )
    # 모두 마스킹됐는지.
    assert "홍길동" not in out
    assert "010-1234-5678" not in out
    assert "hong@example.com" not in out
    assert "봉천동" not in out
    assert "110-123-456789" not in out
    assert "900101" not in out
    # 보존되어야 할 부분.
    assert "임차인" in out
    assert "서울시 관악구" in out


def test_mask_text_idempotent() -> None:
    """마스킹된 텍스트를 다시 마스킹해도 결과가 변하지 않아야 한다."""
    raw = "010-1234-5678 / 900101-1234567"
    first = masking.mask_text(raw)
    second = masking.mask_text(first)
    assert first == second


# --- 원본 분리 invariant ---

def test_mask_text_does_not_mutate_input() -> None:
    raw = "010-1234-5678"
    _ = masking.mask_text(raw)
    assert raw == "010-1234-5678"  # 원본 변하지 않음
