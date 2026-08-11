#!/usr/bin/env python3
"""
CENTINELA OCCIDENTE — Módulo de Entrega
Genera informe diario para AURA MINERALS y lo envía a las 8:00 PM Honduras.
"""
import os
import sys
import json
import smtplib
from collections import Counter, defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/social_monitor/.env"), override=True)

import anthropic
import db
from config import (
    REPORT_RECIPIENTS, REPORTS_DIR, SENDER_NAME,
    OPPOSITION_ACTORS, TRADITIONAL_MEDIA, LOCAL_MEDIA, AURA_ACCOUNTS,
    MONITOR_KEYWORDS,
)

GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

CLIENTE_CONTACTO = "Max González / INSERCO"


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Métricas de fuentes ──────────────────────────────────────────────────────

def build_source_activity(posts: list, news: list) -> dict:
    """
    Calcula qué actores tuvieron actividad y cuáles no,
    por categoría. Devuelve diccionarios para el prompt.
    """
    active_actors = set(p["actor"] for p in posts) | set(n["actor"] for n in news)

    def inactive(source_dict):
        return [name for name in source_dict if name not in active_actors]

    return {
        "inactivos_opositores":  inactive(OPPOSITION_ACTORS),
        "inactivos_trad":        inactive(TRADITIONAL_MEDIA),
        "inactivos_locales":     inactive(LOCAL_MEDIA),
    }


def build_metrics(posts: list, news: list) -> dict:
    """
    Construye las métricas de desglose completo:
    total escaneado → filtrado por relevancia → por actor.
    """
    total_escaneado   = len(posts) + len(news)

    keywords_lower = [k.lower() for k in MONITOR_KEYWORDS]
    def is_relevant(text):
        t = (text or "").lower()
        return any(k in t for k in keywords_lower)

    relevant_posts = [p for p in posts if is_relevant(p.get("text", ""))]
    relevant_news  = [n for n in news  if is_relevant((n.get("title","") + " " + n.get("text","")))]
    total_relevante = len(relevant_posts) + len(relevant_news)

    by_actor = Counter(
        p["actor"] for p in (relevant_posts + relevant_news)
    )

    by_platform = Counter(p.get("platform","?") for p in posts)

    return {
        "total_escaneado":  total_escaneado,
        "total_relevante":  total_relevante,
        "descartado":       total_escaneado - total_relevante,
        "pct_descartado":   round((total_escaneado - total_relevante) / max(total_escaneado, 1) * 100),
        "por_actor":        dict(by_actor.most_common(10)),
        "por_plataforma":   dict(by_platform),
        "posts_total":      len(posts),
        "news_total":       len(news),
    }


# ── Preparar datos para Claude ───────────────────────────────────────────────

def build_data_summary(posts: list, news: list) -> str:
    def fmt(items, max_items=12):
        return [
            {
                "actor":    i.get("actor"),
                "text":     (i.get("text") or i.get("title") or "")[:250],
                "url":      i.get("url", ""),
                "platform": i.get("platform", ""),
            }
            for i in items[:max_items]
        ]

    source_activity = build_source_activity(posts, news)
    metrics         = build_metrics(posts, news)
    alerts          = db.get_pending_alerts()

    return json.dumps({
        "cliente":              fmt([p for p in posts if p.get("categoria") == "CLIENTE"]),
        "opositores":           fmt([p for p in posts if p.get("categoria") == "OPOSITOR"]),
        "medios_trad":          fmt([p for p in posts if p.get("categoria") == "MEDIO_TRADICIONAL"]),
        "noticias_trad":        fmt([n for n in news  if n.get("categoria") == "MEDIO_TRADICIONAL"]),
        "medios_locales":       fmt([p for p in posts if p.get("categoria") == "MEDIO_LOCAL"]),
        "alertas":              [
            {
                "actor":   a.get("actor"), "platform": a.get("platform"),
                "keyword": a.get("keyword"), "text": (a.get("text") or "")[:300],
                "url":     a.get("url"), "level": a.get("level"),
            }
            for a in alerts
        ],
        "fuentes_inactivas":    source_activity,
        "metricas":             metrics,
    }, ensure_ascii=False, indent=2)


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres CENTINELA OCCIDENTE, el motor de análisis de inteligencia digital
desarrollado por INSERCO para el cliente AURA MINERALS.

CONTEXTO:
- Cliente: AURA MINERALS (también conocida como Minosa, Minerales de Occidente)
- Operación: Mina San Andrés / Mina Azacualpa, Cerro Los Hornillos — La Unión, Copán, Honduras
- Misión: detectar riesgos reputacionales, narrativas negativas, crisis ambientales/sociales
  y oportunidades de comunicación para proteger la operación.
