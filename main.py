"""
Hauptprogramm - BFV Scouting-Report-Generator

Orchestriert den gesamten Automatisierungsprozess:
1. BFV-Spielerdaten laden (aus CSV oder per Live-Scraping)
2. Scoring berechnen (4-Kategorien-Modell)
3. PDF-Scouting-Reports generieren
4. E-Mail-Benachrichtigungen versenden (bei Score >= 70)

Verwendung:
    python main.py                    # Standard-Durchlauf mit CSV-Daten
    python main.py --scrape           # Zuerst BFV-Daten live scrapen
    python main.py --top 5            # Top 5 individuelle Reports
    python main.py --send-emails      # E-Mails tatsaechlich senden
    python main.py --liga rl          # Nur Regionalliga analysieren

Fuer Informationssysteme - Automatisierung Use Case:
Option A - Spielerbeobachtung & Scouting-Report-Generator
Datenquelle: www.bfv.de (Bayerischer Fussball-Verband)
"""

import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

# Projektverzeichnis zum Python-Pfad hinzufuegen
sys.path.insert(0, str(Path(__file__).parent))

from config import OUTPUT_DIR, SCORE_THRESHOLD_EMAIL
from data_loader import load_and_process_all_data
from scoring import calculate_scores
from report_generator import generate_single_report, generate_overview_report
from email_notifier import send_batch_alerts
from ai_summary import generate_ai_summary


def setup_logging():
    """Konfiguriert das Logging-System."""
    sys.stdout.reconfigure(encoding="utf-8")

    log_format = "%(asctime)s [%(levelname)s] %(message)s"
    date_format = "%H:%M:%S"

    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(
                OUTPUT_DIR / f"scouting_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                encoding="utf-8",
            ),
        ],
    )


