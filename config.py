"""
Konfigurationsdatei fuer den Scouting-Report-Generator.

Enthaelt alle einstellbaren Parameter fuer:
- Dateipfade und Datenquellen
- BFV Liga-Konfiguration und Scraping-Parameter
- Scoring-Gewichtungen und Schwellenwerte (BFV-Modell)
- E-Mail-Konfiguration
- PDF-Report-Einstellungen

Version 2.0: Umgestellt auf echte BFV-Daten (www.bfv.de)
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ============================================================
# PROJEKTPFADE
# ============================================================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = BASE_DIR / "output"

# ============================================================
# BFV LIGA-KONFIGURATION
# ============================================================
# Wettbewerbs-IDs von www.bfv.de (Saison 2025/2026)
BFV_LEAGUES = {
    "regionalliga": {
        "name": "Regionalliga Bayern",
        "comp_id": "02T7P80AI800000DVS5489BTVSDFH806-G",
        "liga_faktor": 1.0,     # Hoechste bayerische Spielklasse
    },
    "bayernliga_nord": {
        "name": "Bayernliga Nord",
        "comp_id": "02T7P82NM0000004VS5489BTVSDFH806-G",
        "liga_faktor": 0.92,
    },
    "bayernliga_sued": {
        "name": "Bayernliga Sued",
        "comp_id": "02T7P82P8S000055VS5489BTVSDFH806-G",
        "liga_faktor": 0.92,
    },
    "landesliga_mitte": {
        "name": "Landesliga Mitte",
        "comp_id": "02T7P85B3K000008VS5489BTVSDFH806-G",
        "liga_faktor": 0.85,
    },
    "landesliga_nordost": {
        "name": "Landesliga Nordost",
        "comp_id": "02T7P85BRG000000VS5489BTVSDFH806-G",
        "liga_faktor": 0.85,
    },
    "landesliga_nordwest": {
        "name": "Landesliga Nordwest",
        "comp_id": "02T7P85D70000056VS5489BTVSDFH806-G",
        "liga_faktor": 0.85,
    },
    "landesliga_suedost": {
        "name": "Landesliga Suedost",
        "comp_id": "02T7P85ADC000000VS5489BTVSDFH806-G",
        "liga_faktor": 0.85,
    },
    "landesliga_suedwest": {
        "name": "Landesliga Suedwest",
        "comp_id": "02T7P85E1C000005VS5489BTVSDFH806-G",
        "liga_faktor": 0.85,
    },
}

# Pfad zur vorhandenen/gescrapten BFV-Datendatei
BFV_DATA_PATH = DATA_DIR / "bfv_spieler.csv"

# URL-Templates fuer BFV-Scraping
BFV_BASE_URL = "https://www.bfv.de"
BFV_TORJAEGER_URL = BFV_BASE_URL + "/ergebnisse/wettbewerb/-/{comp_id}/torjaeger"
BFV_PLAYER_URL = BFV_BASE_URL + "/spieler/-/{player_id}"

# ============================================================
# SCORING-KONFIGURATION (BFV-Modell)
# ============================================================
# Kalibriert so, dass ein Score > 70 SCHWER zu erreichen ist.
#
# Ein Spieler muss in ALLEN 4 Kategorien ueberdurchschnittlich
# abschneiden, um ueber 70 zu kommen:
# - Hohe Torquote (>0.5 Tore/Spiel)
# - Viele Einsatzminuten (>80 Min/Spiel)
# - Viele Spiele absolviert (>25)
# - Wenige Karten (max 2-3 Gelbe)

# Gewichtung der Scoring-Kategorien (Summe = 1.0)
BFV_SCORING_WEIGHTS = {
    "alter": 0.10,                # Youngstar-Faktor
    "einsatzzeit": 0.25,          # Minuten pro Spiel
    "scorerquote": 0.40,          # Tore + Assists pro Spiel (TM.de)
    "spielpraxis": 0.15,          # Anzahl absolvierter Spiele
    "disziplin": 0.10,            # Karten-Disziplin
}

# Benchmarks fuer maximalen Score (100 Punkte)
# Diese Werte sind ABSICHTLICH hoch gesetzt, damit 70+ schwer ist
SCORING_BENCHMARKS = {
    "tore_pro_spiel_max": 1.0,    # 1.0 Tore/Spiel = Score 100 (quasi unmoeglich)
    "minuten_pro_spiel_max": 90,  # 90 Min/Spiel = Score 100 (Stammspieler)
    "spiele_optimal": 30,         # 30 Spiele = Score 100 (absolute Vollzeit)
    "spiele_sigmoid_k": 0.20,     # Steilheit der Sigmoid-Kurve (flacher = schwerer)
    "karten_gelb_strafe": 8,      # -8 Punkte pro Gelbe Karte
    "karten_rot_strafe": 35,      # -35 Punkte pro Rote Karte
    "karten_basis": 100,          # Startpunktzahl Disziplin
    "score_dampening": 0.92,      # Globaler Daempfungsfaktor (senkt alle Scores massiv)
    "alter_optimal": 19,          # Optimales Alter fuer 100 Punkte
    "alter_fallback": 25,         # Fallback-Alter, wenn nicht bekannt
}

# Liga-Faktor: Multiplikator fuer den Gesamtscore
# Hoehere Ligen = hoeherer Faktor
# (Bereits in BFV_LEAGUES definiert, hier nochmal als Referenz)
LIGA_FAKTOREN = {
    "Regionalliga Bayern": 1.00,
    "Bayernliga Nord": 0.92,
    "Bayernliga Sued": 0.92,
    "Landesliga Mitte": 0.85,
    "Landesliga Nordost": 0.85,
    "Landesliga Nordwest": 0.85,
    "Landesliga Suedost": 0.85,
    "Landesliga Suedwest": 0.85,
}

# Schwellenwerte
SCORE_THRESHOLD_EMAIL = 60     # Ab diesem Score -> E-Mail an Trainerteam
SCORE_THRESHOLD_EXCELLENT = 75  # Herausragend (SEHR selten!)
SCORE_THRESHOLD_GOOD = 60       # Gut
SCORE_THRESHOLD_AVERAGE = 45    # Durchschnittlich

# ============================================================
# E-MAIL-KONFIGURATION
# ============================================================
EMAIL_CONFIG = {
    "smtp_server": "smtp.sendgrid.net",
    "smtp_port": 587,
    "use_tls": True,
    "smtp_username": "apikey",
    "sender_email": os.environ.get("SENDGRID_FROM_EMAIL", "luca.schreiner@hm.edu"),
    "sender_password": os.environ.get("SENDGRID_API_KEY", ""),
    "recipients": [
        "linus.eilers@hm.edu",
        "informationssystemetest@gmail.com",
    ],
    "subject_template": "Scouting-Alert: {player_name} (Score: {score}/100)",
}

# ============================================================
# PDF-REPORT-EINSTELLUNGEN
# ============================================================
REPORT_CONFIG = {
    "title": "BFV Scouting Report",
    "club_name": "Scouting-Abteilung Bayern",
    "season": "2025/2026",
    "author": "Automatisierte Scouting-Analyse",
    "data_source": "www.bfv.de",
    # Farben (RGB 0-255)
    "primary_color": (0, 73, 144),        # BFV Blau
    "secondary_color": (44, 62, 80),      # Dunkelblau/Anthrazit
    "accent_color": (231, 76, 60),        # Rot (Hervorhebungen)
    "success_color": (39, 174, 96),       # Gruen (Positive Werte)
    "warning_color": (243, 156, 18),      # Orange (Warnungen)
    "text_color": (52, 73, 94),           # Textfarbe
    "light_bg": (236, 240, 241),          # Heller Hintergrund
}

# Filterkriterien fuer die Spielersuche (optional)
SEARCH_CRITERIA = {
    "min_spiele": 10,          # Mindestanzahl Spiele fuer Score-Berechnung
    "ligen": None,             # z.B. ["Regionalliga Bayern"] oder None fuer alle
}
