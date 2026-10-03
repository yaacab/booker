"""Deterministic, ticket-safe support assistant for the first production stage."""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SupportAgentReply:
    assistant_message: str
    intent: str
    outcome: str
    needs_human: bool
    source_ids: tuple[str, ...]


_HUMAN_REQUEST = (
    "оператор",
    "человек",
    "живой специалист",
    "позовите поддержку",
    "передайте специалисту",
)
_MONEY_OR_LEGAL = (
    "возврат",
    "верните деньги",
    "спор",
    "претенз",
    "суд",
    "юрист",
    "договор",
    "компенсац",
    "выплат",
    "мошен",
    "платёж",
    "платеж",
    "оплат",
    "чек",
)
_SECURITY = (
    "взлом",
    "украли аккаунт",
    "чужой вход",
    "утечк",
    "пароль укра",
    "не мой вход",
)
_EVENT_DAY_NO_SHOW = (
    "сорвал событие",
    "сорвано событие",
    "срыв даты",
)
_PERFORMER = (
    r"(?:исполнител\w*|артист\w*|ведущ\w*|дидже\w*|dj|фотограф\w*|музыкант\w*|подрядчик\w*)"
)
_NOT_ARRIVED = r"(?:не\s+приехал[а]?|не\s+приш[её]л|не\s+пришла|не\s+явил(?:ся|ась|ись)|не\s+появил(?:ся|ась|ись))"
_PERFORMER_NO_SHOW = re.compile(
    rf"\b(?:{_PERFORMER}\s+(?:(?:так\s+и|сегодня|вовремя|на\s+(?:событие|мероприятие|площадку))\s+){{0,3}}{_NOT_ARRIVED}"
    rf"|{_NOT_ARRIVED}\s+{_PERFORMER}|неявк\w*\s+{_PERFORMER}|{_PERFORMER}\s+неявк\w*)\b",
    re.IGNORECASE,
)
_NO_SHOW_RESOLVED_IN_MESSAGE = re.compile(
    r"\b(?:но\s+)?(?:затем|потом|позже)\s+приехал[а]?\s+и\s+(?:выступил[а]?|отработал[а]?)\b",
    re.IGNORECASE,
)
_ARRIVAL_PROBLEM = ("не приехал", "не приехала", "не пришёл", "не пришел", "не пришла")
_CODE_DELIVERY = ("не пришёл код", "не пришел код", "код не пришёл", "код не пришел")
_PAID_MARKERS = (
    "оплата прошла",
    "оплатил",
    "оплатила",
    "деньги списали",
    "деньги списаны",
    "перевод учтён",
    "перевод учтен",
)
_NOT_CONFIRMED_MARKERS = (
    "бронь не подтвержд",
    "не confirmed",
    "не подтверждена",
    "не подтверждено",
    "awaitingpayment",
    "awaiting payment",
)
_PERFORMER_CANCELLED_EVENT = re.compile(
    rf"\b{_PERFORMER}\s+(?:внезапно\s+)?(?:отменил[а]?|отказал(?:ся|ась)\s+от)\s+"
    r"(?:сво[её]\s+)?(?:выступлени\w*|участия\s+в\s+(?:событии|мероприятии))\b",
    re.IGNORECASE,
)
_CARD_CHARGE_PENDING_BOOKING = re.compile(
    r"\b(?:с\s+карты\s+списали(?:\s+деньги)?|деньги\s+списали\s+с\s+карты|"
    r"списали\s+деньги\s+с\s+карты)\b",
    re.IGNORECASE,
)
_BOOKING_AWAITS_PAYMENT = re.compile(
    r"\bброн\w*\s+(?:вс[её]\s+ещ[её]\s+)?(?:ожидает\s+оплаты|в\s+ожидании\s+оплаты)\b",
    re.IGNORECASE,
)
_DOUBLE_CONFIRMED_SLOT = re.compile(
    r"\b(?:две|2)\s+подтвержд[её]нн\w*\s+брон\w*\s+на\s+"
    r"(?:один\s+и\s+тот\s+же|один|тот\s+же)\s+слот\b",
    re.IGNORECASE,
)


def _has_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)


