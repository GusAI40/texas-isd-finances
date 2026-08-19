"""The outreach email itself — renderer and Resend client, in deployed code.

Moved here VERBATIM from scripts/send_outreach.py on 2026-08-19, because the
root-cause review of "why did the outreach machine stop working" landed on one
fact: every part of the pipeline that lived outside the deployed site died
with the container that held it. Vercel is the one place in this system where
secrets have proven durable — the site never lost its keys through three
container losses — so the send machinery moves to where the keys are, not the
other way around. scripts/send_outreach.py imports these same objects, so the
laptop path and the server path render byte-identical messages and there is
exactly one copy of each (the src/format.py lesson).

Nothing here decides WHO gets mail. Selection, skip-lists and the watermark
guard live in src/outreach_runner.py; this file only knows how to render one
row and how to speak to Resend.
"""
from __future__ import annotations

import html
import json
import ssl
import urllib.request

SITE = "https://txisd.dev"
API = "https://api.resend.com"

BLUE = "#2f4bd7"
INK = "#111318"
MUT = "#5a5f6b"


def render_email(row: dict, postal: str, unsubscribe: str,
                 rid: str = "", site: str = SITE) -> tuple[str, str]:
    """(html, text) for one district. Inline styles only — email clients strip
    <style> blocks. The three insights come from the merge data, which built
    them from the same artefacts the site serves: frame honesty travels.

    When `rid` is supplied the message carries this recipient's journey token:
    the link gets `&rid=…` so their click and everything after it is
    attributable, and an open pixel is appended. Without a rid the email is
    byte-identical to the untracked version, which is what --test sends.
    """
    e = html.escape
    name = row["district_name"]
    insights = [row[k] for k in ("insight_bonds", "insight_debt",
                                 "insight_trend") if row.get(k)]
    # The tracked link and the open pixel. Both are empty-safe: with no rid the
    # link is exactly what wave 1 sent, and the pixel is an empty string.
    link = f"{row['deep_link']}&src=email" + (f"&rid={rid}" if rid else "")
    pixel = (f'<img src="{site}/px/{rid}.gif" width="1" height="1" alt="" '
             f'style="display:block;border:0;" />') if rid else ""
    disclose = (f'This email carries a code unique to you, so we can see '
                f'whether it was opened and whether the report was useful. If '
                f'you&rsquo;d rather we didn&rsquo;t, don&rsquo;t click the '
                f'link &mdash; or reply and we&rsquo;ll delete the record. '
                f'<a href="{site}/about#privacy" style="color:{MUT};">'
                f'What we collect</a>.<br>') if rid else ""
    bullets = "".join(
        f'<tr><td style="padding:0 0 14px 0;vertical-align:top;width:18px;'
        f'color:{BLUE};font-weight:700;">&#8250;</td>'
        f'<td style="padding:0 0 14px 8px;color:{INK};font-size:15px;'
        f'line-height:1.55;">{e(s)}</td></tr>' for s in insights)

    body = f"""<!DOCTYPE html>
<html><body style="margin:0;padding:0;background:#f4f4f2;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f2;">
<tr><td align="center" style="padding:32px 16px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="max-width:600px;background:#ffffff;border:1px solid #e4e4e0;">
  <tr><td style="padding:36px 40px 0;font-family:Georgia,'Times New Roman',serif;">
    <div style="font-size:12px;letter-spacing:2px;color:{MUT};font-family:Arial,sans-serif;">
      TAG AI &middot; TEXAS ISD FINANCIAL RESOURCE GUIDE</div>
    <h1 style="font-size:26px;line-height:1.3;color:{INK};margin:14px 0 0;">
      We built {e(name)}&rsquo;s report. It&rsquo;s yours.</h1>
  </td></tr>
  <tr><td style="padding:20px 40px 0;font-family:Arial,Helvetica,sans-serif;">
    <p style="font-size:15px;line-height:1.6;color:{INK};margin:0 0 16px;">
      Dear {e(row['greeting'])},</p>
    <p style="font-size:15px;line-height:1.6;color:{INK};margin:0 0 16px;">
      Congratulations on the start of the new school year. This week,
      campuses across Texas open their doors &mdash; we know it&rsquo;s the
      busiest week on your calendar, and we wish {e(name)}&rsquo;s students,
      teachers and staff a great 2026&ndash;27.</p>
    <p style="font-size:15px;line-height:1.6;color:{INK};margin:0 0 16px;">
      We&rsquo;re writing because we built something for you, and this felt
      like the right week to hand it over. Texas publishes every number about
      {e(name)} &mdash; finances, results, bonds, debt, boundaries &mdash; but
      across ten different state files that never talk to each other, which
      means the people your numbers describe can rarely see the whole
      picture. We believe transparency shouldn&rsquo;t take a records
      request. So we connected the files. This isn&rsquo;t a pitch;
      it&rsquo;s a gift: your district&rsquo;s complete public record,
      synthesized, on one page. A few things it already shows:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:6px 0 8px;">{bullets}</table>
    <p style="font-size:13px;line-height:1.5;color:{MUT};margin:0 0 22px;">
      {e(row['hook'])}</p>
    <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 26px;"><tr>
      <td style="background:{BLUE};border-radius:4px;">
        <a href="{e(link)}"
           style="display:inline-block;padding:13px 26px;color:#ffffff;
                  font-family:Arial,sans-serif;font-size:15px;font-weight:bold;
                  text-decoration:none;">See {e(name)}&rsquo;s full report &rarr;</a>
      </td></tr></table>
  </td></tr>
  <tr><td style="padding:0 40px;"><hr style="border:none;border-top:1px solid #e4e4e0;margin:0;"></td></tr>
  <tr><td style="padding:22px 40px 0;font-family:Arial,Helvetica,sans-serif;">
    <p style="font-size:14px;line-height:1.6;color:{INK};margin:0 0 12px;">
      <b>Who we are.</b> TAG ai works at the intelligence layer of data: we
      don&rsquo;t replace the systems you already have, we connect them and
      make them answer questions. This portal is our proof &mdash; 6.6 million
      public data points on all 1,310 districts, every figure linked to the
      state file it came from, and it refuses to guess.</p>
    <img src="{SITE}/static/tag-pipeline.png" width="520"
         alt="TAG ai: ten official state sources in, one intelligence layer,
              plain-English answers out"
         style="width:100%;max-width:520px;height:auto;margin:6px 0 16px;border:1px solid #e4e4e0;">
    <p style="font-size:14px;line-height:1.6;color:{INK};margin:0 0 22px;">
      If you&rsquo;d like a 20-minute walkthrough of {e(name)}&rsquo;s page
      &mdash; or to talk about what the same intelligence layer could do on
      your district&rsquo;s own data &mdash; just reply to this email. And if
      any figure looks wrong, tell us: we publish corrections with credit.</p>
    <p style="font-size:14px;line-height:1.7;color:{INK};margin:0 0 28px;">
      <b>Gus Sanchez</b><br>
      TAG ai<br>
      <a href="tel:+19092686875" style="color:{INK};text-decoration:none;">909-268-6875</a><br>
      <a href="mailto:gus@ubntag.com" style="color:{INK};">gus@ubntag.com</a></p>
  </td></tr>
  <tr><td style="padding:18px 40px 26px;background:#fafaf8;border-top:1px solid #e4e4e0;
               font-family:Arial,sans-serif;font-size:11.5px;line-height:1.6;color:{MUT};">
    All figures are derived from public records published by the State of
    Texas (TEA, Bond Review Board, Comptroller); sources and methods:
    <a href="{SITE}/sources" style="color:{MUT};">{SITE.replace('https://','')}/sources</a>.
    Your address comes from TEA&rsquo;s public district directory (AskTED).<br>
    Artificial intelligence was used in the preparation of this report and this
    email, orchestrated across our entire system. Figures carry a margin of
    error and are provided &ldquo;as&nbsp;is&rdquo; without warranty; verify
    independently before acting &mdash; use is at your own risk.
    <a href="{SITE}/transparency" style="color:{MUT};">How this was made, and
    the full terms</a>.<br>
    {disclose}This is a commercial message from TAG ai &middot; {e(postal)}<br>
    Don&rsquo;t want to hear from us? <a href="{e(unsubscribe)}"
    style="color:{MUT};">Unsubscribe</a> and we won&rsquo;t write again.
  </td></tr>
</table>
</td></tr></table>{pixel}</body></html>"""

    text = (f"Dear {row['greeting']},\n\n"
            f"Congratulations on the start of the new school year — we wish "
            f"{name}'s students, teachers and staff a great 2026–27.\n\n"
            f"We're writing because we built something for you, and this felt "
            f"like the right week to hand it over. Texas publishes every "
            f"number about {name} — but across ten state files that never "
            f"talk to each other, so the people the numbers describe can "
            f"rarely see the whole picture. We believe transparency "
            f"shouldn't take a records request. So we connected the files. "
            f"Your district's complete public record, on one page:\n\n"
            + "".join(f"  • {s}\n" for s in insights) +
            f"\n{row['hook']}\n\n"
            f"See {name}'s full report: {link}\n\n"
            f"Who we are: TAG ai works at the intelligence layer of data — we "
            f"connect the systems you already have and make them answer "
            f"questions. Reply to this email for a 20-minute walkthrough, or "
            f"to talk about your own data. If any figure looks wrong, tell "
            f"us — we publish corrections with credit.\n\n"
            f"Gus Sanchez\n"
            f"TAG ai\n"
            f"909-268-6875\n"
            f"gus@ubntag.com\n\n"
            f"Sources and methods: {SITE}/sources\n"
            f"AI disclosure: artificial intelligence was used in the "
            f"preparation of this report and this email, orchestrated across "
            f"our entire system. Figures carry a margin of error and are "
            f"provided as-is without warranty; verify independently before "
            f"acting — use is at your own risk. How this was made and full "
            f"terms: {SITE}/transparency\n"
            + (f"This email carries a code unique to you, so we can see "
               f"whether it was opened and whether the report was useful. If "
               f"you'd rather we didn't, don't click the link — or reply and "
               f"we'll delete the record. {SITE}/about#privacy\n"
               if rid else "") +
            f"This is a commercial message from TAG ai · {postal}\n"
            f"Unsubscribe: {unsubscribe}\n")
    return body, text


