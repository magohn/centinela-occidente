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
from config import (
    REPORT_RECIPIENTS, REPORTS_DIR,
    OPPOSITION_ACTORS, TRADITIONAL_MEDIA, LOCAL_MEDIA,
    MONITOR_KEYWORDS,
)

GMAIL_USER         = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]


def log(msg):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ── Datos para Claude ────────────────────────────────────────────────────────

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

    # Actores con actividad real
    active_actors = set(p["actor"] for p in posts) | set(n["actor"] for n in news)

    def inactive(source_dict):
        return [name for name in source_dict if name not in active_actors]

    # Métricas de relevancia
    kws = [k.lower() for k in MONITOR_KEYWORDS]
    def relevant(text):
        return any(k in (text or "").lower() for k in kws)

    rel_posts = [p for p in posts if relevant(p.get("text", ""))]
    rel_news  = [n for n in news  if relevant(n.get("title","") + " " + n.get("text",""))]

    by_platform = Counter(p.get("platform","?") for p in posts)

    alerts = db.get_pending_alerts()

    return json.dumps({
        "cliente":          fmt([p for p in posts if p.get("categoria") == "CLIENTE"]),
        "seguimiento":      fmt([p for p in posts if p.get("categoria") == "OPOSITOR"]),
        "medios_trad":      fmt([p for p in posts if p.get("categoria") == "MEDIO_TRADICIONAL"]),
        "noticias_trad":    fmt([n for n in news  if n.get("categoria") == "MEDIO_TRADICIONAL"]),
        "medios_locales":   fmt([p for p in posts if p.get("categoria") == "MEDIO_LOCAL"]),
        "alertas":          [
            {
                "actor":   a.get("actor"), "platform": a.get("platform"),
                "keyword": a.get("keyword"), "text": (a.get("text") or "")[:300],
                "url":     a.get("url"), "level": a.get("level"),
            }
            for a in alerts
        ],
        "inactivos": {
            "seguimiento": inactive(OPPOSITION_ACTORS),
            "trad":        inactive(TRADITIONAL_MEDIA),
            "locales":     inactive(LOCAL_MEDIA),
        },
        "metricas": {
            "total_escaneado":  len(posts) + len(news),
            "total_relevante":  len(rel_posts) + len(rel_news),
            "descartado":       (len(posts) + len(news)) - (len(rel_posts) + len(rel_news)),
            "pct_relevante":    round((len(rel_posts) + len(rel_news)) / max(len(posts) + len(news), 1) * 100),
            "posts":            len(posts),
            "noticias_rss":     len(news),
            "alertas_total":    len(alerts),
            "por_plataforma":   dict(by_platform),
            "actor_mas_activo": Counter(p["actor"] for p in posts).most_common(1)[0] if posts else None,
        },
    }, ensure_ascii=False, indent=2)


# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres CENTINELA OCCIDENTE, el motor de análisis de inteligencia digital
desarrollado por INSERCO para el cliente AURA MINERALS.

CONTEXTO:
- Cliente: AURA MINERALS (Minosa, Minerales de Occidente)
- Operación: Mina San Andres / Mina Azacualpa, Cerro Los Hornillos — La Union, Copan, Honduras
- Mision: detectar riesgos reputacionales, narrativas negativas, crisis ambientales/sociales
  y oportunidades de comunicacion para proteger la operacion.
- Actores en seguimiento: Radio Dignidad, El Referente, Movimiento Amplio, Victor Fernandez,
  Criterio HN, Canal 6, Contra Corriente, Radio Progreso, ASONOG.

REGLAS OBLIGATORIAS — aplican sin excepcion a todos los informes:

R1. USA UNICAMENTE etiquetas HTML validas. NUNCA uses markdown.

R2. La red social X (antes Twitter) se llama SIEMPRE "X".

R3. Analiza UNICAMENTE los datos reales proporcionados. No inventes informacion.

R4. SIN EMOJIS NI ICONOS en ningun encabezado, viñeta ni cuerpo de texto.
    Los titulos van en texto plano con numeracion y mayusculas/negrita.