_SECRET_VALUE = (
    r"(?!(?:не\s+[а-яё]+|not\s+[a-z]+|ист[её]к|просрочен|expired|invalid)\b)"
    r"(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|“[^”\r\n]*”|\S+)"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(?:пароль(?:\s+для\s+входа)?|password|otp|totp|"
    r"код(?:\s+(?:из\s+sms|подтверждения))?|api[_\s-]?key)\b"
    rf"\s*(?:[:=—–-]|\bis\b|\bэто\b)\s*{_SECRET_VALUE}"
)
_BARE_PASSWORD_VALUE = re.compile(
    r"(?i)\b(?:пароль(?:\s+для\s+входа)?|password)\b\s+"
    r"(?:(?:\"[^\"\r\n]*\"|'[^'\r\n]*'|“[^”\r\n]*”)|"
    r"(?=\S*\d)[a-z0-9!@#$%^&*_-]{5,})"
)
_TOKEN_LABEL = r"(?:токен(?:\s+(?:доступа|авторизации|сессии))?|(?:access\s+)?token)"
_TOKEN_ASSIGNMENT = re.compile(
    rf"(?i)\b{_TOKEN_LABEL}\b\s*(?:[:=—–-]|\bis\b|\bэто\b)\s*"
    rf"(?:bearer\s+)?{_SECRET_VALUE}"
)
_TOKEN_BARE_VALUE = re.compile(
    rf"(?i)\b{_TOKEN_LABEL}\b\s+(?:bearer\s+)?[a-z0-9._-]{{12,}}\b"
)
_BEARER_VALUE = re.compile(
    r"(?i)\bbearer\s+[a-z0-9._~+/-]{8,}=*(?![a-z0-9._~+/=-])"
)
_BARE_OTP_CODE = re.compile(
    r"(?i)\bкод(?:\s+подтверждения|\s+из\s+sms)?\b\s*(?:[:=—–-]\s*|\s+)\d{4,8}\b"
)
_CARD_NUMBER = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
_CARD_SECRET = re.compile(r"(?i)\b(cvc|cvv)\b\s*[:=]?\s*\d{3,4}")
_STANDALONE_TOKEN = re.compile(
    r"(?i)\b(?:sk_(?:live|test)_[a-z0-9_-]{12,}|sk-[a-z0-9_-]{16,}|"
    r"gh[pousr]_[a-z0-9]{20,}|github_pat_[a-z0-9_]{20,}|"
    r"xox[baprs]-[a-z0-9-]{12,})\b"
)
_JWT_CANDIDATE = re.compile(
    r"(?<![a-zA-Z0-9_-])[a-zA-Z0-9_-]{8,}\."
    r"[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}(?![a-zA-Z0-9_-])"
)
_JWE_CANDIDATE = re.compile(
    r"(?<![a-zA-Z0-9_-])[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]*\."
    r"[a-zA-Z0-9_-]{8,}\.[a-zA-Z0-9_-]{8,}\."
    r"[a-zA-Z0-9_-]{8,}(?![a-zA-Z0-9_-])"
)


def _jose_json_segment(segment: str) -> dict | None:
    padded = segment + "=" * (-len(segment) % 4)
    try:
        decoded = json.loads(base64.urlsafe_b64decode(padded))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return None
    return decoded if isinstance(decoded, dict) else None


def _redact_jwt_candidate(match: re.Match[str]) -> str:
    value = match.group(0)
    header, payload, _signature = value.split(".")
    header_data = _jose_json_segment(header)
    if (
        header_data
        and isinstance(header_data.get("alg"), str)
        and header_data["alg"]
        and _jose_json_segment(payload) is not None
    ):
        return "[СЕКРЕТ УДАЛЁН]"
    return value


def _redact_jwe_candidate(match: re.Match[str]) -> str:
    value = match.group(0)
    header_data = _jose_json_segment(value.split(".", 1)[0])
    if (
        header_data
        and isinstance(header_data.get("alg"), str)
        and header_data["alg"]
        and isinstance(header_data.get("enc"), str)
        and header_data["enc"]
    ):
        return "[СЕКРЕТ УДАЛЁН]"
    return value


def redact_sensitive_support_text(message: str) -> str:
    """Remove common credentials before support text is persisted or escalated."""

    redacted = _BARE_OTP_CODE.sub("[СЕКРЕТ УДАЛЁН]", message)
    redacted = _TOKEN_ASSIGNMENT.sub("[СЕКРЕТ УДАЛЁН]", redacted)
    redacted = _TOKEN_BARE_VALUE.sub("[СЕКРЕТ УДАЛЁН]", redacted)
    redacted = _BEARER_VALUE.sub("[СЕКРЕТ УДАЛЁН]", redacted)
    redacted = _SECRET_ASSIGNMENT.sub("[СЕКРЕТ УДАЛЁН]", redacted)
    redacted = _BARE_PASSWORD_VALUE.sub("[СЕКРЕТ УДАЛЁН]", redacted)
    redacted = _STANDALONE_TOKEN.sub("[СЕКРЕТ УДАЛЁН]", redacted)
    redacted = _JWE_CANDIDATE.sub(_redact_jwe_candidate, redacted)
    redacted = _JWT_CANDIDATE.sub(_redact_jwt_candidate, redacted)
    redacted = _CARD_SECRET.sub("[ПЛАТЁЖНЫЕ ДАННЫЕ УДАЛЕНЫ]", redacted)
    redacted = _CARD_NUMBER.sub("[ПЛАТЁЖНЫЕ ДАННЫЕ УДАЛЕНЫ]", redacted)
    return redacted


def _no_show_offsets(message: str) -> list[int]:
    offsets = [match.start() for match in _PERFORMER_NO_SHOW.finditer(message)]
    folded = message.casefold()
    for phrase in _EVENT_DAY_NO_SHOW:
        offsets.extend(match.start() for match in re.finditer(re.escape(phrase), folded))
    return offsets


def no_show_evidence_offset(message: str) -> int | None:
    """Locate the most recent no-show evidence for a shortened operator handoff."""

    offsets = _no_show_offsets(message)
    return max(offsets) if offsets else None


def _active_no_show_in_message(message: str) -> bool:
    """A completed arrival cannot resolve a later no-show in the same message."""

    offsets = _no_show_offsets(message)
    if not offsets:
        return False
    resolution = list(_NO_SHOW_RESOLVED_IN_MESSAGE.finditer(message))
    return not resolution or max(offsets) >= resolution[-1].end()


def answer_support_question(message: str) -> SupportAgentReply:
    """Return a bounded answer from approved static guidance, without network or mutations."""

    text = re.sub(r"\s+", " ", message.casefold()).strip()

    if _active_no_show_in_message(text):
        return SupportAgentReply(
            assistant_message=(
                "Это срочный случай дня события. Помощник не меняет сделку и не назначает "
                "замену. Нажмите «Передать человеку» и укажите событие, участника и время, "
                "когда ожидалось прибытие. Оператор получит обращение с высоким приоритетом."
            ),
            intent="event_day_no_show",
            outcome="needs_human",
            needs_human=True,
            source_ids=("sla.event_day_no_show", "support.human_handoff"),
        )

    if _PERFORMER_CANCELLED_EVENT.search(text):
        return SupportAgentReply(
            assistant_message=(
                "Понимаю, что отмена выступления перед событием требует быстрой проверки. "
                "Помощник не видит условия сделки и не назначает замену. Нажмите «Передать "
                "человеку» и укажите событие, исполнителя и время отмены без личных данных. "
                "Специалист проверит ситуацию и доступные действия."
            ),
            intent="performer_cancelled_event",
            outcome="needs_human",
            needs_human=True,
            source_ids=("support.human_handoff",),
        )

    if (_has_any(text, _PAID_MARKERS) and _has_any(text, _NOT_CONFIRMED_MARKERS)) or (
        _CARD_CHARGE_PENDING_BOOKING.search(text) and _BOOKING_AWAITS_PAYMENT.search(text)
    ):
        return SupportAgentReply(
            assistant_message=(
                "Статус денег и брони должен проверить оператор по серверному журналу. "
                "Не повторяйте оплату. Нажмите «Передать человеку» и укажите сделку и время "
                "операции без платёжных реквизитов. Оператор проверит журналы оплаты и брони."
            ),
            intent="paid_not_confirmed",
            outcome="needs_human",
            needs_human=True,
            source_ids=("sla.paid_not_confirmed", "contract.money_api_only"),
        )

    if _DOUBLE_CONFIRMED_SLOT.search(text):
        return SupportAgentReply(
            assistant_message=(
                "Две подтверждённые брони на один слот должен проверить специалист по данным "
                "сделок. Не отменяйте и не создавайте брони заново по совету помощника. "
                "Нажмите «Передать человеку» и укажите обе сделки и слот без личных данных."
            ),
            intent="duplicate_confirmed_booking",
            outcome="needs_human",
            needs_human=True,
            source_ids=("contract.booking_state", "support.human_handoff"),
        )

    if _has_any(text, _HUMAN_REQUEST):
        return SupportAgentReply(
            assistant_message=(
                "Передам обращение специалисту после вашего нажатия «Передать человеку». "
                "Статусы сделки и денег при этом не изменятся."
            ),
            intent="human_request",
            outcome="needs_human",
            needs_human=True,
            source_ids=("support.human_handoff",),
        )

    if _has_any(text, _SECURITY):
        return SupportAgentReply(
            assistant_message=(
                "Это должен проверить специалист. Не отправляйте пароль, код из SMS, TOTP или "
                "платёжные реквизиты. Нажмите «Передать человеку» и кратко укажите, когда вы "
                "заметили проблему."
            ),
            intent="account_security",
            outcome="needs_human",
            needs_human=True,
            source_ids=("support.security", "support.human_handoff"),
        )

    if _has_any(text, _MONEY_OR_LEGAL):
        return SupportAgentReply(
            assistant_message=(
                "Решения по платежам, возвратам, спорам и юридическим вопросам принимает "
                "специалист. Помощник не меняет платёж или сделку и не обещает результат. "
                "Нажмите «Передать человеку», чтобы создать обращение."
            ),
            intent="money_or_legal",
            outcome="needs_human",
            needs_human=True,
            source_ids=("contract.money_api_only", "support.human_handoff"),
        )

    if _has_any(text, ("игнорируй", "system prompt", "системный промпт", "покажи инструкц")):
        return SupportAgentReply(
            assistant_message=(
                "Я могу помочь с работой Букера: входом, организацией, приглашениями, "
                "брифом, предложением, сообщениями и загрузкой файлов. Опишите проблему в этих "
                "рамках. Если нужна другая помощь, нажмите «Передать человеку»."
            ),
            intent="unsupported_instruction",
            outcome="clarify",
            needs_human=False,
            source_ids=("support.scope",),
        )

    if _has_any(text, ("не могу войти", "войти", "вход", "логин", "пароль")):
        return SupportAgentReply(
            assistant_message=(
                "Проверьте адрес почты, раскладку и Caps Lock. Затем обновите страницу и "
                "попробуйте войти ещё раз. Если пароль не подходит, откройте восстановление "
                "на странице входа. Если доступ не восстановился, передайте вопрос человеку. "
                "Не отправляйте пароль или код подтверждения в чат."
            ),
            intent="account_access",
            outcome="answered",
            needs_human=False,
            source_ids=("support.account_access", "support.security"),
        )

    if _has_any(text, ("приглаш", "команд", "организац", "рабочее пространство", "роль")):
        return SupportAgentReply(
            assistant_message=(
                "Откройте рабочее пространство и проверьте активную организацию. Приглашение "
                "нужно принять из письма тем же адресом, на который его отправили. Если ссылка "
                "истекла или приглашение отозвано, попросите владельца отправить новое."
            ),
            intent="organization_invitation",
            outcome="answered",
            needs_human=False,
            source_ids=("support.organizations", "support.invitations"),
        )

    if _has_any(text, ("документ", "скачать договор", "подписан")) or re.search(
        r"\bакт(?:а|е|ом|ы|ов)?\b", text
    ):
        return SupportAgentReply(
            assistant_message=(
                "Если речь о сделке, откройте её вкладку «Документы» и проверьте доступные "
                "файлы. Помощник не видит вашу сделку и не подтверждает наличие, подписание "
                "или юридическую силу документа. Если файл отсутствует, не открывается или "
                "нужно проверить его статус, нажмите «Передать человеку» и укажите сделку "
                "без личных данных в сообщении."
            ),
            intent="deal_documents",
            outcome="answered",
            needs_human=False,
            source_ids=("support.deal_documents", "contract.legal_drafts"),
        )

    if _has_any(text, _CODE_DELIVERY):
        return SupportAgentReply(
            assistant_message=(
                "Уточните, какой код не поступил: для входа, приглашения или подтверждения "
                "черновика сделки. Проверьте адрес почты и папку нежелательных писем. Не "
                "публикуйте код в чате; если он не приходит повторно, передайте вопрос человеку."
            ),
            intent="code_delivery",
            outcome="clarify",
            needs_human=False,
            source_ids=("support.account_access", "support.human_handoff"),
        )

    if _has_any(text, _ARRIVAL_PROBLEM):
        return SupportAgentReply(
            assistant_message=(
                "Я не могу определить, кто именно не прибыл и как это влияет на событие. "
                "Если вопрос требует действий сейчас, нажмите «Передать человеку» и укажите "
                "событие, участника и ожидаемое время без личных или платёжных данных."
            ),
            intent="arrival_unclear",
            outcome="needs_human",
            needs_human=True,
            source_ids=("support.human_handoff",),
        )

    if _has_any(text, ("площадк", "исполнител", "артист", "профиль не вид", "карточк")):
        return SupportAgentReply(
            assistant_message=(
                "Если не видите карточку площадки или исполнителя, проверьте активную "
                "организацию и данные профиля в кабинете. Публикация зависит от проверки "
                "профиля, цены и календаря; помощник не видит статус вашей карточки и не "
                "может обещать её появление в каталоге. Если нужна проверка владения "
                "карточкой или причина отказа, нажмите «Передать человеку»."
            ),
            intent="supply_profile",
            outcome="answered",
            needs_human=False,
            source_ids=("contract.profile_publication", "support.human_handoff"),
        )

    if _has_any(text, ("файл", "загруз", "фото", "видео", "вложен", "медиа")):
        return SupportAgentReply(
            assistant_message=(
                "Проверьте формат и размер файла, затем повторите загрузку из стабильной сети. "
                "Не загружайте пароли, платёжные реквизиты и документы, которые не нужны для "
                "сделки. Если ошибка повторяется, укажите тип файла и текст ошибки."
            ),
            intent="media_upload",
            outcome="answered",
            needs_human=False,
            source_ids=("support.uploads", "support.security"),
        )

    if _has_any(text, ("сообщен", "чат", "не отправ", "не приходит")):
        return SupportAgentReply(
            assistant_message=(
                "Откройте «Сообщения», выберите нужный запрос или сделку и обновите страницу. "
                "Проверьте активную организацию: сообщения доступны только участникам. Если "
                "отправка всё ещё не работает, пришлите текст ошибки без личных данных."
            ),
            intent="messages",
            outcome="answered",
            needs_human=False,
            source_ids=("support.messages", "support.organizations"),
        )

    if _has_any(text, ("брон", "предложен", "оффер", "бриф", "запрос", "дата", "слот")):
        return SupportAgentReply(
            assistant_message=(
                "Проверьте активную организацию и откройте нужный запрос в сообщениях. Статус "
                "брони меняется только профильным действием в сделке; помощник его не меняет. "
                "Если действие недоступно, напишите текущий статус и название кнопки, которую вы "
                "ожидали увидеть."
            ),
            intent="booking_flow",
            outcome="answered",
            needs_human=False,
            source_ids=("contract.booking_state", "support.organizations"),
        )

    if _has_any(text, ("ошиб", "не работает", "завис", "белый экран", "500", "404")):
        return SupportAgentReply(
            assistant_message=(
                "Обновите страницу один раз и повторите действие. Если ошибка остаётся, укажите "
                "страницу, действие перед ошибкой и точный текст ошибки. Не отправляйте токены, "
                "пароли и платёжные реквизиты."
            ),
            intent="technical",
            outcome="clarify",
            needs_human=False,
            source_ids=("support.technical", "support.security"),
        )

    return SupportAgentReply(
        assistant_message=(
            "Я не могу определить проблему по этому сообщению и не вижу ваши данные, статусы "
            "или идентификаторы. Уточните, где возникла проблема: вход, организация, бронь, "
            "документы, площадка, исполнитель, сообщения, файл или оплата. Опишите действие "
            "и результат без паролей, кодов и платёжных реквизитов. Если вопрос вне этих тем "
            "или нужна проверка вашей ситуации, нажмите «Передать человеку»."
        ),
        intent="clarification",
        outcome="clarify",
        needs_human=False,
        source_ids=("support.scope",),
    )
