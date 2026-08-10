#!/usr/bin/env python3
"""
CENTINELA OCCIDENTE — Módulo de Recolección
Monitorea X (Nitter) + RSS para AURA MINERALS e actores relacionados.
"""
import os
import sys
import time
import random
import hashlib
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/social_monitor/.env"), override=True)

import requests
import feedparser
import db
from config import (
    AURA_ACCOUNTS, OPPOSITION_ACTORS, TRADITIONAL_MEDIA, LOCAL_MEDIA,
    NITTER_INSTANCES, CRISIS_KEYWORDS, MONITOR_KEYWORDS,
    REPORT_RECIPIENTS, MAX_TWEETS_PER_PROFILE, MAX_RSS_ITEMS, LOG_PATH,
)

GMAIL_USER         = os.environ.get("GMAIL_USER", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ── Nitter scraping ──────────────────────────────────────────────────────────

def get_nitter_instance():
    for instance in NITTER_INSTANCES:
        try:
            r = requests.get(f"{instance}/", timeout=5)
            if r.status_code == 200:
                return instance
        except Exception:
            continue
    return None


def fetch_nitter_rss(username: str, instance: str, max_items: int = MAX_TWEETS_PER_PROFILE):
    url = f"{instance}/{username}/rss"
    try:
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:max_items]:
            items.append({
                "source_id": entry.get("id", ""),
                "text":      entry.get("title", ""),
                "url":       entry.get("link", ""),
                "published": entry.get("published", ""),
            })
        return items
    except Exception as e:
        log(f"  [nitter] Error {username}@{instance}: {e}")
        return []


def scrape_twitter_accounts(accounts: dict, categoria: str, nitter: str):
    total = 0
    for name, data in accounts.items():
        handle = data.get("twitter")
        if not handle:
            continue
        log(f"  → X: @{handle} ({name})")
        tweets = fetch_nitter_rss(handle, nitter)
        for t in tweets:
            saved = db.save_post(
                source_id=t["source_id"],
                actor=name,
                categoria=categoria,
                platform="x",
                text=t["text"],
                url=t["url"],
            )
            if saved:
                total += 1
                check_crisis(t["text"], t["url"], name, "x")
        time.sleep(random.uniform(1.5, 3.5))
    return total


# ── RSS scraping ─────────────────────────────────────────────────────────────

def fetch_rss(name: str, url: str, categoria: str):
    try:
        feed = feedparser.parse(url)
        count = 0
        for entry in feed.entries[:MAX_RSS_ITEMS]:
            title = entry.get("title", "")
            text  = entry.get("summary", title)
            link  = entry.get("link", "")
            sid   = hashlib.md5(link.encode()).hexdigest() if link else None
            # Filter for relevance
            combined = (title + " " + text).lower()
            relevant = any(kw.lower() in combined for kw in MONITOR_KEYWORDS)
            if not relevant:
                continue
            saved = db.save_news(
                source_id=sid,
                actor=name,
                categoria=categoria,
                title=title,
                text=text[:500],
                url=link,
                published_at=entry.get("published", ""),
            )
            if saved:
                count += 1
                check_crisis(title + " " + text, link, name, "rss")
        return count
    except Exception as e:
        log(f"  [rss] Error {name}: {e}")
        return 0


# ── Crisis detection ─────────────────────────────────────────────────────────

def check_crisis(text: str, url: str, actor: str, platform: str):
    text_lower = text.lower()
    for kw in CRISIS_KEYWORDS:
        if kw.lower() in text_lower:
            db.save_alert(
                post_id=None,
                actor=actor,
                platform=platform,
                keyword=kw,
                text=text[:300],
                url=url,
                level="ALTO",
            )
            log(f"  🚨 ALERTA: '{kw}' detectado en {actor} [{platform}]")
            return


# ── Envío de alerta inmediata ────────────────────────────────────────────────

