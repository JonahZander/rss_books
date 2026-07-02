from __future__ import annotations

import logging
from email.message import EmailMessage
from pathlib import Path

import aiosmtplib

from rss_kindle.db import Database
from rss_kindle.models import AppSettings, Delivery

logger = logging.getLogger(__name__)

# Amazon's gateway rejects attachments over 50 MB; leave headroom for
# MIME overhead (base64 adds ~37%... the guard is on the raw file size
# Amazon documents, so 45 MB keeps us safely under their cap).
MAX_ATTACHMENT_BYTES = 45 * 1024 * 1024


class EmailError(Exception):
    """Raised for configuration problems and SMTP transport failures."""


def require_email_config(settings: AppSettings, to: list[str]) -> None:
    missing = []
    if not settings.smtp_host:
        missing.append("SMTP host")
    if not settings.smtp_from:
        missing.append("From address")
    if not to:
        missing.append("destination address")
    if missing:
        raise EmailError("email not configured: missing " + ", ".join(missing))


async def _smtp_send(settings: AppSettings, msg: EmailMessage) -> None:
    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username or None,
            password=settings.smtp_password or None,
            use_tls=settings.smtp_security == "ssl",
            start_tls=True if settings.smtp_security == "starttls" else None,
            timeout=30,
        )
    except (aiosmtplib.SMTPException, OSError) as exc:
        raise EmailError(str(exc)) from exc


async def send_test_email(settings: AppSettings, to: list[str] | None = None) -> list[str]:
    recipients = to or settings.send_to
    require_email_config(settings, recipients)
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = "RSS Books test"
    msg.set_content(
        "Your delivery settings work. Editions will arrive like this, as EPUB attachments.\n"
    )
    await _smtp_send(settings, msg)
    return recipients


async def send_digest_email(
    settings: AppSettings, *, epub_path: Path, digest_title: str, to: list[str]
) -> None:
    require_email_config(settings, to)
    if not epub_path.exists():
        raise EmailError(f"EPUB missing on disk: {epub_path}")
    size = epub_path.stat().st_size
    if size > MAX_ATTACHMENT_BYTES:
        raise EmailError(
            f"EPUB is {size / 2**20:.1f} MB, over the {MAX_ATTACHMENT_BYTES // 2**20} MB "
            "email limit (Amazon caps personal documents at 50 MB)"
        )
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = ", ".join(to)
    msg["Subject"] = f"Pressed edition {digest_title}"
    msg.set_content("Attached: your hand-picked edition, pressed by RSS Books.\n")
    msg.add_attachment(
        epub_path.read_bytes(),
        maintype="application",
        subtype="epub+zip",
        filename=f"digest-{digest_title}.epub",
    )
    await _smtp_send(settings, msg)


async def send_digest_and_record(db: Database, settings: AppSettings, digest_id: int) -> Delivery:
    """Email a ready digest to the configured addresses and record the outcome.

    Configuration problems raise EmailError without recording anything;
    transport failures are recorded as a failed delivery.
    Raises LookupError for an unknown digest.
    """
    require_email_config(settings, settings.send_to)

    async with db.connect() as conn:
        cur = await conn.execute(
            "SELECT title, epub_path, status FROM digests WHERE id = ?", (digest_id,)
        )
        row = await cur.fetchone()
    if row is None:
        raise LookupError(f"digest {digest_id} not found")
    if row["status"] != "ready" or not row["epub_path"]:
        raise EmailError("digest is not ready")

    target = ", ".join(settings.send_to)
    try:
        await send_digest_email(
            settings,
            epub_path=Path(row["epub_path"]),
            digest_title=row["title"],
            to=settings.send_to,
        )
        send_status, error = "sent", None
    except EmailError as exc:
        send_status, error = "failed", str(exc)

    async with db.connect() as conn:
        cur = await conn.execute(
            "INSERT INTO deliveries (digest_id, channel, target, status, error) "
            "VALUES (?, 'email', ?, ?, ?)",
            (digest_id, target, send_status, error),
        )
        delivery_id = cur.lastrowid
        if send_status == "sent":
            await conn.execute(
                "UPDATE digests SET delivered_at = CURRENT_TIMESTAMP WHERE id = ?",
                (digest_id,),
            )
        await conn.commit()
        cur = await conn.execute(
            "SELECT id, digest_id, channel, target, status, error, created_at "
            "FROM deliveries WHERE id = ?",
            (delivery_id,),
        )
        drow = await cur.fetchone()
    if drow is None:
        raise RuntimeError("delivery record vanished after insert")

    logger.info("digest %d email %s (%s)", digest_id, send_status, target)
    return Delivery.model_validate(dict(drow))