R5. TERMINOLOGIA — nunca usar "crisis" para personas u organizaciones opositoras
    como clasificacion por defecto. "Crisis" se reserva para amenaza real y directa
    contra la operacion del cliente. Usar "Alerta" o "Bajo el radar" en su lugar.
    La seccion 6 se llama "Alertas", no "Alertas de Crisis".

R6. CLASIFICACION CONFIDENCIAL siempre visible — el texto "CONFIDENCIAL" debe aparecer
    en el encabezado y en el pie de todo informe, sin excepcion.

R7. SIN NOMBRES PERSONALES en firma, atribucion ni pie de pagina. Cerrar unicamente con:
    "Informe generado por CENTINELA OCCIDENTE — Motor de Inteligencia Digital INSERCO."

R8. RELEVANCIA: no describir ni listar titulares de actores/medios sin relacion con el
    cliente, su operacion o su entorno de riesgo (agua, territorio, mineria, ambiente).
    Si un actor publico solo contenido de actualidad general, una sola linea:
    "[Actor]: actividad registrada sin relacion con el cliente."

R9. TERMINOLOGIA — reemplazar "Opositores" por "Medios en Seguimiento" en todo el documento.

R10. FUENTES INACTIVAS — no crear un encabezado individual por cada fuente sin actividad.
     Consolidar en una sola linea: "Sin actividad registrada: Fuente1, Fuente2, Fuente3."

R11. COLOR DE NIVEL DE RIESGO: cuando se indique nivel de riesgo o nivel de seguimiento/amenaza,
     envolver la palabra en un span HTML con fondo de color y texto blanco:
     BAJO   → <span style="background:#27ae60;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">BAJO</span>
     MEDIO  → <span style="background:#f39c12;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">MEDIO</span>
     ALTO   → <span style="background:#e67e22;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">ALTO</span>
     ALERTA → <span style="background:#e67e22;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">ALERTA</span>
     CRISIS → <span style="background:#c0392b;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">CRISIS</span>

R12. COLOR DE SENTIMIENTO: cuando se indique "Sentimiento general", envolver la palabra en span:
     Positivo → <span style="background:#27ae60;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">POSITIVO</span>
     Neutral  → <span style="background:#f39c12;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">NEUTRAL</span>
     Negativo → <span style="background:#c0392b;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">NEGATIVO</span>
     Mixto    → <span style="background:#8e44ad;color:#fff;padding:2px 10px;border-radius:3px;font-weight:bold">MIXTO</span>

R13. REFUERZO ABSOLUTO — CONTENIDO IRRELEVANTE: si un actor en seguimiento publico contenido
     SIN relacion con el cliente, su operacion o entorno de riesgo, la UNICA linea permitida es:
     "[Actor]: actividad registrada sin relacion con el cliente."
     NUNCA desarrollar narrativa, contexto, nivel de amenaza ni detalles de ese contenido.
     Ejemplo de lo que NO se debe hacer: detallar una nota sobre un diputado o recursos publicos
     sin conexion con la operacion minera.

R14. Los encabezados <h2> estan estilizados en el CSS del email (azul rey, texto blanco, ancho
     completo). NO agregar estilos inline adicionales a las etiquetas h2.
"""

DAILY_PROMPT = """Analiza los datos de monitoreo digital del {date} y genera el
INFORME DIARIO de CENTINELA OCCIDENTE para AURA MINERALS.

PERIODO: Ultimas 24 horas ({period_start} al {period_end})

DATOS:
{data}

IMPORTANTE ANTES DE GENERAR:
- En "Nivel de riesgo del dia" y "Nivel de seguimiento", la palabra del nivel va en badge de color (R11).
- En "Sentimiento general", la palabra va en badge de color (R12).
- Los <h2> ya tienen estilo azul rey aplicado por CSS — no agregar estilos inline a h2.
- Si un actor en seguimiento no tiene contenido relacionado con el cliente: UNA sola linea,
  sin contexto adicional: "[Actor]: actividad registrada sin relacion con el cliente."

Genera el informe en HTML limpio con EXACTAMENTE estos 9 numerales, en este orden:

<h2>1. RESUMEN EJECUTIVO</h2>
<ul>
<li><strong>Nivel de riesgo del dia:</strong> [badge-color ALTO/MEDIO/BAJO] — [razon en una oracion]</li>
<li><strong>Narrativa dominante sobre Aura Minerals:</strong> [descripcion]</li>
<li><strong>Hecho mas relevante:</strong> [descripcion]</li>
<li><strong>Actores mas activos:</strong> [lista]</li>
<li><strong>Accion inmediata requerida:</strong> Si / No — [por que]</li>
</ul>

