#!/usr/bin/env python3
"""
CENTINELA OCCIDENTE — Módulo de Entrega
Genera informe diario para AURA MINERALS y lo envía a las 8:00 PM Honduras.
"""
import os
import sys
import json
import smtplib
from collections import Counter
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/social_monitor/.env"), override=True)

import anthropic
import db
from config import REPORT_RECIPIENTS, REPORTS_DIR, SENDER_NAME

GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres CENTINELA OCCIDENTE, el motor de análisis de inteligencia digital
desarrollado por INSERCO para el cliente AURA MINERALS.

CONTEXTO:
- Cliente principal: AURA MINERALS (también conocida como Minosa, Minerales de Occidente)
- Operación: Mina San Andrés / Mina Azacualpa, Cerro Los Hornillos — La Unión, Copán, Honduras
- Tu misión: detectar riesgos reputacionales, narrativas negativas, crisis ambientales/sociales
  y oportunidades de comunicación para proteger la operación de la empresa.
- Actores opositores monitoreados: Radio Dignidad, El Referente, Movimiento Amplio,
  Víctor Fernández, Criterio HN, Canal 6, Contra Corriente, Radio Progreso, ASONOG.

INSTRUCCIONES DE FORMATO:
- Usa ÚNICAMENTE etiquetas HTML válidas. NUNCA uses markdown.
- La red social X (antes Twitter) se llama SIEMPRE "X", nunca "Twitter".
- Si no hay datos: <p><em>Sin actividad registrada.</em></p>
- Analiza ÚNICAMENTE los datos reales. No inventes información."""

DAILY_PROMPT = """Analiza los datos de monitoreo digital del día {date} y genera el
INFORME DIARIO de CENTINELA OCCIDENTE para AURA MINERALS.

PERÍODO: Últimas 24 horas ({period_start} → {period_end})

DATOS:
{data}

Genera el informe en HTML limpio con EXACTAMENTE estas 10 secciones:

<h2>📊 1. RESUMEN EJECUTIVO</h2>
<ul>
<li><strong>Nivel de riesgo del día:</strong> ALTO / MEDIO / BAJO — [razón en una oración]</li>
<li><strong>Narrativa dominante sobre Aura Minerals:</strong> [descripción]</li>
<li><strong>Hecho más relevante:</strong> [descripción]</li>
<li><strong>Actores más activos:</strong> [lista]</li>
<li><strong>Acción inmediata requerida:</strong> Sí / No — [por qué]</li>
</ul>

<h2>🏭 2. COBERTURA Y SENTIMIENTO — AURA MINERALS</h2>
Análisis de todo lo publicado sobre Aura Minerals / Minosa / La Bufa / Azacualpa.
<ul>
<li><strong>Sentimiento general:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>% estimado:</strong> [X% Positivo / X% Neutral / X% Negativo]</li>
<li><strong>Publicación más relevante:</strong> [fuente y contenido]</li>
<li><strong>Narrativa en construcción:</strong> [descripción]</li>
<li><strong>Temas asociados hoy:</strong> [lista]</li>
</ul>

<h2>⚔️ 3. MEDIOS Y ACTORES OPOSITORES</h2>
Análisis de Radio Dignidad, El Referente, Movimiento Amplio, Víctor Fernández,
Criterio HN, Canal 6, Contra Corriente, Radio Progreso, ASONOG.
Para cada actor con actividad relevante:
<h3>[Nombre del actor]</h3>
<ul>
<li><strong>Actividad:</strong> [resumen de publicaciones]</li>
<li><strong>Narrativa:</strong> [qué mensaje están construyendo]</li>
<li><strong>Nivel de amenaza:</strong> ALTO / MEDIO / BAJO</li>
<li><strong>Alcance estimado:</strong> [alto / medio / bajo]</li>
</ul>
Si no hubo actividad relevante: <p><em>Sin actividad de actores opositores en las últimas 24 horas.</em></p>

<h2>📺 4. MEDIOS DE COMUNICACIÓN TRADICIONALES</h2>
Análisis de HCH, TSI, Tu Nota, Once Noticias, QHubo, La Prensa, La Tribuna, HRN, Radio América, Radio Cadena Voces.
<ul>
<li><strong>Sentimiento general:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>Medio más activo cubriendo el tema:</strong> [nombre y enfoque]</li>
<li><strong>Nota más destacada:</strong> [medio y titular]</li>
<li><strong>Tono dominante:</strong> [descripción]</li>
</ul>
Si no hubo cobertura: <p><em>Sin cobertura en medios tradicionales en las últimas 24 horas.</em></p>

<h2>📻 5. MEDIOS LOCALES</h2>
Análisis de Copan TV, Ramón Rojas, Jorge Posadas y medios de La Unión, Copán.
<ul>
<li><strong>Actividad registrada:</strong> [resumen o "Sin datos"]</li>
<li><strong>Tono:</strong> [descripción o "Sin datos"]</li>
<li><strong>Nota más relevante:</strong> [contenido o "Sin datos"]</li>
</ul>