def send_immediate_alert(alerts: list):
    if not alerts or not GMAIL_USER:
        return

    rows_html = ""
    for a in alerts:
        rows_html += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #eee"><b>{a['actor']}</b></td>
          <td style="padding:8px;border-bottom:1px solid #eee">{a['platform'].upper()}</td>
          <td style="padding:8px;border-bottom:1px solid #eee;color:#c0392b"><b>{a['keyword']}</b></td>
          <td style="padding:8px;border-bottom:1px solid #eee">{(a['text'] or '')[:200]}</td>
          <td style="padding:8px;border-bottom:1px solid #eee">
            <a href="{a['url'] or '#'}">Ver fuente</a>
          </td>
        </tr>"""

    html = f"""<html><body>
    <div style="background:#c0392b;color:#fff;padding:16px 20px;border-radius:8px 8px 0 0">
      <h2 style="margin:0">🚨 CENTINELA OCCIDENTE — ALERTA DE CRISIS</h2>
      <p style="margin:6px 0 0;opacity:.85;font-size:13px">
        {datetime.now().strftime('%d/%m/%Y %H:%M')} · AURA MINERALS · Detección automática
      </p>
    </div>
    <div style="padding:20px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px">
      <p>Se detectaron <b>{len(alerts)}</b> publicación(es) con palabras clave de crisis:</p>
      <table style="width:100%;border-collapse:collapse;font-size:13px">
        <tr style="background:#2c3e50;color:#fff">
          <th style="padding:8px">Actor</th>
          <th style="padding:8px">Plataforma</th>
          <th style="padding:8px">Keyword</th>
          <th style="padding:8px">Extracto</th>
          <th style="padding:8px">Fuente</th>
        </tr>
        {rows_html}
      </table>
    </div>
    </body></html>"""

    try:
        recipients = REPORT_RECIPIENTS if isinstance(REPORT_RECIPIENTS, list) else [REPORT_RECIPIENTS]
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🚨 CENTINELA OCCIDENTE — ALERTA CRISIS · {datetime.now().strftime('%d/%m %H:%M')}"
        msg["From"]    = GMAIL_USER
        msg["To"]      = GMAIL_USER
        msg["Bcc"]     = ", ".join(recipients)
        msg.attach(MIMEText(html, "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            s.sendmail(GMAIL_USER, recipients, msg.as_string())
        log(f"  ✓ Alerta enviada a {len(recipients)} destinatario(s)")
        db.mark_alerts_notified()
    except Exception as e:
        log(f"  [email] Error enviando alerta: {e}")


# ── Ciclo principal ──────────────────────────────────────────────────────────

def collect_cycle():
    log("=" * 60)
    log("CENTINELA OCCIDENTE — Ciclo de recolección iniciado")
    db.init_db()

    nitter = get_nitter_instance()
    if not nitter:
        log("⚠️  Sin instancia Nitter disponible — saltando X")
    else:
        log(f"✓ Nitter: {nitter}")

    total_posts = 0
    total_news  = 0

    # 1. Aura Minerals oficial
    log("→ Monitoreando AURA MINERALS (X)…")
    if nitter:
        total_posts += scrape_twitter_accounts(AURA_ACCOUNTS, "CLIENTE", nitter)

    # 2. Actores opositores
    log("→ Monitoreando OPOSITORES (X)…")
    if nitter:
        total_posts += scrape_twitter_accounts(OPPOSITION_ACTORS, "OPOSITOR", nitter)

    # 3. Medios tradicionales
    log("→ Monitoreando MEDIOS TRADICIONALES (X + RSS)…")
    if nitter:
        total_posts += scrape_twitter_accounts(TRADITIONAL_MEDIA, "MEDIO_TRADICIONAL", nitter)
    for name, data in TRADITIONAL_MEDIA.items():
        if data.get("rss"):
            log(f"  → RSS: {name}")
            total_news += fetch_rss(name, data["rss"], "MEDIO_TRADICIONAL")

    # 4. Medios locales (solo Facebook por ahora — pendiente token)
    log("→ Medios locales: pendiente token Facebook")

    log(f"\n✓ Ciclo completo: {total_posts} posts · {total_news} noticias")

    # Alertas pendientes
    pending = db.get_pending_alerts()
    if pending:
        log(f"🚨 {len(pending)} alerta(s) — enviando notificación inmediata")
        send_immediate_alert(pending)
    else:
        log("✓ Sin alertas de crisis en este ciclo")

    log("=" * 60)


if __name__ == "__main__":
    collect_cycle()
