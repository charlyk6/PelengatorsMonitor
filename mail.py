import os
import smtplib
import ssl
from email.message import EmailMessage
from html import unescape
import re

MAIL_FROM = os.getenv("MAIL_FROM", "").strip()
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "").strip()
MAIL_SMTP_HOST = os.getenv("MAIL_SMTP_HOST", "smtp.mail.ru").strip()
MAIL_SMTP_PORT = int(os.getenv("MAIL_SMTP_PORT", "2525"))

_TAG_RE = re.compile(r"<[^>]+>")


def configured() -> bool:
    return bool(MAIL_FROM and MAIL_PASSWORD)


def html_to_text(html: str) -> str:
    text = unescape(html or "")
    text = text.replace("<br>", "\n").replace("<br/>", "\n")
    return _TAG_RE.sub("", text).strip()


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _open_smtp() -> smtplib.SMTP:
    host = MAIL_SMTP_HOST
    context = _ssl_context()
    attempts: list[tuple[str, int]] = []
    seen: set[tuple[str, int]] = set()
    for mode, port in (
        ("starttls", 587),
        ("ssl", 465),
        ("starttls", 2525),
        ("starttls", MAIL_SMTP_PORT),
        ("ssl", MAIL_SMTP_PORT),
    ):
        key = (mode, port)
        if key in seen:
            continue
        seen.add(key)
        attempts.append(key)
    last_error: Exception | None = None
    for mode, port in attempts:
        try:
            if mode == "ssl":
                smtp = smtplib.SMTP_SSL(host, port, context=context, timeout=8)
            else:
                smtp = smtplib.SMTP(host, port, timeout=8)
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            smtp.login(MAIL_FROM, MAIL_PASSWORD)
            return smtp
        except Exception as error:
            last_error = error
            continue
    if last_error is not None:
        raise last_error
    raise RuntimeError("Не удалось подключиться к SMTP")


def send_mail(to_email: str, subject: str, html_body: str) -> bool:
    to_email = (to_email or "").strip()
    if not configured() or not to_email:
        return False
    message = EmailMessage()
    message["From"] = MAIL_FROM
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(html_to_text(html_body))
    message.add_alternative(html_body, subtype="html")
    with _open_smtp() as smtp:
        smtp.send_message(message)
    return True