<h2>🚨 6. ALERTAS DE CRISIS</h2>
Publicaciones que contienen palabras clave críticas (derrames, contaminación, represión,
protestas, expropiación, maya, chortí, mina a cielo abierto, licencias ambientales, etc.)
Para cada alerta:
<ul>
<li><strong>Actor:</strong> [quién lo publicó]</li>
<li><strong>Plataforma:</strong> [X / Facebook / RSS]</li>
<li><strong>Keyword detectada:</strong> [palabra clave]</li>
<li><strong>Nivel:</strong> ALTO / MEDIO / BAJO</li>
<li><strong>Descripción:</strong> [qué se dice y alcance estimado]</li>
<li><strong>Acción sugerida:</strong> [respuesta recomendada y tiempo]</li>
</ul>
Si no hay alertas: <p><em>Sin alertas de crisis en las últimas 24 horas.</em></p>

<h2>💡 7. OPORTUNIDADES DETECTADAS</h2>
Espacios para posicionamiento positivo, corrección de narrativas o comunicación proactiva.
<ul>
<li><strong>Oportunidad:</strong> [descripción concreta]</li>
<li><strong>Cómo aprovecharla:</strong> [acción específica]</li>
<li><strong>Urgencia:</strong> Inmediata / Esta semana / Este mes</li>
</ul>
Si no hay oportunidades: <p><em>Sin oportunidades destacadas hoy.</em></p>

<h2>🔤 8. PALABRAS MÁS UTILIZADAS</h2>
Las 10 palabras o frases más repetidas en el monitoreo del día asociadas a Aura Minerals.
Genera una tabla HTML:
<table>
  <tr><th>Palabra/Frase</th><th>Frecuencia</th><th>Contexto</th></tr>
  [filas con los términos más mencionados]
</table>

<h2>📈 9. MÉTRICAS DEL DÍA</h2>
<ul>
<li><strong>Total de publicaciones monitoreadas:</strong> [número]</li>
<li><strong>Publicaciones sobre Aura Minerals:</strong> [número]</li>
<li><strong>Actor más activo:</strong> [nombre]</li>
<li><strong>Plataforma más activa:</strong> [X / Facebook / RSS]</li>
<li><strong>Publicación con mayor alcance estimado:</strong> [actor y contenido]</li>
<li><strong>Alertas generadas:</strong> [número]</li>
</ul>