<h2>2. COBERTURA Y SENTIMIENTO — AURA MINERALS</h2>
Analisis de todo lo publicado sobre Aura Minerals / Minosa / Azacualpa.
<ul>
<li><strong>Sentimiento general:</strong> [badge-color POSITIVO/NEUTRAL/NEGATIVO/MIXTO]</li>
<li><strong>Porcentaje estimado:</strong> [X% Positivo / X% Neutral / X% Negativo]</li>
<li><strong>Publicacion mas relevante:</strong> [fuente y contenido]</li>
<li><strong>Narrativa en construccion:</strong> [descripcion]</li>
<li><strong>Temas asociados hoy:</strong> [lista]</li>
</ul>

<h2>3. MEDIOS EN SEGUIMIENTO</h2>
Analisis de: Radio Dignidad, El Referente, Movimiento Amplio, Victor Fernandez,
Criterio HN, Canal 6, Contra Corriente, Radio Progreso, ASONOG.

Para cada actor CON actividad relacionada con el cliente o su entorno de riesgo:
<h3>[Nombre del actor]</h3>
<ul>
<li><strong>Actividad:</strong> [resumen de publicaciones relevantes]</li>
<li><strong>Narrativa:</strong> [mensaje que estan construyendo]</li>
<li><strong>Nivel de seguimiento:</strong> [badge-color ALTO/MEDIO/BAJO]</li>
<li><strong>Alcance estimado:</strong> alto / medio / bajo</li>
</ul>

Si un actor publico solo contenido sin relacion con el cliente, una sola linea:
"[Actor]: actividad registrada sin relacion con el cliente."

Al final, una sola linea consolidada para los completamente inactivos:
<p><em>Sin actividad registrada: [lista separada por coma]</em></p>

<h2>4. MEDIOS DE COMUNICACION TRADICIONALES</h2>
Analisis de HCH, TSI, Tu Nota, Once Noticias, QHubo, La Prensa, La Tribuna,
HRN, Radio America, Radio Cadena Voces.
<ul>
<li><strong>Sentimiento general:</strong> [badge-color POSITIVO/NEUTRAL/NEGATIVO/MIXTO]</li>
<li><strong>Medio mas activo cubriendo el tema:</strong> [nombre y enfoque]</li>
<li><strong>Nota mas destacada:</strong> [medio y titular]</li>
<li><strong>Tono dominante:</strong> [descripcion]</li>
</ul>
Solo incluir medios con cobertura relacionada al cliente o su entorno de riesgo.
Para los que publicaron sin relacion: una sola linea por medio: "[Medio]: actividad registrada sin relacion con el cliente."
Medios completamente inactivos: <p><em>Sin actividad registrada: [lista]</em></p>

<h2>5. MEDIOS LOCALES</h2>
Analisis de Copan TV, Ramon Rojas, Jorge Posadas y medios de La Union, Copan.
<ul>
<li><strong>Actividad registrada:</strong> [resumen o "Sin datos"]</li>
<li><strong>Tono:</strong> [descripcion o "Sin datos"]</li>
<li><strong>Nota mas relevante:</strong> [contenido o "Sin datos"]</li>
</ul>
<p><em>Sin actividad registrada: [lista de medios locales sin actividad]</em></p>

<h2>6. ALERTAS</h2>
Publicaciones con palabras clave de riesgo para la operacion.
IMPORTANTE: el termino "crisis" solo se usa cuando hay amenaza real y directa
contra la operacion. Para menciones de actores opositores, usar "Alerta" o "Bajo el radar".
El titulo de la alerta NUNCA debe ser el nombre de una persona — usar la organizacion
o la narrativa como sujeto.

