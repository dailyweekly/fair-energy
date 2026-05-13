"""자료 확인 메시지 예시 (Phase 9 — 2026-05-13 외부 자문 반영).

정책 01 §8 + 외부 전문가 의견에 따라 사용자가 임대인에게 보낼 수 있는
메시지 예시를 제공한다. 본 모듈의 모든 출력은 정책 01 §2 금지어 필터를 통과한다.

⚠ 한계 사항 (LIMITATION):
- 본 모듈의 문구는 외부 전문가 검토 의견을 반영한 「추정 안전 영역」이다.
  화우 ESG센터의 실제 사전 검토 의견서(G5 게이트) 수령 후 재검토가 필요하다.
- 자동 발송 기능은 절대 추가하지 않는다.
- 메시지명은 「요청서」가 아닌 **「자료 확인 메시지 예시」**로 표기한다.
- 자동 채움은 「주소」·「청구 기간」 등 사용자 확인된 중립 사실값에 한정한다.
  청구액·임대인 이름·계좌·전화번호는 절대 자동 채우지 않는다.

허용 의도 (정책 01 §8.1):
- 정산 재확인 요청
- 자료 확인 요청
- 산식 공개 요청
- 검침일 확인 요청

금지 의도 (정책 01 §8.2):
- 금액 단정 ("X원 과다하게 청구되었습니다")
- 반환 요구 ("X원을 반환해 주십시오")
- 법적 조치 암시 ("법적 조치를 검토 중입니다")
- 분쟁 행동 예고 ("민원을 제기할 예정입니다")
- 위법성 단정 ("위법한 청구입니다")
- 임대인 신원 비난 ("임대인께서 잘못하셨습니다")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .guardrails import assert_safe_output
from .models import CaseClassification


# ---------------------------------------------------------------------------
# 템플릿 데이터 클래스
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MessageTemplate:
    """단일 메시지 예시.

    `body` 안의 플레이스홀더는 `{address}`, `{billing_period}` 두 개뿐이며,
    그 외 자동 채움은 의도적으로 제공하지 않는다(분쟁 단정 표현 차단).
    """

    key: str
    title: str
    purpose: str        # 사용 의도 (정책 01 §8.1)
    body: str
    applicable_to: tuple[str, ...]  # CaseClassification.value 목록


@dataclass(frozen=True)
class TemplateContext:
    """메시지 자동 채움에 사용할 컨텍스트.

    중립 사실값만 받는다. 사용자가 확인한 「주소」와 「청구 기간」 외 다른 필드는
    절대 자동 채우지 않는다.
    """

    address: Optional[str] = None        # 예: "○○구 ○○호실"
    billing_period: Optional[str] = None # 예: "2026-04-01 ~ 2026-04-30"


# ---------------------------------------------------------------------------
# 메시지 템플릿 (외부 자문 표현 범위 안)
# ---------------------------------------------------------------------------


MESSAGE_TEMPLATES: tuple[MessageTemplate, ...] = (
    MessageTemplate(
        key="data_request_basic",
        title="자료 확인 메시지 예시 (기본)",
        purpose="자료 확인 요청",
        body=(
            "안녕하세요.\n\n"
            "{address}에 거주 중인 임차인입니다.\n"
            "최근 받은 전기요금 청구와 관련하여 아래 자료를 확인하고 싶습니다.\n\n"
            "1. 해당 기간({billing_period})의 전기요금 고지서 사본\n"
            "2. 세대별 전기요금 배분 기준\n"
            "3. 제 호실에 적용된 사용량 또는 배분 산식\n"
            "4. 공용 전기료가 포함된 경우 그 산정 기준\n\n"
            "확인 가능한 범위에서 자료를 공유해 주시면 감사하겠습니다.\n"
            "감사합니다.\n"
        ),
        applicable_to=(
            CaseClassification.NEEDS_BASIS_REQUEST.value,
            CaseClassification.PRELIMINARY_CALCULATION.value,
        ),
    ),
    MessageTemplate(
        key="data_request_allocation",
        title="세대별 배분 산식 확인 메시지 예시",
        purpose="산식 공개 요청",
        body=(
            "안녕하세요.\n\n"
            "{address} 거주 임차인입니다.\n"
            "전기요금 청구 내역과 관련해 세대별 배분 기준을 알고 싶어 문의드립니다.\n\n"
            "다음 정보를 알려주실 수 있을까요?\n"
            "- 전체 건물 전기요금이 어떻게 측정되는지 (메인 계량기·보조 계량기 등)\n"
            "- 세대별 배분 방식 (사용량 기준 / 면적 기준 / 균등 분배 / 기타)\n"
            "- 공용 전기료의 산정 기준\n\n"
            "참고용으로 확인하려는 것이며, 정리되어 있는 범위에서 공유해 주시면 됩니다.\n"
            "감사합니다.\n"
        ),
        applicable_to=(
            CaseClassification.NEEDS_BASIS_REQUEST.value,
            CaseClassification.PRELIMINARY_CALCULATION.value,
        ),
    ),
    MessageTemplate(
        key="data_request_meter",
        title="검침일·계량기 확인 메시지 예시",
        purpose="검침일 확인 요청",
        body=(
            "안녕하세요.\n\n"
            "{address} 거주 임차인입니다.\n"
            "전기요금 검침일 기준을 확인하고 싶습니다.\n\n"
            "- 한전 검침일이 매월 며칠인지\n"
            "- 임대인 측 청구 기간이 한전 검침일과 동일한지\n"
            "- 검침일 기준 계량기 숫자 사진을 공유 가능한지\n\n"
            "감사합니다.\n"
        ),
        applicable_to=(
            CaseClassification.NEEDS_BASIS_REQUEST.value,
            CaseClassification.PRELIMINARY_CALCULATION.value,
        ),
    ),
    MessageTemplate(
        key="data_request_reconciliation",
        title="정산 재확인 메시지 예시",
        purpose="정산 재확인 요청",
        body=(
            "안녕하세요.\n\n"
            "{address} 거주 임차인입니다.\n"
            "최근 청구 기간({billing_period}) 전기요금 정산 내역을 함께 확인해 보고 싶습니다.\n\n"
            "- 해당 기간의 한전 공식 고지서 사본\n"
            "- 제 호실에 적용된 산정 내역\n"
            "- 정산 기준 시점의 계량기 검침 자료\n\n"
            "자료가 정리되어 있는 범위에서 공유해 주시면 감사하겠습니다.\n"
            "감사합니다.\n"
        ),
        applicable_to=(
            CaseClassification.NEEDS_BASIS_REQUEST.value,
            CaseClassification.PRELIMINARY_CALCULATION.value,
            CaseClassification.OFFICIAL_COMPARISON.value,
        ),
    ),
)


# ---------------------------------------------------------------------------
# 조회·렌더링
# ---------------------------------------------------------------------------


def list_applicable_templates(
    case: CaseClassification,
) -> list[MessageTemplate]:
    """주어진 분류에 적용 가능한 템플릿 목록.

    NOT_CALCULABLE·FIXED_MANAGEMENT_FEE는 빈 리스트를 반환한다 —
    검산 자체가 불가능한 케이스에서는 자료 요청이 사용자에게 의미가 적고,
    오히려 분쟁 행동으로 비칠 위험이 있다.
    """
    return [t for t in MESSAGE_TEMPLATES if case.value in t.applicable_to]


def render_template(
    template: MessageTemplate,
    context: TemplateContext,
) -> str:
    """플레이스홀더를 사용자 확인된 중립 사실값으로 치환.

    렌더 결과는 사용자가 자유 편집 가능하나, 본 함수가 출력하는 시점에서는
    `assert_safe_output()`을 통과한 안전한 텍스트만 반환된다.
    """
    rendered = template.body
    rendered = rendered.replace(
        "{address}", context.address or "○○구 ○○호실(직접 입력)",
    )
    rendered = rendered.replace(
        "{billing_period}",
        context.billing_period or "○○○○-○○-○○ ~ ○○○○-○○-○○ (직접 입력)",
    )
    assert_safe_output(rendered)
    return rendered


def validate_edited_message(text: str) -> None:
    """사용자가 편집한 메시지의 안전성 검증.

    편집 결과가 정책 01 §2 금지어 필터를 통과해야 「복사」 버튼이 활성된다.
    위반 시 `UnsafeOutputError`를 발생시켜 호출 측이 차단할 수 있게 한다.
    """
    assert_safe_output(text)


# ---------------------------------------------------------------------------
# 안내 문구
# ---------------------------------------------------------------------------


MESSAGE_PAGE_HEADER_NOTE = (
    "본 페이지의 메시지는 임대인에게 자료 확인을 요청할 때 참고할 수 있는 **예시**입니다. "
    "공정에너지는 자동 발송·자동 완성 기능을 제공하지 않으며, 분쟁 행동을 권유하지 않습니다. "
    "사용자가 본인 사실관계에 맞춰 직접 편집·복사하여 사용하시기 바랍니다."
)

MESSAGE_EDIT_GUIDANCE = (
    "메시지에는 다음 의도만 사용하실 수 있습니다: "
    "정산 재확인 / 자료 확인 / 산식 공개 / 검침일 확인.\n"
    "금액 단정·금전 청구 표현·분쟁 행동 암시는 자동 차단됩니다."
)
