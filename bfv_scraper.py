"""
BFV Web-Scraper - Automatisierte Datenextraktion von www.bfv.de

Scrapt Spielerstatistiken (Torjaeger-Listen) aus verschiedenen
bayerischen Fussball-Ligen direkt von der BFV-Website.

Features:
- Selenium-basiertes Scraping (JavaScript-Rendering)
- Konfigurierbare Ligen (Regionalliga, Bayernliga, Landesliga, Bezirksliga)
- Automatische CSV-Export der gesammelten Daten
- Rate-Limiting zum Schutz der BFV-Server
- Fallback auf vorhandene CSV-Daten wenn Scraping fehlschlaegt

Hinweis: Die BFV-Website nutzt dynamisches JavaScript-Rendering,
daher ist ein Browser-Treiber (Chrome/Firefox) erforderlich.

Verwendung:
    python bfv_scraper.py              # Alle konfigurierten Ligen scrapen
    python bfv_scraper.py --liga rl    # Nur Regionalliga
    python bfv_scraper.py --headless   # Ohne Browser-Fenster
"""

import csv
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

# BFV Liga-Konfiguration mit IDs und Multiplikatoren
BFV_LEAGUES = {
    "regionalliga": {
        "name": "Regionalliga Bayern",
        "comp_id": "02T7P80AI800000DVS5489BTVSDFH806-G",
        "liga_faktor": 1.0,   # Hoechste Spielklasse = voller Faktor
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
        "comp_id": "nordwest",
        "liga_faktor": 0.85,
    },
    "landesliga_suedwest": {
        "name": "Landesliga Südwest",
        "comp_id": "suedwest",
        "liga_faktor": 0.85,
    },
    "landesliga_suedost": {
        "name": "Landesliga Südost",
        "comp_id": "suedost",
        "liga_faktor": 0.85,
    },
}

BFV_BASE_URL = "https://www.bfv.de"
TORJAEGER_URL = BFV_BASE_URL + "/ergebnisse/wettbewerb/-/{comp_id}/torjaeger"
PLAYER_URL = BFV_BASE_URL + "/spieler/-/{player_id}"