Para cada alerta:
<h3>[Organizacion o narrativa — nunca un nombre de persona como titulo]</h3>
<ul>
<li><strong>Actor:</strong> [nombre de la organizacion o medio]</li>
<li><strong>Plataforma:</strong> [X / Facebook / RSS]</li>
<li><strong>Palabra clave detectada:</strong> [keyword]</li>
<li><strong>Clasificacion:</strong> Alerta ALTA / Alerta MEDIA / Bajo el radar</li>
<li><strong>Descripcion:</strong> [que se dice y alcance estimado]</li>
<li><strong>Accion sugerida:</strong> [respuesta recomendada y tiempo]</li>
</ul>
Si no hay alertas: <p><em>Sin alertas en las ultimas 24 horas.</em></p>

<h2>7. OPORTUNIDADES DETECTADAS</h2>
Espacios para posicionamiento positivo, correccion de narrativas o comunicacion proactiva.
<ul>
<li><strong>Oportunidad:</strong> [descripcion concreta]</li>
<li><strong>Como aprovecharla:</strong> [accion especifica]</li>
<li><strong>Urgencia:</strong> Inmediata / Esta semana / Este mes</li>
</ul>
Si no hay oportunidades: <p><em>Sin oportunidades destacadas hoy.</em></p>

<h2>8. METRICAS DEL DIA</h2>
<ul>
<li><strong>Total escaneado:</strong> [N posts + N noticias RSS = N total]</li>
<li><strong>Total relevante (relacionado con el cliente):</strong> [N — X% del total]</li>
<li><strong>Descartado (sin relacion con el cliente):</strong> [N — Y% del total]</li>
<li><strong>Publicaciones sobre Aura Minerals:</strong> [numero]</li>
<li><strong>Actor mas activo:</strong> [nombre]</li>
<li><strong>Plataforma mas activa:</strong> [X / Facebook / RSS]</li>
<li><strong>Alertas generadas:</strong> [numero]</li>
</ul>

<h2>9. ACCIONES RECOMENDADAS</h2>
Exactamente 3 acciones priorizadas por urgencia:
<h3>[Titulo Accion 1]</h3>
<ul>
<li><strong>Contexto:</strong> [por que es necesaria ahora]</li>
<li><strong>Accion:</strong> [que hacer exactamente]</li>
<li><strong>Urgencia:</strong> ALTA / MEDIA / BAJA</li>
</ul>
<h3>[Titulo Accion 2]</h3>
<ul>
<li><strong>Contexto:</strong> [...]</li>
<li><strong>Accion:</strong> [...]</li>
<li><strong>Urgencia:</strong> [...]</li>
</ul>
<h3>[Titulo Accion 3]</h3>
<ul>
<li><strong>Contexto:</strong> [...]</li>
<li><strong>Accion:</strong> [...]</li>
<li><strong>Urgencia:</strong> [...]</li>
</ul>

<p style="margin-top:32px;font-size:12px;color:#555;text-align:center;border-top:1px solid #ddd;padding-top:12px">
  Informe generado por CENTINELA OCCIDENTE — Motor de Inteligencia Digital INSERCO.
</p>"""


# ── Análisis con Claude ──────────────────────────────────────────────────────

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
                date=now.strftime("%d de %B de %Y"),
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
    date_str = now.strftime("%d de %B de %Y · %H:%M")

    return f"""<html>