- Actores opositores monitoreados: Radio Dignidad, El Referente, Movimiento Amplio,
  Víctor Fernández, Criterio HN, Canal 6, Contra Corriente, Radio Progreso, ASONOG.

REGLAS OBLIGATORIAS DE FORMATO Y CONTENIDO:
1. Usa ÚNICAMENTE etiquetas HTML válidas. NUNCA uses markdown.
2. La red social X (antes Twitter) siempre se llama "X", nunca "Twitter".
3. Si no hay datos: <p><em>Sin actividad registrada.</em></p>
4. Analiza ÚNICAMENTE los datos reales. No inventes información.
5. ESTRUCTURA EN DOS CAPAS: primero la CAPA 1 (Resumen Ejecutivo), luego la CAPA 2 (Anexo Detallado).
6. Cada hallazgo se desarrolla UNA sola vez. El Resumen Ejecutivo solo referencia brevemente
   lo que el Anexo desarrolla; NUNCA repitas el mismo contexto, cita o cifra en ambas capas.
7. FUENTES INACTIVAS: no crees un encabezado individual por cada fuente sin actividad.
   Agrupa todas en una sola línea: "Sin actividad registrada: [lista separada por comas]".
8. ALERTAS CON PERSONAS INDIVIDUALES: el sujeto de la alerta es siempre la organización
   o la narrativa emergente, no la persona. El nombre puede aparecer como contexto en el cuerpo,
   pero nunca en el título/clasificación de la alerta.
9. MÉTRICAS: siempre muestra el desglose completo — total escaneado → filtrado por relevancia →
   por actor. Si el total relevante es muy inferior al escaneado, indica el % descartado
   por no relacionarse con el cliente o su entorno de riesgo.
10. Resumen Ejecutivo: lenguaje directo, sin subtítulos decorativos, lectura < 2 minutos.
    Incluye: nivel de riesgo, narrativa dominante, hecho más relevante, alertas activas
    (solo titular 1-2 líneas c/u), acciones recomendadas (solo título + urgencia),
    y la métrica clave: publicaciones relevantes / total escaneado.
"""

DAILY_PROMPT = """Analiza los datos de monitoreo digital del día {date} y genera el
INFORME DIARIO de CENTINELA OCCIDENTE para AURA MINERALS.

PERÍODO: Últimas 24 horas ({period_start} → {period_end})

DATOS:
{data}

Genera el informe en HTML limpio siguiendo la ESTRUCTURA EN DOS CAPAS:

═══════════════════════════════════════════════════════════
CAPA 1 — RESUMEN EJECUTIVO
(Máx. 1 página — solo lo que un ejecutivo necesita leer)
═══════════════════════════════════════════════════════════

<div class="exec-summary">
<h2>RESUMEN EJECUTIVO · {date}</h2>

Escribe una narrativa fluida (3-5 párrafos sin sub-encabezados decorativos) que cubra:
- Nivel de riesgo del día: ALTO / MEDIO / BAJO con razón en una oración.
- Narrativa dominante (qué dice el entorno sobre Aura Minerals hoy).
- Hecho más relevante del período.
- Alertas activas: solo el titular de cada una y urgencia (1-2 líneas por alerta).
  Si involucra a una persona, el sujeto debe ser la organización/narrativa, no el individuo.
- Acciones recomendadas: solo título + nivel de urgencia (ALTA/MEDIA/BAJA), sin contexto.
- Métrica clave al final: "Publicaciones relevantes: X de Y escaneadas (Z% relacionadas con el cliente)."

No uses listas de viñetas en el Resumen Ejecutivo. Prosa directa.
</div>

═══════════════════════════════════════════════════════════
CAPA 2 — ANEXO DETALLADO
(Contexto completo para el equipo — sin repetir lo del Resumen)
═══════════════════════════════════════════════════════════

<h2>A. COBERTURA Y SENTIMIENTO — AURA MINERALS</h2>
Análisis completo de todo lo publicado sobre Aura Minerals / Minosa / Azacualpa.
<ul>
<li><strong>Sentimiento general:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>Desglose estimado:</strong> X% Positivo / X% Neutral / X% Negativo</li>
<li><strong>Publicación más relevante:</strong> [fuente y contenido]</li>
<li><strong>Narrativa en construcción:</strong> [descripción]</li>
<li><strong>Temas asociados hoy:</strong> [lista]</li>
</ul>

<h2>B. ACTORES OPOSITORES — ANÁLISIS DETALLADO</h2>
Para cada actor CON actividad relevante, crea una subsección <h3>:
<h3>[Nombre del actor]</h3>
<ul>
<li><strong>Actividad:</strong> [resumen de publicaciones]</li>
<li><strong>Narrativa:</strong> [mensaje que están construyendo]</li>
<li><strong>Nivel de amenaza:</strong> ALTO / MEDIO / BAJO</li>
<li><strong>Alcance estimado:</strong> alto / medio / bajo</li>
</ul>
Al final de esta sección, UNA sola línea para los inactivos:
<p><em>Sin actividad registrada: [lista de actores inactivos separados por coma]</em></p>

