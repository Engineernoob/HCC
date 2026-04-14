"""
Daily email digest — sends a morning briefing via Resend.

Runs at 07:00 every day (configurable via CRON_DAILY_DIGEST).
Includes: top 5 targets, new signals, outreach due, priority action.

Falls back to console output if Resend is not configured.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from hirectl.config import settings

logger = logging.getLogger(__name__)


@dataclass
class DigestData:
    top_companies: list[dict]  # company dicts with name, score, urgency, signals
    new_signals: list[dict]    # signal dicts with company, type, headline
    outreach_due: list[dict]   # outreach records due for follow-up
    stats: dict                # totals: companies, roles, signals
    ai_brief: str = ""
    generated_at: datetime | None = None

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.utcnow()


class EmailDigest:
    """
    Generates and sends the daily intelligence digest.
    Uses Resend for email delivery.
    Falls back to rich console output in development.
    """

    def __init__(self):
        self.logger = logging.getLogger("hirectl.digest")

    async def send(self, data: DigestData) -> bool:
        """Send the digest. Returns True on success."""
        html = self._render_html(data)
        text = self._render_text(data)

        if not settings.resend_api_key:
            self.logger.info("Resend not configured — printing digest to console")
            self._print_console(text)
            return True

        return await self._send_resend(html, text, data.generated_at)

    async def _send_resend(self, html: str, text: str, dt: datetime) -> bool:
        try:
            import resend
            resend.api_key = settings.resend_api_key

            subject = (
                f"HIRE INTEL — {dt.strftime('%a %b %d')} · "
                f"Daily Intelligence Digest"
            )

            resend.Emails.send({
                "from": settings.alert_email_from,
                "to": [settings.alert_email_to],
                "subject": subject,
                "html": html,
                "text": text,
            })
            self.logger.info(f"Digest sent to {settings.alert_email_to}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send digest: {e}")
            return False

    def _render_html(self, data: DigestData) -> str:
        """Render the HTML email — matches the terminal aesthetic."""
        date_str = data.generated_at.strftime("%A, %B %d, %Y")

        companies_html = ""
        for i, co in enumerate(data.top_companies[:5], 1):
            urgency_color = {
                "critical": "#c06060",
                "high": "#c08050",
                "medium": "#b0a060",
                "low": "#609070",
            }.get(co.get("urgency", "low"), "#888")

            companies_html += f"""
            <tr>
              <td style="padding: 10px 0; border-bottom: 1px solid #2a2a22; vertical-align: top;">
                <span style="font-family: monospace; font-size: 11px; color: #5a5a50;">
                  {str(i).zfill(2)}
                </span>
              </td>
              <td style="padding: 10px 12px; border-bottom: 1px solid #2a2a22; vertical-align: top;">
                <div style="font-family: Georgia, serif; font-style: italic; font-size: 16px;
                             color: #eceae0; margin-bottom: 3px;">
                  {co['name']}
                </div>
                <div style="font-family: monospace; font-size: 10px; color: #5a5a50;">
                  {co.get('tagline', '')} · {co.get('stage', '')}
                </div>
                <div style="font-family: monospace; font-size: 10px; color: #8a8a78;
                             margin-top: 4px;">
                  {' · '.join(co.get('signals', [])[:2])}
                </div>
              </td>
              <td style="padding: 10px 0; border-bottom: 1px solid #2a2a22; vertical-align: top;
                          text-align: right; font-family: monospace; font-size: 22px;
                          color: #c8a96e; white-space: nowrap;">
                {co.get('score', 0):.0f}
              </td>
              <td style="padding: 10px 0 10px 12px; border-bottom: 1px solid #2a2a22;
                          vertical-align: top;">
                <span style="font-family: monospace; font-size: 9px; padding: 2px 6px;
                              border: 1px solid; color: {urgency_color};">
                  {co.get('urgency', 'low').upper()}
                </span>
              </td>
            </tr>"""

        signals_html = ""
        for sig in data.new_signals[:6]:
            signals_html += f"""
            <tr>
              <td style="padding: 8px 0; border-bottom: 1px solid #1e1e18; vertical-align: top;">
                <div style="font-family: monospace; font-size: 9px; letter-spacing: 0.1em;
                              text-transform: uppercase; color: #5a5a50; margin-bottom: 3px;">
                  {sig.get('type', '').replace('_', ' ')}
                </div>
                <div style="font-family: Georgia, serif; font-style: italic; font-size: 13px;
                              color: #c8c5b8;">
                  {sig.get('headline', '')}
                </div>
              </td>
              <td style="padding: 8px 0 8px 12px; border-bottom: 1px solid #1e1e18;
                          vertical-align: top; white-space: nowrap;">
                <span style="font-family: monospace; font-size: 9px; padding: 2px 6px;
                              border: 1px solid #3a3a32; color: #8a8a78;">
                  {sig.get('company', '')}
                </span>
              </td>
            </tr>"""

        return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>HIRE INTEL — Daily Digest</title>
</head>
<body style="background: #080806; color: #c8c5b8; font-family: monospace;
              margin: 0; padding: 0;">
  <div style="max-width: 680px; margin: 0 auto; padding: 32px 24px;">

    <!-- Header -->
    <div style="border-bottom: 2px solid #2e2e28; padding-bottom: 20px; margin-bottom: 24px;">
      <div style="font-size: 9px; letter-spacing: 0.2em; text-transform: uppercase;
                   color: #5a5a50; margin-bottom: 8px;">Hire Intel</div>
      <div style="font-family: Georgia, serif; font-style: italic; font-size: 24px;
                   color: #eceae0; line-height: 1.2; margin-bottom: 6px;">
        Daily Intelligence Digest
      </div>
      <div style="font-size: 10px; color: #5a5a50;">{date_str}</div>
    </div>

    <!-- Stats row -->
    <div style="display: flex; gap: 24px; margin-bottom: 24px; border-bottom: 1px solid #1e1e18;
                 padding-bottom: 16px;">
      <div>
        <div style="font-size: 22px; color: #eceae0;">{data.stats.get('new_signals', 0)}</div>
        <div style="font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
                     color: #5a5a50;">New Signals</div>
      </div>
      <div>
        <div style="font-size: 22px; color: #eceae0;">{data.stats.get('companies', 0)}</div>
        <div style="font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
                     color: #5a5a50;">Companies</div>
      </div>
      <div>
        <div style="font-size: 22px; color: #c8a96e;">{len(data.outreach_due)}</div>
        <div style="font-size: 9px; letter-spacing: 0.1em; text-transform: uppercase;
                     color: #5a5a50;">Outreach Due</div>
      </div>
    </div>

    <!-- AI Brief -->
    {f'''<div style="border: 1px solid #2e2e28; padding: 16px; margin-bottom: 24px;
                      background: #0d0d0a;">
      <div style="font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;
                   color: #5a5a50; margin-bottom: 8px;">AI Intelligence Brief</div>
      <div style="font-family: Georgia, serif; font-size: 13px; color: #c8c5b8;
                   line-height: 1.7;">{data.ai_brief}</div>
    </div>''' if data.ai_brief else ''}

    <!-- Priority Queue -->
    <div style="margin-bottom: 24px;">
      <div style="font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;
                   color: #5a5a50; margin-bottom: 10px;">Priority Queue</div>
      <table style="width: 100%; border-collapse: collapse;">
        {companies_html}
      </table>
    </div>

    <!-- Signal Radar -->
    <div style="margin-bottom: 24px;">
      <div style="font-size: 9px; letter-spacing: 0.18em; text-transform: uppercase;
                   color: #5a5a50; margin-bottom: 10px;">Signal Radar — Last 24h</div>
      <table style="width: 100%; border-collapse: collapse;">
        {signals_html}
      </table>
    </div>

    <!-- Footer -->
    <div style="border-top: 1px solid #1e1e18; padding-top: 16px; font-size: 9px;
                 color: #3a3a32; letter-spacing: 0.06em;">
      HIRE INTEL · Generated {data.generated_at.strftime('%Y-%m-%d %H:%M')} UTC ·
      Real-time hiring intelligence for high-signal opportunities before they saturate
    </div>
  </div>
</body>
</html>"""

    def _render_text(self, data: DigestData) -> str:
        """Plain text fallback."""
        lines = [
            "=" * 60,
            f"HIRE INTEL — Daily Digest — {data.generated_at.strftime('%Y-%m-%d')}",
            "=" * 60,
            "",
            f"New signals (24h): {data.stats.get('new_signals', 0)}",
            f"Companies tracked: {data.stats.get('companies', 0)}",
            f"Outreach due: {len(data.outreach_due)}",
            "",
        ]

        if data.ai_brief:
            lines += ["AI BRIEF", "-" * 40, data.ai_brief, ""]

        lines += ["PRIORITY QUEUE", "-" * 40]
        for i, co in enumerate(data.top_companies[:5], 1):
            lines.append(
                f"{i:02d}. {co['name']:30} "
                f"Score: {co.get('score', 0):.0f}  "
                f"[{co.get('urgency', 'low').upper()}]"
            )
            for sig in co.get("signals", [])[:1]:
                lines.append(f"    → {sig}")

        lines += ["", "SIGNALS", "-" * 40]
        for sig in data.new_signals[:6]:
            lines.append(
                f"[{sig.get('type', '').upper():20}] {sig.get('company', '')}: "
                f"{sig.get('headline', '')}"
            )

        return "\n".join(lines)

    def _print_console(self, text: str) -> None:
        """Print digest to console with rich formatting."""
        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console()
            console.print(Panel(text, title="[gold1]HIRE INTEL — Daily Digest[/]",
                                border_style="dim"))
        except ImportError:
            print(text)
