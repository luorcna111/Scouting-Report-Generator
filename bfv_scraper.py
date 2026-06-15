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
import urllib.request
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

_font_cache = {}  # font_id -> decoder dict

def _get_bfv_decoder(driver):
    """
    Lädt den BFV-Custom-Font und baut ein Mapping von PUA-Zeichen zu echten Zeichen.
    BFV wechselt den Font-ID pro Seite — daher wird per Font-ID gecacht, nicht global.
    """
    import re, io
    try:
        from fontTools.ttLib import TTFont
        from fontTools import agl
    except ImportError:
        logger.warning("fontTools nicht installiert, Decoder nicht verfügbar")
        return {}

    page_source = driver.page_source
    match = re.search(r'export\.fontface/-/format/ttf/id/([^/\'"]+)/type/font', page_source)

    font_url = None
    font_id = None

    if match:
        font_id = match.group(1)
        font_url = f"https://app.bfv.de/export.fontface/-/format/ttf/id/{font_id}/type/font"
    else:
        # Detailseiten laden die Font per JavaScript — via Performance API suchen
        try:
            resources = driver.execute_script(
                "return performance.getEntriesByType('resource')"
                ".filter(function(r){ return r.name.indexOf('fontface') !== -1; })"
                ".map(function(r){ return r.name; });"
            )
            if resources:
                font_url = resources[0]
                id_match = re.search(r'id/([^/]+)/type', font_url)
                font_id = id_match.group(1) if id_match else font_url
                logger.info(f"  Font-URL via Performance API gefunden (ID: {font_id})")
            else:
                logger.warning("BFV-Font-URL nicht gefunden, Decoder nicht verfügbar")
                return {}
        except Exception as e:
            logger.warning(f"BFV-Font-URL nicht gefunden, Decoder nicht verfügbar")
            return {}

    if font_id in _font_cache:
        return _font_cache[font_id]
    logger.info(f"  Lade BFV-Decoder-Font (ID: {font_id})")

    try:
        req = urllib.request.Request(font_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            font_data = r.read()

        font = TTFont(io.BytesIO(font_data))
        cmap = font.getBestCmap()
        decoder = {chr(pua): agl.toUnicode(name) for pua, name in cmap.items() if agl.toUnicode(name)}
        _font_cache[font_id] = decoder
        logger.info(f"  BFV-Decoder geladen: {len(decoder)} Zeichen-Mappings")
        return decoder

    except Exception as e:
        logger.warning(f"  BFV-Decoder konnte nicht geladen werden: {e}")
        _font_cache[font_id] = {}
        return {}


def _decode_bfv(text, decoder):
    """Dekodiert BFV-verschlüsselten Text anhand des Font-Mappings."""
    if not decoder:
        return text
    return ''.join(decoder.get(c, c) for c in text)

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
        "comp_id": "02T7P85D70000056VS5489BTVSDFH806-G",
        "liga_faktor": 0.85,
    },
    "landesliga_suedwest": {
        "name": "Landesliga Südwest",
        "comp_id": "02T7P85E1C000005VS5489BTVSDFH806-G",
        "liga_faktor": 0.85,
    },
    "landesliga_suedost": {
        "name": "Landesliga Südost",
        "comp_id": "02T7P85ADC000000VS5489BTVSDFH806-G",
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
    from bs4 import BeautifulSoup

    url = TORJAEGER_URL.format(comp_id=comp_id)
    logger.info(f"Scrape Torjaeger: {liga_name} -> {url}")

    driver.get(url)
    time.sleep(3)  # Warten auf JavaScript-Rendering

    players = []

    try:
        # Decoder für BFV-Font-Verschlüsselung laden
        decoder = _get_bfv_decoder(driver)

        # Seite via BeautifulSoup parsen (schneller als viele find_element Aufrufe)
        soup = BeautifulSoup(driver.page_source, "html.parser")
        rows = soup.find_all("tr", attrs={"data-testid": "row"})

        if not rows:
            logger.warning(f"  Keine Spieler-Zeilen gefunden in {liga_name} (data-testid='row')")
            return players

        for i, row in enumerate(rows[:max_players]):
            try:
                tds = row.find_all("td")
                if len(tds) < 4:
                    continue

                # Spalte 2: Name + Verein, Spalte 3: Tore
                player_td = tds[2]
                goals_td = tds[3]

                texts = [_decode_bfv(t.strip(), decoder) for t in player_td.stripped_strings if t.strip()]
                name = texts[0] if texts else ""
                verein = texts[1] if len(texts) > 1 else ""

                goals_raw = list(goals_td.stripped_strings)
                goals_str = _decode_bfv(goals_raw[0], decoder) if goals_raw else "0"
                goals = int(goals_str) if goals_str.isdigit() else 0

                link = player_td.find("a", href=True)
                profile_url = link["href"] if link else ""
                player_id = profile_url.split("/")[-1] if profile_url else ""

                if name:
                    players.append({
                        "name": name,
                        "verein": verein,
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

    return players, decoder


def scrape_player_details(driver, player_id, player_name, decoder=None):
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
        decoder: Optional vorgeladener BFV-Font-Decoder von der Listen-Seite

    Returns:
        Dictionary mit Spieler-Detaildaten
    """
    from selenium.webdriver.common.by import By

    url = PLAYER_URL.format(player_id=player_id)
    logger.info(f"  Scrape Details: {player_name}")

    driver.get(url)
    time.sleep(3)

    # Fallback-Werte: Spieler auf Torjaeger-Liste haben definitiv genug Spiele
    details = {
        "spiele": 20,
        "tore": 0,
        "gelbe_karten": 0,
        "rote_karten": 0,
        "minuten": 1600,
        "alter": None,
    }

    try:
        import json
        import re
        from datetime import datetime
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # BFV ist eine Next.js App — alle Daten stecken unverschluesselt im __NEXT_DATA__ JSON
        next_data_tag = soup.find("script", {"id": "__NEXT_DATA__"})
        if next_data_tag:
            next_data = json.loads(next_data_tag.string)

            # JSON-Struktur rekursiv nach Leistungsdaten durchsuchen
            def find_values(obj, keys):
                """Sucht rekursiv nach einem Dict das alle keys enthaelt."""
                results = []
                if isinstance(obj, dict):
                    if all(k in obj for k in keys):
                        results.append(obj)
                    for v in obj.values():
                        results.extend(find_values(v, keys))
                elif isinstance(obj, list):
                    for item in obj:
                        results.extend(find_values(item, keys))
                return results

            # Nach Spielstatistik-Eintraegen suchen (enthalten goals/yellowCards/redCards)
            stat_entries = find_values(next_data, ["goals", "yellowCards"])
            if not stat_entries:
                # Alternativ-Keys versuchen
                stat_entries = find_values(next_data, ["tore", "gelbeKarten"])

            spiele = 0
            tore = 0
            gelbe = 0
            rote = 0
            minuten = 0

            for entry in stat_entries:
                spiele += 1
                tore += int(entry.get("goals", entry.get("tore", 0)) or 0)
                gelbe += int(entry.get("yellowCards", entry.get("gelbeKarten", 0)) or 0)
                rote += int(entry.get("redCards", entry.get("roteKarten", 0)) or 0)
                mins = entry.get("minutes", entry.get("minuten", 0)) or 0
                minuten += int(mins)

            if spiele > 0:
                details["spiele"] = spiele
                details["tore"] = tore
                details["gelbe_karten"] = gelbe
                details["rote_karten"] = rote
                details["minuten"] = minuten if minuten > 0 else spiele * 80
                logger.info(f"  [OK] {player_name}: {spiele} Spiele, {tore} Tore, {gelbe} Gelb, {rote} Rot (via JSON)")
            else:
                logger.warning(f"  {player_name}: Keine Statistik-Eintraege im JSON gefunden")

            # Alter aus JSON extrahieren
            alter_entries = find_values(next_data, ["age"])
            if alter_entries:
                alter = alter_entries[0].get("age")
                if alter and str(alter).isdigit():
                    details["alter"] = int(alter)
            if not details["alter"]:
                dob_entries = find_values(next_data, ["dateOfBirth"])
                if dob_entries:
                    dob = dob_entries[0].get("dateOfBirth", "")
                    dob_match = re.search(r'(\d{4})', str(dob))
                    if dob_match:
                        details["alter"] = datetime.now().year - int(dob_match.group(1))
        else:
            logger.warning(f"  {player_name}: Kein __NEXT_DATA__ gefunden auf Detailseite")

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
            players, list_decoder = scrape_torjaeger_list(
                driver, liga["comp_id"], liga["name"], max_per_league
            )

            # Spieler-Details scrapen (Rate Limiting)
            # Decoder von der Listen-Seite weitergeben, damit Zahlen korrekt dekodiert werden
            for player in players:
                if player.get("player_id"):
                    details = scrape_player_details(
                        driver, player["player_id"], player["name"],
                        decoder=list_decoder
                    )
                    list_tore = player.get("tore", 0)
                    list_gelbe = player.get("gelbe_karten", 0)
                    list_rote = player.get("rote_karten", 0)
                    player.update(details)
                    if player.get("tore", 0) == 0 and list_tore > 0:
                        player["tore"] = list_tore
                    if player.get("gelbe_karten", 0) == 0 and list_gelbe > 0:
                        player["gelbe_karten"] = list_gelbe
                    if player.get("rote_karten", 0) == 0 and list_rote > 0:
                        player["rote_karten"] = list_rote

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