def parse_arguments():
    """Kommandozeilenargumente parsen."""
    parser = argparse.ArgumentParser(
        description="BFV Scouting-Report-Generator - Automatisierte Spieleranalyse",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  python main.py                    Standardanalyse mit CSV-Daten
  python main.py --scrape           Zuerst live von BFV scrapen
  python main.py --top 5            Top 5 Reports generieren
  python main.py --send-emails      E-Mails wirklich senden
  python main.py --liga rl          Nur Regionalliga
        """,
    )
    parser.add_argument(
        "--top", type=int, default=5,
        help="Anzahl der Top-Spieler fuer individuelle Reports (Standard: 5)",
    )
    parser.add_argument(
        "--send-emails", action="store_true",
        help="E-Mails tatsaechlich senden (Standard: Simulation)",
    )
    parser.add_argument(
        "--scrape", action="store_true",
        help="BFV-Daten live von www.bfv.de scrapen",
    )
    parser.add_argument(
        "--liga", type=str, default=None,
        help="Nur bestimmte Liga analysieren (rl/bln/bls/ll)",
    )
    parser.add_argument(
        "--min-score", type=float, default=None,
        help="Minimaler Score fuer Report-Generierung",
    )
    parser.add_argument(
        "--csv", type=str, default=None,
        help="Pfad zu einer bestimmten CSV-Datei",
    )
    return parser.parse_args()


def print_banner():
    """Zeigt das Programm-Banner an."""
    banner = """
================================================================
                                                                
    BFV SCOUTING-REPORT-GENERATOR                              
                                                                
    Automatisierte Spielerbeobachtung & Analyse                 
    Datenquelle: www.bfv.de                                     
    Informationssysteme - Automatisierungs-Use-Case             
                                                                
    Option A: Spielerbeobachtung & Scouting-Report-Generator    
                                                                
================================================================
    """
    print(banner)


def run_scraper(liga_filter=None):
    """
    Fuehrt den BFV-Scraper aus und gibt den Pfad zur CSV zurueck.

    Args:
        liga_filter: Optional - bestimmte Liga scrapen

    Returns:
        Pfad zur erzeugten CSV-Datei oder None bei Fehler
    """
    try:
        from bfv_scraper import scrape_all_leagues, save_to_csv
        from config import DATA_DIR

        logger = logging.getLogger(__name__)
        logger.info("Starte BFV Live-Scraping...")

        leagues = None
        if liga_filter:
            liga_map = {
                "rl": ["regionalliga"],
                "bln": ["bayernliga_nord"],
                "bls": ["bayernliga_sued"],
                "bl": ["bayernliga_nord", "bayernliga_sued"],
                "ll": ["landesliga_mitte", "landesliga_nordost"],
            }
            leagues = liga_map.get(liga_filter, [liga_filter])

        players = scrape_all_leagues(leagues=leagues, headless=True, max_per_league=20)

        if players:
            csv_path = DATA_DIR / f"bfv_scraped_{datetime.now().strftime('%Y%m%d')}.csv"
            save_to_csv(players, str(csv_path))
            return str(csv_path)
        else:
            logger.warning("Scraping hat keine Daten geliefert. Nutze CSV-Fallback.")
            return None

    except ImportError:
        logger.warning("Selenium nicht installiert. Nutze vorhandene CSV-Daten.")
        logger.info("Installiere mit: pip install selenium")
        return None
    except Exception as e:
        logger.error(f"Scraping-Fehler: {e}")
        return None


def main():
    """Hauptfunktion - Orchestriert den gesamten Prozess."""
    # Ausgabeverzeichnis sicherstellen
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Setup
    setup_logging()
    logger = logging.getLogger(__name__)
    args = parse_arguments()

    print_banner()

    start_time = datetime.now()
    logger.info(f"Gestartet: {start_time.strftime('%d.%m.%Y %H:%M:%S')}")

    # ============================================================
    # SCHRITT 0: OPTIONAL - LIVE SCRAPING
    # ============================================================
    csv_path = args.csv  # Benutzer-definierter CSV-Pfad

    if args.scrape:
        logger.info("\n[SCHRITT 0] BFV Live-Scraping")
        scraped_path = run_scraper(liga_filter=args.liga)
        if scraped_path:
            csv_path = scraped_path

    # ============================================================
    # SCHRITT 1: DATEN LADEN UND VERARBEITEN
    # ============================================================
    logger.info("\n[SCHRITT 1] Daten laden und verarbeiten")
    df = load_and_process_all_data(csv_path=csv_path)

    if df.empty:
        logger.error("Keine Daten geladen! Pruefe die Datenquellen.")
        logger.info("Tipp: Stelle sicher dass data/bfv_spieler.csv existiert")
        sys.exit(1)

    # Liga-Filter aus CLI
    if args.liga and not args.scrape:
        liga_map = {
            "rl": "Regionalliga Bayern",
            "bln": "Bayernliga Nord",
            "bls": "Bayernliga Sued",
        }
        liga_name = liga_map.get(args.liga, args.liga)
        df = df[df["liga"] == liga_name]
        logger.info(f"  -> Gefiltert auf Liga: {liga_name} ({len(df)} Spieler)")

    # ============================================================
    # SCHRITT 2: SCORING BERECHNEN
    # ============================================================
    logger.info("\n[SCHRITT 2] Scoring berechnen")
    df_scored = calculate_scores(df)

    # Optionaler Score-Filter
    if args.min_score:
        df_scored = df_scored[df_scored["total_score"] >= args.min_score]
        logger.info(f"  -> Gefiltert auf Score >= {args.min_score} ({len(df_scored)} Spieler)")

    # ============================================================
    # SCHRITT 3: KI-FAZIT GENERIEREN (einmalig pro Spieler)
    # ============================================================
    top_n = min(args.top, len(df_scored))
    logger.info(f"\n[SCHRITT 3] KI-Fazit generieren (Gemini) fuer Top {top_n} Spieler")

    ai_fazits = {}
    for i in range(top_n):
        player = df_scored.iloc[i]
        player_name = player["name"]
        logger.info(f"  Generiere KI-Fazit fuer {player_name}...")
        ai_fazits[player_name] = generate_ai_summary(player)

    # ============================================================
    # SCHRITT 4: PDF-REPORTS GENERIEREN
    # ============================================================
    logger.info("\n[SCHRITT 4] PDF-Reports generieren")

    # Uebersichts-Report
    overview_path = generate_overview_report(df_scored)
    logger.info(f"  [OK] Uebersichts-Report: {overview_path}")

    # Individuelle Reports fuer Top-Spieler
    report_paths = {}

    logger.info(f"\n  Generiere individuelle Reports fuer Top {top_n} Spieler...")
    for i in range(top_n):
        player = df_scored.iloc[i]
        player_name = player["name"]

        report_path = generate_single_report(player, df_scored, i + 1, ai_fazit=ai_fazits.get(player_name, ""))
        report_paths[player_name] = report_path
        logger.info(f"  [OK] #{i+1} {player_name}: {Path(report_path).name}")

    # ============================================================
    # SCHRITT 5: E-MAIL-BENACHRICHTIGUNGEN
    # ============================================================
    logger.info("\n[SCHRITT 5] E-Mail-Benachrichtigungen")

    simulate = not args.send_emails
    if simulate:
        logger.info("  Info: Simulationsmodus aktiv (--send-emails fuer echten Versand)")

    email_results = send_batch_alerts(
        df_scored,
        report_paths,
        simulate=simulate,
        ai_fazits=ai_fazits,
    )

    # ============================================================
    # ZUSAMMENFASSUNG
    # ============================================================
    elapsed = (datetime.now() - start_time).total_seconds()

    logger.info("\n" + "=" * 60)
    logger.info("ZUSAMMENFASSUNG")
    logger.info("=" * 60)
    logger.info(f"  Verarbeitete Spieler:    {len(df_scored)}")
    logger.info(f"  Ligen:                   {df_scored['liga'].nunique()}")
    logger.info(f"  Generierte Reports:      {len(report_paths) + 1} (inkl. Uebersicht)")
    logger.info(f"  KI-Fazits generiert:     {sum(1 for v in ai_fazits.values() if v)} von {len(ai_fazits)}")
    logger.info(f"  E-Mail-Alerts:           {sum(email_results.values())} von {len(email_results)}")
    logger.info(f"  Score-Schwellenwert:     {SCORE_THRESHOLD_EMAIL}/100")
    logger.info(f"  Datenquelle:             www.bfv.de")
    logger.info(f"  Ausgabeverzeichnis:      {OUTPUT_DIR}")
    logger.info(f"  Laufzeit:                {elapsed:.1f} Sekunden")

    # Score-Verteilung
    above_70 = len(df_scored[df_scored["total_score"] >= 70])
    logger.info(f"\n  Spieler mit Score >= 70: {above_70} ({above_70/len(df_scored)*100:.1f}%)")

    # Top-Spieler nochmal anzeigen
    logger.info(f"\n  TOP {top_n} SPIELER:")
    for i in range(top_n):
        player = df_scored.iloc[i]
        alert = "[Mail]" if player["name"] in email_results and email_results[player["name"]] else "      "
        logger.info(
            f"  {alert} #{i+1:2d} | {player['name']:<25s} | "
            f"{player['verein']:<22s} | "
            f"Score: {player['total_score']:5.1f} | {player['rating']}"
        )

    logger.info(f"\n{'=' * 60}")
    logger.info("Scouting-Analyse abgeschlossen!")
    logger.info(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