<head>
  <style>
    body  {{ font-family: Arial, sans-serif; max-width: 960px; margin: 0 auto; color: #222; }}
    h2    {{ margin-top: 28px; padding: 10px 16px; border-radius: 5px;
             background: #1a3db5; color: #fff !important;
             font-size: 15px; font-weight: bold; letter-spacing: 0.3px; }}
    h3    {{ color: #1a3db5; margin-top: 18px; font-size: 14px; }}
    table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 14px; }}
    th    {{ background: #1a5e1a; color: #fff; padding: 9px 12px; text-align: left; }}
    td    {{ padding: 8px 12px; border-bottom: 1px solid #eee; vertical-align: top; }}
    tr:nth-child(even) {{ background: #f7f9fc; }}
    a     {{ color: #2980b9; }}
    p     {{ line-height: 1.6; }}
    ul    {{ margin: 6px 0; padding-left: 20px; }}
    li    {{ margin-bottom: 5px; line-height: 1.5; font-size: 14px; }}
    @media print {{
      body::before {{
        content: "CONFIDENCIAL";
        position: fixed; top: 40%; left: 50%;
        transform: translate(-50%, -50%) rotate(-45deg);
        font-size: 80px; font-weight: 900;
        color: rgba(192, 57, 43, 0.07);
        pointer-events: none; z-index: 9999; white-space: nowrap;
      }}
    }}
  </style>
</head>
<body>
  <!-- ENCABEZADO -->
  <div style="background:#1a5e1a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0">
    <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap">
      <div style="flex:1">
        <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
          <h1 style="margin:0;font-size:22px;font-weight:900;letter-spacing:1px">
            CENTINELA OCCIDENTE
          </h1>
          <span style="background:#c0392b;color:#fff;font-size:10px;font-weight:900;
                       letter-spacing:2px;padding:3px 10px;border-radius:3px">
            CONFIDENCIAL
          </span>
        </div>
        <div style="font-size:12px;opacity:.82;margin-top:4px">
          Desarrollado por: <strong>INSERCO</strong> &nbsp;·&nbsp; Cliente: <strong>AURA MINERALS</strong>
        </div>
        <div style="font-size:11px;opacity:.65;margin-top:2px;text-transform:uppercase;letter-spacing:2px">
          Inteligencia Digital · La Union, Copan, Honduras
        </div>
      </div>
    </div>
    <p style="margin:12px 0 0;opacity:.75;font-size:13px;
              border-top:1px solid rgba(255,255,255,.25);padding-top:10px">
      {date_str}
    </p>
  </div>

  <div style="padding:20px;background:#fff;border:1px solid #ddd;
              border-top:none;border-radius:0 0 8px 8px">

    <!-- Bloque de cobertura -->
    <div style="background:#e8f5e9;border-left:4px solid #1a5e1a;
                padding:10px 14px;border-radius:4px;margin-bottom:20px;font-size:13px">
      <strong>Monitoreando:</strong> Aura Minerals · Minosa · Mina Azacualpa · Cerro Los Hornillos<br>
      <strong>Medios en Seguimiento:</strong> Radio Dignidad · El Referente · Movimiento Amplio ·
      Victor Fernandez · Criterio HN · Canal 6 · Contra Corriente · Radio Progreso · ASONOG<br>
      <strong>Medios:</strong> HCH · TSI · Tu Nota · Once Noticias · QHubo · La Prensa ·
      La Tribuna · HRN · Radio America · Cadena Voces · Copan TV · Ramon Rojas · Jorge Posadas
    </div>

    {analysis_html}

    <!-- Linea final de restriccion -->
    <p style="font-size:12px;color:#888;border-top:1px solid #eee;
              padding-top:12px;margin-top:28px;text-align:center">
      Este documento no debe reenviarse ni citarse sin autorizacion de INSERCO.
    </p>
  </div>

  <!-- PIE -->
  <p style="color:#aaa;font-size:11px;text-align:center;margin-top:10px;padding:0 10px">
    CENTINELA OCCIDENTE — Desarrollado por INSERCO · Inteligencia Digital Honduras<br>
    <span style="color:#c0392b;font-weight:bold">CONFIDENCIAL</span> —
    Distribucion limitada a AURA MINERALS y equipo INSERCO autorizado.
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
    log(f"  Reporte guardado: {path}")
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
    log(f"  Email enviado (BCC) a {len(recipients)} destinatario(s)")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    log("=" * 60)
    log("CENTINELA OCCIDENTE — Modulo de entrega iniciado")
    db.init_db()

    now = datetime.now()

    log("Cargando datos de las ultimas 24h...")
    posts = db.get_today_posts()
    news  = db.get_today_news()
    log(f"   {len(posts)} posts · {len(news)} noticias")

    if posts or news:
        log("Analizando con Claude AI...")
        data_summary  = build_data_summary(posts, news)
        analysis_html = analyze_daily(data_summary)

        email_html = build_email_html(analysis_html)
        save_local_report(email_html)

        subject = (
            f"[CONFIDENCIAL] CENTINELA OCCIDENTE — "
            f"{now.strftime('%d/%m/%Y')} · Informe Diario"
        )
        log("Enviando informe...")
        send_email(email_html, subject)
        db.mark_alerts_notified()
    else:
        log("  Sin datos para el informe (collect.py corrio?)")

    log("Entrega completa")
    log("=" * 60)


if __name__ == "__main__":
    main()