<h2>✅ 10. ACCIONES RECOMENDADAS</h2>
Exactamente 3 acciones priorizadas por urgencia.
<h3>[Título Acción 1]</h3>
<ul>
<li><strong>Contexto:</strong> [por qué es necesaria ahora]</li>
<li><strong>Acción:</strong> [qué hacer exactamente]</li>
<li><strong>Urgencia:</strong> ALTA / MEDIA / BAJA</li>
</ul>
<h3>[Título Acción 2]</h3>
<ul>
<li><strong>Contexto:</strong> [...]</li>
<li><strong>Acción:</strong> [...]</li>
<li><strong>Urgencia:</strong> [...]</li>
</ul>
<h3>[Título Acción 3]</h3>
<ul>
<li><strong>Contexto:</strong> [...]</li>
<li><strong>Acción:</strong> [...]</li>
<li><strong>Urgencia:</strong> [...]</li>
</ul>"""


# ── Análisis con Claude ──────────────────────────────────────────────────────

def build_data_summary(posts: list, news: list) -> str:
    summary = {
        "cliente":           [p for p in posts if p.get("categoria") == "CLIENTE"],
        "opositores":        [p for p in posts if p.get("categoria") == "OPOSITOR"],
        "medios_trad":       [p for p in posts if p.get("categoria") == "MEDIO_TRADICIONAL"],
        "noticias_trad":     [n for n in news  if n.get("categoria") == "MEDIO_TRADICIONAL"],
        "medios_locales":    [p for p in posts if p.get("categoria") == "MEDIO_LOCAL"],
        "total_posts":       len(posts),
        "total_news":        len(news),
    }

    def fmt(items, max_items=10):
        return [{"actor": i.get("actor"), "text": (i.get("text") or "")[:200],
                 "url": i.get("url", ""), "platform": i.get("platform", "")}
                for i in items[:max_items]]

    return json.dumps({
        "cliente":       fmt(summary["cliente"]),
        "opositores":    fmt(summary["opositores"]),
        "medios_trad":   fmt(summary["medios_trad"]),
        "noticias_trad": fmt(summary["noticias_trad"]),
        "medios_locales":fmt(summary["medios_locales"]),
        "total_posts":   summary["total_posts"],
        "total_news":    summary["total_news"],
    }, ensure_ascii=False, indent=2)


def analyze_daily(data_summary: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    now    = datetime.now()
    since  = (now - timedelta(hours=24)).strftime("%d/%m %H:%M")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=10000,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": DAILY_PROMPT.format(
                date=now.strftime("%d de %B, %Y"),
                period_start=since,
                period_end=now.strftime("%d/%m %H:%M"),
                data=data_summary,
            )
        }]
    )
    return msg.content[0].text


# ── HTML del email ───────────────────────────────────────────────────────────

def build_email_html(analysis_html: str) -> str:
    now      = datetime.now()
    date_str = now.strftime("%d de %B, %Y · %H:%M")

    return f"""
    <html>
    <head>
      <style>
        body  {{ font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; color: #222; }}
        h2    {{ margin-top: 28px; padding: 8px 14px; border-radius: 6px;
                 background: #f0f4f8; border-left: 4px solid #1a5e1a; }}
        h3    {{ color: #1a5e1a; margin-top: 18px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
        th    {{ background: #1a5e1a; color: #fff; padding: 9px 12px; text-align: left; }}
        td    {{ padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
        tr:nth-child(even) {{ background: #f7f9fc; }}
        a     {{ color: #2980b9; }}
        p     {{ line-height: 1.6; }}
      </style>
    </head>
    <body>
      <div style="background:#1a5e1a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0">
        <div style="display:flex;align-items:center;gap:14px">
          <span style="font-size:40px">🗺️</span>
          <div>
            <h1 style="margin:0;font-size:22px;font-weight:900;letter-spacing:1px">CENTINELA OCCIDENTE</h1>
            <div style="font-size:12px;opacity:.80;margin-top:3px">
              Desarrollado por: <b>INSERCO</b> · Cliente: <b>AURA MINERALS</b>
            </div>
            <div style="font-size:11px;opacity:.65;margin-top:2px;text-transform:uppercase;letter-spacing:2px">
              Inteligencia Digital · La Unión, Copán, Honduras
            </div>
          </div>
        </div>
        <p style="margin:12px 0 0;opacity:.75;font-size:13px;
                  border-top:1px solid rgba(255,255,255,.25);padding-top:10px">
          📅 {date_str}
        </p>
      </div>

      <div style="padding:20px;background:#fff;border:1px solid #ddd;
                  border-top:none;border-radius:0 0 8px 8px">
        <div style="background:#e8f5e9;border-left:4px solid #1a5e1a;
                    padding:10px 14px;border-radius:4px;margin-bottom:20px;font-size:13px">
          <strong>Monitoreando:</strong> Aura Minerals · Minosa · Mina Azacualpa · Cerro Los Hornillos<br>
          <strong>Opositores:</strong> Radio Dignidad · El Referente · Movimiento Amplio · Víctor Fernández ·
          Criterio HN · Canal 6 · Contra Corriente · Radio Progreso · ASONOG<br>
          <strong>Medios:</strong> HCH · TSI · Tu Nota · Once Noticias · QHubo · La Prensa ·
          La Tribuna · HRN · Radio América · Cadena Voces · Copan TV
        </div>
        {analysis_html}
      </div>

      <p style="color:#aaa;font-size:11px;text-align:center;margin-top:12px">
        🗺️ CENTINELA OCCIDENTE — Desarrollado por INSERCO · Inteligencia Digital Honduras
      </p>
    </body>
    </html>"""


# ── Guardar reporte ──────────────────────────────────────────────────────────

def save_local_report(html: str) -> str:
    now      = datetime.now()
    dir_path = os.path.join(REPORTS_DIR, now.strftime("%Y"), now.strftime("%m"))
    os.makedirs(dir_path, exist_ok=True)
    filename = f"occidente_{now.strftime('%Y-%m-%d_%H%M')}.html"
    path     = os.path.join(dir_path, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"  ✓ Reporte guardado: {path}")
    return path


# ── Envío de email ───────────────────────────────────────────────────────────

def send_email(html: str, subject: str):
    recipients = REPORT_RECIPIENTS if isinstance(REPORT_RECIPIENTS, list) else [REPORT_RECIPIENTS]
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = GMAIL_USER
    msg["Bcc"]     = ", ".join(recipients)
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        s.sendmail(GMAIL_USER, recipients, msg.as_string())
    log(f"  ✓ Email enviado (BCC) a {len(recipients)} destinatario(s)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("CENTINELA OCCIDENTE — Módulo de entrega iniciado")
    db.init_db()

    now = datetime.now()

    log("→ Cargando datos de las últimas 24h…")
    posts = db.get_today_posts()
    news  = db.get_today_news()
    log(f"   {len(posts)} posts · {len(news)} noticias")

    if posts or news:
        log("→ Analizando con Claude AI…")
        data_summary  = build_data_summary(posts, news)
        analysis_html = analyze_daily(data_summary)

        email_html = build_email_html(analysis_html)
        save_local_report(email_html)

        subject = f"🗺️ CENTINELA OCCIDENTE — {now.strftime('%A %d/%m/%Y')} · Informe Diario"
        log("→ Enviando informe…")
        send_email(email_html, subject)
    else:
        log("  ⚠️  Sin datos para el informe (¿collect.py corrió?)")

    log("✓ Entrega completa")
    log("=" * 60)


if __name__ == "__main__":
    main()