<h2>C. MEDIOS DE COMUNICACIÓN TRADICIONALES</h2>
<ul>
<li><strong>Sentimiento general:</strong> POSITIVO / NEUTRAL / NEGATIVO / MIXTO</li>
<li><strong>Medio más activo:</strong> [nombre y enfoque]</li>
<li><strong>Nota más destacada:</strong> [medio y titular]</li>
<li><strong>Tono dominante:</strong> [descripción]</li>
</ul>
<p><em>Sin actividad registrada: [lista de medios sin cobertura]</em></p>

<h2>D. MEDIOS LOCALES — COPÁN</h2>
<ul>
<li><strong>Actividad registrada:</strong> [resumen o "Sin datos"]</li>
<li><strong>Tono:</strong> [descripción o "Sin datos"]</li>
<li><strong>Nota más relevante:</strong> [contenido o "Sin datos"]</li>
</ul>
<p><em>Sin actividad registrada: [lista de medios locales inactivos]</em></p>

<h2>E. ALERTAS DE CRISIS — CONTEXTO COMPLETO</h2>
Para cada alerta (el sujeto es siempre la organización o narrativa, nunca el individuo):
<h3>[Organización/Narrativa — NO el nombre de persona]</h3>
<ul>
<li><strong>Actor que publicó:</strong> [nombre de la organización/medio]</li>
<li><strong>Plataforma:</strong> [X / Facebook / RSS]</li>
<li><strong>Keyword detectada:</strong> [palabra clave]</li>
<li><strong>Nivel:</strong> ALTO / MEDIO / BAJO</li>
<li><strong>Descripción completa:</strong> [qué se dice, contexto y alcance estimado]</li>
<li><strong>Acción sugerida:</strong> [respuesta recomendada y tiempo]</li>
</ul>
Si no hay alertas: <p><em>Sin alertas de crisis en las últimas 24 horas.</em></p>

<h2>F. OPORTUNIDADES DETECTADAS</h2>
<ul>
<li><strong>Oportunidad:</strong> [descripción concreta]</li>
<li><strong>Cómo aprovecharla:</strong> [acción específica]</li>
<li><strong>Urgencia:</strong> Inmediata / Esta semana / Este mes</li>
</ul>
Si no hay oportunidades: <p><em>Sin oportunidades destacadas hoy.</em></p>

<h2>G. PALABRAS Y FRASES MÁS UTILIZADAS</h2>
Las 10 palabras/frases más repetidas asociadas a Aura Minerals:
<table>
  <tr><th>Palabra/Frase</th><th>Frecuencia</th><th>Contexto de uso</th></tr>
  [filas]
</table>

<h2>H. MÉTRICAS DETALLADAS</h2>
Muestra el desglose completo — nunca dejes una cifra total sin su explicación:
<ul>
<li><strong>Total escaneado:</strong> [N posts + N noticias RSS = N total]</li>
<li><strong>Total relevante (relacionado con el cliente):</strong> [N — X% del total]</li>
<li><strong>Descartado por no relacionarse:</strong> [N — Y% del total]</li>
<li><strong>Por actor (top activos):</strong> [lista Actor: N publicaciones]</li>
<li><strong>Por plataforma:</strong> [X: N · Facebook: N · RSS: N]</li>
<li><strong>Alertas generadas:</strong> [N]</li>
<li><strong>Actor más activo:</strong> [nombre]</li>
</ul>

<h2>I. ACCIONES RECOMENDADAS — CONTEXTO COMPLETO</h2>
Exactamente 3 acciones priorizadas. El Resumen Ejecutivo solo puso el título y urgencia;
aquí va el contexto completo:
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