def scrape_torjaeger_list(driver, comp_id, liga_name, max_players=20):
    """
    Scrapt die Torjaegerliste einer Liga von der BFV-Website.

    Args:
        driver: Selenium WebDriver Instanz
        comp_id: BFV Wettbewerbs-ID
        liga_name: Name der Liga (fuer Logging)
        max_players: Maximale Anzahl Spieler zum Scrapen

    Returns:
        Liste von Dictionaries mit Spielerdaten
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    url = TORJAEGER_URL.format(comp_id=comp_id)
    logger.info(f"Scrape Torjaeger: {liga_name} -> {url}")

    driver.get(url)
    time.sleep(5)  # Warten auf JavaScript-Rendering

    players = []

    try:
        # "MEHR" Button klicken um genug Spieler zu laden (ca. 20 pro Klick)
        clicks_needed = (max_players // 20) + 1
        for _ in range(clicks_needed):
            try:
                mehr_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'MEHR') or contains(text(), 'Mehr')]")
                driver.execute_script("arguments[0].click();", mehr_btn)
                time.sleep(2.5)
            except Exception:
                break  # Button nicht mehr da oder verdeckt

        # Torjaeger-Eintraege finden
        entries = driver.find_elements(By.CSS_SELECTOR, ".bfv-torjaeger-entry, .scorer-entry, [class*='torjaeger']")

        if not entries:
            # Fallback: Versuche andere Selektoren
            entries = driver.find_elements(By.CSS_SELECTOR, ".ranking-list-item, .list-item")

        for i, entry in enumerate(entries[:max_players]):
            try:
                # Spielername und Verein extrahieren
                name_el = entry.find_element(By.CSS_SELECTOR, ".player-name, .name, a[href*='spieler']")
                name = name_el.text.strip()

                team_el = entry.find_element(By.CSS_SELECTOR, ".team-name, .club, .verein")
                team = team_el.text.strip()

                # Tore extrahieren
                goals_el = entry.find_element(By.CSS_SELECTOR, ".goals, .tore, .count")
                goals = int(goals_el.text.strip())

                # Spieler-Profil-Link
                link_el = entry.find_element(By.CSS_SELECTOR, "a[href*='spieler']")
                profile_url = link_el.get_attribute("href")
                player_id = profile_url.split("/")[-1] if profile_url else ""

                players.append({
                    "name": name,
                    "verein": team,
                    "tore": goals,
                    "player_id": player_id,
                    "profile_url": profile_url,
                    "rang": i + 1,
                })
            except Exception as e:
                logger.debug(f"Konnte Eintrag {i+1} nicht parsen: {e}")
                continue

        logger.info(f"  -> {len(players)} Spieler gefunden in {liga_name}")

    except Exception as e:
        logger.error(f"Fehler beim Scrapen von {liga_name}: {e}")

    return players


def scrape_player_details(driver, player_id, player_name):
    """
    Scrapt detaillierte Leistungsdaten eines Spielers von seinem Profil.
    Zudem wird versucht, das Alter (oder Geburtsdatum) zu extrahieren.

    Extrahiert aus der "Leistungsdaten"-Tabelle:
    - Anzahl Spiele
    - Tore
    - Gelbe Karten
    - Rote Karten
    - Einsatzminuten

    Args:
        driver: Selenium WebDriver
        player_id: BFV Spieler-ID
        player_name: Name (fuer Logging)

    Returns:
        Dictionary mit Spieler-Detaildaten
    """
    from selenium.webdriver.common.by import By

    url = PLAYER_URL.format(player_id=player_id)
    logger.info(f"  Scrape Details: {player_name}")

    driver.get(url)
    time.sleep(3)

    details = {
        "spiele": 0,
        "tore": 0,
        "gelbe_karten": 0,
        "rote_karten": 0,
        "minuten": 0,
        "alter": None,
    }

    try:
        # Leistungsdaten-Tabelle finden
        rows = driver.find_elements(By.CSS_SELECTOR, ".performance-row, .leistungsdaten-row, tr[class*='match']")

        for row in rows:
            cols = row.find_elements(By.TAG_NAME, "td")
            if len(cols) >= 7:
                details["spiele"] += 1
                try:
                    details["tore"] += int(cols[3].text.strip() or 0)
                except (ValueError, IndexError):
                    pass
                try:
                    gelb_text = cols[4].text.strip()
                    if gelb_text:
                        details["gelbe_karten"] += 1
                except (ValueError, IndexError):
                    pass
                try:
                    rot_text = cols[5].text.strip()
                    if rot_text:
                        details["rote_karten"] += 1
                except (ValueError, IndexError):
                    pass
                try:
                    min_text = cols[6].text.strip().replace("'", "")
                    if min_text:
                        details["minuten"] += int(min_text)
                except (ValueError, IndexError):
                    pass

        # Versuch das Alter aus dem Seitentext zu parsen
        import re
        from datetime import datetime
        page_text = driver.find_element(By.TAG_NAME, "body").text
        
        # 1. Nach Alter direkt suchen
        age_match = re.search(r'Alter:?\s*(\d{2})', page_text, re.IGNORECASE)
        if age_match:
            details["alter"] = int(age_match.group(1))
        else:
            # 2. Nach Geburtsjahr suchen (z.B. 15.05.2003)
            dob_match = re.search(r'Geburtsdatum:?\s*\d{2}\.\d{2}\.(\d{4})', page_text, re.IGNORECASE)
            if dob_match:
                birth_year = int(dob_match.group(1))
                current_year = datetime.now().year
                details["alter"] = current_year - birth_year

    except Exception as e:
        logger.warning(f"Konnte Details fuer {player_name} nicht laden: {e}")

    return details


def create_selenium_driver(headless=True):
    """
    Erstellt einen Selenium WebDriver mit Chrome.

    Args:
        headless: Wenn True, laeuft Chrome ohne sichtbares Fenster

    Returns:
        WebDriver Instanz
    """
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service

    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

    try:
        driver = webdriver.Chrome(options=options)
        logger.info("Chrome WebDriver erfolgreich gestartet")
        return driver
    except Exception as e:
        logger.error(f"Chrome WebDriver konnte nicht gestartet werden: {e}")
        logger.info("Tipp: Installiere ChromeDriver oder nutze die vorhandenen CSV-Daten")
        return None


def scrape_all_leagues(leagues=None, headless=True, max_per_league=20):
    """
    Scrapt Spielerdaten aus allen konfigurierten BFV-Ligen.

    Args:
        leagues: Liste der Liga-Keys (None = alle)
        headless: Chrome ohne Fenster
        max_per_league: Max. Spieler pro Liga

    Returns:
        Liste aller Spielerdaten als Dictionaries
    """
    if leagues is None:
        leagues = list(BFV_LEAGUES.keys())

    driver = create_selenium_driver(headless=headless)
    if driver is None:
        logger.error("Kein WebDriver verfuegbar. Nutze die CSV-Fallback-Daten.")
        return []

    all_players = []

    try:
        for liga_key in leagues:
            if liga_key not in BFV_LEAGUES:
                logger.warning(f"Unbekannte Liga: {liga_key}")
                continue

            liga = BFV_LEAGUES[liga_key]
            players = scrape_torjaeger_list(
                driver, liga["comp_id"], liga["name"], max_per_league
            )

            # Spieler-Details scrapen (Rate Limiting)
            for player in players:
                if player.get("player_id"):
                    details = scrape_player_details(
                        driver, player["player_id"], player["name"]
                    )
                    list_tore = player.get("tore", 0)
                    player.update(details)
                    if player.get("tore", 0) == 0 and list_tore > 0:
                        player["tore"] = list_tore
                    time.sleep(1)  # Rate Limiting: 1 Sekunde zwischen Anfragen

                # Liga-Informationen hinzufuegen
                player["liga"] = liga["name"]
                player["liga_key"] = liga_key
                player["liga_faktor"] = liga["liga_faktor"]

            all_players.extend(players)
            logger.info(f"Liga {liga['name']}: {len(players)} Spieler verarbeitet")

    finally:
        driver.quit()
        logger.info("WebDriver geschlossen")

    return all_players


def save_to_csv(players, output_path):
    """
    Speichert die Spielerdaten als CSV.

    Args:
        players: Liste von Spieler-Dictionaries
        output_path: Pfad zur CSV-Datei
    """
    if not players:
        logger.warning("Keine Spielerdaten zum Speichern")
        return

    fieldnames = [
        "name", "verein", "liga", "liga_faktor",
        "spiele", "tore", "gelbe_karten", "rote_karten", "minuten", "alter"
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(players)

    logger.info(f"CSV gespeichert: {output_path} ({len(players)} Spieler)")


def main():
    """Hauptfunktion fuer standalone Scraping."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    parser = argparse.ArgumentParser(description="BFV Torjaeger-Scraper")
    parser.add_argument("--liga", nargs="+", default=None,
                       help="Ligen zum Scrapen (z.B. regionalliga bayernliga_nord)")
    parser.add_argument("--headless", action="store_true", default=True,
                       help="Chrome ohne Fenster")
    parser.add_argument("--max", type=int, default=100,
                       help="Max. Spieler pro Liga")
    parser.add_argument("--output", type=str, default=None,
                       help="Ausgabe-CSV-Pfad")
    args = parser.parse_args()

    output_path = args.output or str(
        Path(__file__).parent / "data" / f"bfv_scraped_{datetime.now().strftime('%Y%m%d')}.csv"
    )

    logger.info("=== BFV Torjaeger-Scraper gestartet ===")
    players = scrape_all_leagues(
        leagues=args.liga,
        headless=args.headless,
        max_per_league=args.max,
    )

    if players:
        save_to_csv(players, output_path)
        try:
            from database import save_players_to_db
            save_players_to_db(players)
            logger.info(f"Fertig! {len(players)} Spieler in CSV und lokaler SQLite Datenbank gespeichert")
        except Exception as e:
            logger.error(f"Fehler beim Speichern in die Datenbank: {e}")
    else:
        logger.warning("Keine Spieler gescrapt. Pruefe die Verbindung und den WebDriver.")


if __name__ == "__main__":
    main()
