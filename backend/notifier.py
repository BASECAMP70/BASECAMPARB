"""
Email notifier for arb opportunities.

Configure via .env:
  SMTP_HOST    — SMTP server hostname  (default: smtp.gmail.com)
  SMTP_PORT    — SMTP port             (default: 587)
  SMTP_USER    — login / from address
  SMTP_PASS    — password or app-password
  ARB_EMAIL    — recipient address     (default: scott@basecampinc.ca)

If SMTP_USER or SMTP_PASS are empty the notifier logs a warning and skips sending.
"""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

import aiosmtplib

import config
from calculator import Opportunity

logger = logging.getLogger(__name__)



def _build_email(opportunities: List[Opportunity]) -> tuple[str, str, str]:
    """Return (subject, plain_text, html) for the opportunity digest."""
    count = len(opportunities)
    subject = f"ARB Opportunity — {count} new {'opportunity' if count == 1 else 'opportunities'} found"

    lines_plain = [f"ARB FINDER — {count} new arbitrage {'opportunity' if count == 1 else 'opportunities'}\n"]
    lines_html = [
        "<html><body style='font-family:sans-serif;max-width:600px;margin:auto'>",
        f"<h2 style='color:#22c55e'>ARB Finder — {count} new {'opportunity' if count == 1 else 'opportunities'}</h2>",
    ]

    for opp in opportunities:
        margin_pct = f"{opp.margin * 100:.2f}%"
        event_dt = opp.event_start.strftime("%b %d %H:%M UTC")

        # Plain text block
        lines_plain.append(f"{'─' * 50}")
        lines_plain.append(f"  {opp.event_name}  ({opp.sport.upper()} · {opp.market})")
        lines_plain.append(f"  Game time : {event_dt}")
        lines_plain.append(f"  Margin    : {margin_pct}")
        lines_plain.append(f"  Stake $100 across:")
        for leg in opp.outcomes:
            stake = f"${leg.recommended_stake:.2f}"
            odds_str = f"{leg.decimal_odds:.2f}"
            lines_plain.append(f"    {leg.book:20s}  {leg.participant:30s}  {odds_str:>6}  {stake}")
        lines_plain.append("")

        # HTML block
        leg_rows = "".join(
            f"<tr>"
            f"<td style='padding:4px 8px'>{leg.book}</td>"
            f"<td style='padding:4px 8px'>{leg.participant}</td>"
            f"<td style='padding:4px 8px;text-align:right'>"
            f"<b>{leg.decimal_odds:.2f}</b></td>"
            f"<td style='padding:4px 8px;text-align:right'>${leg.recommended_stake:.2f}</td>"
            f"</tr>"
            for leg in opp.outcomes
        )
        lines_html.append(
            f"<div style='border:1px solid #e5e7eb;border-radius:8px;padding:12px;margin-bottom:16px'>"
            f"<p style='margin:0 0 4px'><strong>{opp.event_name}</strong>"
            f"<span style='color:#6b7280;font-size:0.85em'> · {opp.sport.upper()} {opp.market} · {event_dt}</span></p>"
            f"<p style='margin:0 0 8px;font-size:1.1em;color:#22c55e'>Margin: <strong>{margin_pct}</strong></p>"
            f"<table style='width:100%;border-collapse:collapse;font-size:0.9em'>"
            f"<thead><tr style='background:#f9fafb'>"
            f"<th style='padding:4px 8px;text-align:left'>Book</th>"
            f"<th style='padding:4px 8px;text-align:left'>Selection</th>"
            f"<th style='padding:4px 8px;text-align:right'>Odds</th>"
            f"<th style='padding:4px 8px;text-align:right'>Stake</th>"
            f"</tr></thead><tbody>{leg_rows}</tbody></table></div>"
        )

    lines_html.append("</body></html>")

    return subject, "\n".join(lines_plain), "\n".join(lines_html)


async def notify_new_opportunities(opportunities: List[Opportunity]) -> None:
    """Send an email digest for newly-detected arb opportunities."""
    if not config.SMTP_USER or not config.SMTP_PASS:
        logger.debug(
            "[notifier] SMTP_USER/SMTP_PASS not configured — skipping email for %d opportunities",
            len(opportunities),
        )
        return

    subject, plain, html = _build_email(opportunities)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = config.SMTP_USER
    msg["To"] = config.ARB_EMAIL
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=config.SMTP_HOST,
            port=config.SMTP_PORT,
            username=config.SMTP_USER,
            password=config.SMTP_PASS,
            start_tls=True,
        )
        logger.info(
            "[notifier] Emailed %d opportunity alert(s) to %s",
            len(opportunities), config.ARB_EMAIL,
        )
    except Exception as exc:
        logger.warning("[notifier] Failed to send email: %s", exc)