def analyze_daily(data_summary: str) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    now    = datetime.now()
    since  = (now - timedelta(hours=24)).strftime("%d/%m %H:%M")

    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=12000,
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
        body  {{ font-family: Arial, sans-serif; max-width: 980px; margin: 0 auto; color: #222; }}

        /* ── Resumen Ejecutivo — fondo levemente diferenciado ── */
        .exec-summary {{
          background: #fafff9;
          border: 2px solid #1a5e1a;
          border-radius: 8px;
          padding: 20px 24px;
          margin-bottom: 28px;
        }}
        .exec-summary h2 {{
          margin-top: 0;
          padding: 0 0 10px 0;
          border-bottom: 2px solid #1a5e1a;
          background: transparent;
          color: #1a5e1a;
          font-size: 16px;
          letter-spacing: 0.5px;
          text-transform: uppercase;
        }}
        .exec-summary p {{ line-height: 1.7; margin: 0 0 12px 0; font-size: 14px; }}

        /* ── Separador de capas ── */
        .layer-divider {{
          border: none;
          border-top: 3px dashed #1a5e1a;
          margin: 32px 0 24px;
          opacity: 0.35;
        }}
        .layer-label {{
          text-align: center;
          font-size: 11px;
          color: #888;
          letter-spacing: 2px;
          text-transform: uppercase;
          margin: -14px 0 24px;
        }}

        h2    {{ margin-top: 28px; padding: 8px 14px; border-radius: 6px;
                 background: #f0f4f8; border-left: 4px solid #1a5e1a; font-size: 15px; }}
        h3    {{ color: #1a5e1a; margin-top: 18px; font-size: 14px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
        th    {{ background: #1a5e1a; color: #fff; padding: 9px 12px; text-align: left; }}
        td    {{ padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
        tr:nth-child(even) {{ background: #f7f9fc; }}
        a     {{ color: #2980b9; }}
        p     {{ line-height: 1.6; }}
        ul    {{ margin: 6px 0; padding-left: 20px; }}
        li    {{ margin-bottom: 4px; line-height: 1.5; font-size: 14px; }}

        /* ── Confidencial badge ── */
        .confidencial-badge {{
          display: inline-block;
          background: #c0392b;
          color: #fff;
          font-size: 10px;
          font-weight: 900;
          letter-spacing: 2px;
          padding: 3px 10px;
          border-radius: 3px;
          margin-left: 10px;
          vertical-align: middle;
        }}

        /* ── Watermark para impresión/PDF ── */
        @media print {{
          body::before {{
            content: "CONFIDENCIAL";
            position: fixed;
            top: 40%;
            left: 50%;
            transform: translate(-50%, -50%) rotate(-45deg);
            font-size: 80px;
            font-weight: 900;
            color: rgba(192, 57, 43, 0.08);
            pointer-events: none;
            z-index: 9999;
            white-space: nowrap;
          }}
        }}
      </style>
    </head>
    <body>
      <!-- ENCABEZADO CON CONFIDENCIAL -->
      <div style="background:#1a5e1a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0">
        <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
          <span style="font-size:40px">🗺️</span>
          <div style="flex:1">
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
              <h1 style="margin:0;font-size:22px;font-weight:900;letter-spacing:1px">CENTINELA OCCIDENTE</h1>
              <span style="background:#c0392b;color:#fff;font-size:10px;font-weight:900;
                           letter-spacing:2px;padding:3px 10px;border-radius:3px">CONFIDENCIAL</span>
            </div>
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
        <!-- Chips de cobertura -->
        <div style="background:#e8f5e9;border-left:4px solid #1a5e1a;
                    padding:10px 14px;border-radius:4px;margin-bottom:20px;font-size:13px">
          <strong>Monitoreando:</strong> Aura Minerals · Minosa · Mina Azacualpa · Cerro Los Hornillos<br>
          <strong>Opositores:</strong> Radio Dignidad · El Referente · Movimiento Amplio · Víctor Fernández ·
          Criterio HN · Canal 6 · Contra Corriente · Radio Progreso · ASONOG<br>
          <strong>Medios:</strong> HCH · TSI · Tu Nota · Once Noticias · QHubo · La Prensa ·
          La Tribuna · HRN · Radio América · Cadena Voces · Copan TV · Ramón Rojas · Jorge Posadas
        </div>

        {analysis_html}

        <!-- LÍNEA FINAL DE RESTRICCIÓN -->
        <p style="font-size:12px;color:#888;border-top:1px solid #eee;
                  padding-top:12px;margin-top:28px;text-align:center">
          Este documento no debe reenviarse ni citarse sin autorización de {CLIENTE_CONTACTO}.
        </p>
      </div>

      <!-- PIE DE PÁGINA -->
      <p style="color:#aaa;font-size:11px;text-align:center;margin-top:10px;padding:0 10px">
        🗺️ CENTINELA OCCIDENTE — Desarrollado por INSERCO · Inteligencia Digital Honduras<br>
        <span style="color:#c0392b;font-weight:bold">CONFIDENCIAL</span> —
        Distribución limitada a AURA MINERALS y equipo Inserco autorizado.
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

        subject = (
            f"🗺️ [CONFIDENCIAL] CENTINELA OCCIDENTE — "
            f"{now.strftime('%d/%m/%Y')} · Informe Diario"
        )
        log("→ Enviando informe…")
        send_email(email_html, subject)
    else:
        log("  ⚠️  Sin datos para el informe (¿collect.py corrió?)")

    log("✓ Entrega completa")
    log("=" * 60)


if __name__ == "__main__":
    main()