def resend_request(path: str, key: str, payload: dict | None = None,
                   timeout: int = 30) -> dict:
    """One Resend API call. Blocking — server callers run it in a threadpool.

    `timeout` exists because the server-side drain runs against a wall-clock
    budget inside one serverless invocation: a 30s hang on the tail message
    would overrun the function's own duration cap and strand the rest of the
    batch, so the drain passes a shorter timeout than the laptop default.
    """
    data = json.dumps(payload).encode() if payload is not None else None
    # The User-Agent matters: api.resend.com sits behind Cloudflare, which
    # 403s Python's default urllib UA ("error 1010") while the same request
    # from curl succeeds. Same trap as the Supabase Management API — the 403
    # is NOT an auth failure, do not chase the key.
    r = urllib.request.Request(
        f"{API}{path}", data=data, method="POST" if data else "GET",
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json",
                 "User-Agent": "txisd-outreach/1.0 (+https://txisd.dev)"})
    with urllib.request.urlopen(r, timeout=timeout,
                                context=ssl.create_default_context()) as resp:
        return json.load(resp)


def domain_verified(key: str, from_addr: str) -> bool:
    """Refuse a mass send from an unverified domain — Resend would accept the
    call and every message would land in spam or bounce."""
    domain = from_addr.split("@")[-1].rstrip(">").strip()
    got = resend_request("/domains", key)
    for d in got.get("data", []):
        if d.get("name") == domain and d.get("status") == "verified":
            return True
    return False
