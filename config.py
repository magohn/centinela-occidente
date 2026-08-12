"""
CENTINELA OCCIDENTE — Configuración Central
Sistema de monitoreo digital para AURA MINERALS
Cliente: INSERCO / AURA MINERALS
"""

import os

# ── Sujeto Principal: AURA MINERALS ─────────────────────────────────────────

AURA_ACCOUNTS = {
    "Aura Minerals": {
        "twitter":   "AuraMineralsNA",
        "facebook":  "mineralesdeoccidentesa",
        "facebook2": "auramineracao360",
        "categoria": "CLIENTE",
    }
}

AURA_VARIANTES = [
    "Aura Minerals", "Aura", "Minosa", "La mina", "La Bufa",
    "Cerro los Hornillos", "Los Hornillos", "Los Herbederos",
    "Hervederos", "Mina San Andres", "Mina Azacualpa",
    "Cementerio Azacualpa", "Minerales de Occidente",
]

# ── Actores Opositores ───────────────────────────────────────────────────────

OPPOSITION_ACTORS = {
    "Radio Dignidad": {
        "twitter":   None,
        "facebook":  "profile.php?id=61567476033483",
        "categoria": "OPOSITOR",
    },
    "El Referente": {
        "twitter":   "ElReferentehn",
        "facebook":  "ElReferenteHn",
        "categoria": "OPOSITOR",
    },
    "Movimiento Amplio": {
        "twitter":   "MovAmplioHN",
        "facebook":  "MovAmplioHn",
        "tiktok":    "@movimientoamplio",
        "categoria": "OPOSITOR",
    },
    "Victor Fernandez": {
        "twitter":   "VictorFerG",
        "facebook":  "victor.fernandez.10485546",
        "categoria": "OPOSITOR",
    },
    "Criterio HN": {
        "twitter":   "criteriohn",
        "facebook":  None,
        "categoria": "OPOSITOR",
    },
    "Canal 6 Honduras": {
        "twitter":   "Canal6Honduras",
        "facebook":  None,
        "categoria": "OPOSITOR",
    },
    "Contra Corriente": {
        "twitter":   "ContraC_HN",
        "facebook":  None,
        "categoria": "OPOSITOR",
    },
    "Radio Progreso": {
        "twitter":   "RadioProgresoHN",
        "facebook":  "RadioProgresoPaginaOficial",
        "categoria": "OPOSITOR",
    },
    "ASONOG": {
        "twitter":   "AsonogOficial",
        "facebook":  "ASONOG",
        "categoria": "OPOSITOR",
    },
}

# ── Medios de Comunicación Tradicionales ────────────────────────────────────

TRADITIONAL_MEDIA = {
    "HCH Televisión":     {"twitter": "HCHTelevDigital",  "rss": "https://hch.tv/feed/"},
    "TSI Honduras":       {"twitter": "TSIHonduras",       "rss": None},
    "Tu Nota":            {"twitter": "tunota_com",        "rss": None},
    "Once Noticias":      {"twitter": "11_Noticias",       "rss": None},
    "QHubo":              {"twitter": "Qhubotvoficial",    "rss": None},
    "La Prensa":          {"twitter": "DiarioLaPrensa",    "rss": "https://www.laprensa.hn/feed/"},
    "La Tribuna":         {"twitter": "LaTribunahn",       "rss": "https://www.latribuna.hn/feed/"},
    "HRN":                {"twitter": "radiohrn",          "rss": "https://www.radiohrn.hn/feed/"},
    "Radio América":      {"twitter": "radioamericahn",    "rss": None},
    "Radio Cadena Voces": {"twitter": "RCVHonduras",       "rss": None},
}

# ── Medios Locales ───────────────────────────────────────────────────────────

LOCAL_MEDIA = {
    "Copan TV":     {"facebook": "copantv30",              "twitter": None},
    "Ramon Rojas":  {"facebook": "resumenenlinea2019jjz",  "twitter": None},
    "Jorge Posadas":{"facebook": "jorge.posadas.92102",    "twitter": None},
}

# ── Instancias Nitter ────────────────────────────────────────────────────────

NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.it",
    "https://nitter.nl",
    "https://nitter.1d4.us",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]

# ── Palabras clave críticas ──────────────────────────────────────────────────

CRISIS_KEYWORDS = [
    # Impacto ambiental
    "derrames", "contaminación", "contaminacion", "ríos contaminados",
    "rios contaminados", "suelos contaminados", "fuentes de agua",
    "bosques arrasados", "mina a cielo abierto",
    # Conflicto social
    "protestas", "represión", "represion", "agresión", "agresion",
    "expropiación", "expropiacion", "explotación", "explotacion",
    "licencias ambientales", "pueblos indígenas", "maya", "chortí", "chorti",
    # Variantes del proyecto
    "Minosa", "La Bufa", "Cerro los Hornillos", "Mina Azacualpa",
    "Cementerio Azacualpa", "Mina San Andres", "Hervederos",
]

# ── Palabras clave de monitoreo general ─────────────────────────────────────

MONITOR_KEYWORDS = [
    "Aura Minerals", "Aura", "Minosa", "La mina", "La Bufa",
    "Cerro los Hornillos", "Los Hornillos", "Los Herbederos",
    "Hervederos", "Mina San Andres", "Mina Azacualpa",
    "Cementerio Azacualpa", "Minerales de Occidente",
    "La Unión Copán", "La Union Copan", "Azacualpa", "San Andrés Copán",
]

# ── Rutas y configuración general ───────────────────────────────────────────

_GHA       = os.environ.get("GITHUB_ACTIONS") == "true"
_WORKSPACE = os.environ.get("GITHUB_WORKSPACE", "")

if _GHA:
    BASE_DIR    = _WORKSPACE
    REPORTS_DIR = os.path.join(_WORKSPACE, "reportes_occidente")
    DB_PATH     = os.path.join(_WORKSPACE, "occidente.db")
    ENV_PATH    = os.path.join(_WORKSPACE, ".env")
    LOG_PATH    = os.path.join(_WORKSPACE, "occidente.log")
else:
    BASE_DIR    = os.path.expanduser("~/social_monitor/occidente_agent")
    REPORTS_DIR = os.path.expanduser("~/social_monitor/reportes_occidente")
    DB_PATH     = os.path.join(BASE_DIR, "occidente.db")
    ENV_PATH    = os.path.expanduser("~/social_monitor/.env")
    LOG_PATH    = os.path.join(BASE_DIR, "occidente.log")

REPORT_RECIPIENTS = [
    "maxgonzales1981@gmail.com",
]
REPORT_BCC = []
SENDER_NAME       = "🗺️ CENTINELA OCCIDENTE"

MAX_TWEETS_PER_PROFILE = 15
MAX_RSS_ITEMS          = 20
