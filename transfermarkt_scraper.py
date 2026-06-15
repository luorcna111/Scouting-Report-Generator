import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging
import time

logger = logging.getLogger(__name__)

# cloudscraper loest Cloudflare-JS-Challenges automatisch
# (TM sperrt plain requests auf Spieler-Seiten, aber nicht auf Suche)
try:
    import cloudscraper
    _session = cloudscraper.create_scraper(
        browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False}
    )
    logger.info("TM-Scraper: cloudscraper aktiv (Cloudflare-Bypass)")
except ImportError:
    _session = requests.Session()
    _session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept-Language': 'de-DE,de;q=0.9',
        'Referer': 'https://www.transfermarkt.de/',
    })
    logger.warning("TM-Scraper: cloudscraper nicht verfuegbar, Fallback auf requests")

TM_URLS = {
    "Regionalliga Bayern": "https://www.transfermarkt.de/regionalliga-bayern/scorerliste/wettbewerb/RLB3",
    "Bayernliga Nord": "https://www.transfermarkt.de/bayernliga-nord/scorerliste/wettbewerb/OLL5",
    "Bayernliga Süd": "https://www.transfermarkt.de/bayernliga-sud/scorerliste/wettbewerb/OLL6",
    "Landesliga Mitte": "https://www.transfermarkt.de/landesliga-bayern-mitte/scorerliste/wettbewerb/LBM",
    "Landesliga Nordost": "https://www.transfermarkt.de/landesliga-bayern-nordost/scorerliste/wettbewerb/BLN",
    "Landesliga Nordwest": "https://www.transfermarkt.de/landesliga-bayern-nordwest/scorerliste/wettbewerb/LBNW",
    "Landesliga Südwest": "https://www.transfermarkt.de/landesliga-bayern-sudwest/scorerliste/wettbewerb/LBSW",
    "Landesliga Südost": "https://www.transfermarkt.de/landesliga-bayern-sudost/scorerliste/wettbewerb/LBSO",
}

TM_LIGA_KEYS = {
    "Regionalliga Bayern": "RLB3",
    "Bayernliga Nord": "OLL5",
    "Bayernliga Süd": "OLL6",
    "Landesliga Mitte": "LBM",
    "Landesliga Nordost": "BLN",
    "Landesliga Nordwest": "LBNW",
    "Landesliga Südwest": "LBSW",
    "Landesliga Südost": "LBSO",
}


def _tm_get(url, retries=2):
    """GET via shared Session mit Retry bei Fehler."""
    for attempt in range(retries + 1):
        try:
            r = _session.get(url, timeout=15, allow_redirects=True)
            logger.info(f"    GET {url} -> HTTP {r.status_code}")
            if r.status_code == 200:
                return r
            logger.warning(f"    TM HTTP {r.status_code} fuer {url}")
        except Exception as e:
            logger.warning(f"    TM Fehler (Versuch {attempt+1}): {e}")
        if attempt < retries:
            time.sleep(2)
    return None


def get_transfermarkt_assists(liga_name):
    """
    Holt echte Assist-Daten (Vorlagen) von Transfermarkt.de fuer eine gegebene Liga.
    """
    url = TM_URLS.get(liga_name)
    if not url:
        logger.info(f"Keine Transfermarkt URL konfiguriert fuer {liga_name}")
        return []

    logger.info(f"Scrape Transfermarkt Assists: {url}")

    try:
        response = _tm_get(url)
        if not response:
            logger.error(f"Transfermarkt: Keine Antwort fuer {url}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')

        table = soup.select_one("table.items")
        if not table:
            return []

        players = []
        rows = table.select("tbody tr")

        for row in rows:
            cols = row.find_all("td")
            if len(cols) < 5:
                continue

            name_col = row.select_one("td.hauptlink a")
            if not name_col:
                continue

            name = name_col.text.strip()

            # Transfermarkt Scorerliste Spalten (zentriert):
            # 0: Platzierung, 1: Verein, 2: Nationalitaet, 3: Alter,
            # 4: Spiele, 5: Tore, 6: Vorlagen, 7: Scorerpunkte
            num_cols = row.select("td.zentriert")
            assists = 0
            if len(num_cols) >= 7:
                try:
                    assists_text = num_cols[6].text.strip()
                    if assists_text and assists_text != '-':
                        assists = int(assists_text)
                except ValueError:
                    pass

            players.append({"name": name, "assists": assists})

        logger.info(f"  -> {len(players)} Spieler-Statistiken von Transfermarkt geladen.")
        return players

    except Exception as e:
        logger.error(f"Fehler beim Transfermarkt Scraping: {e}")
        return []


def _search_tm_player(name):
    """Sucht einen Spieler auf Transfermarkt und gibt seine Profil-URL zurueck."""
    query = name.replace(' ', '+')
    url = f"https://www.transfermarkt.de/schnellsuche/ergebnis/schnellsuche?query={query}&Spieler_page=0"
    r = _tm_get(url)
    if not r:
        return None
    soup = BeautifulSoup(r.text, 'html.parser')

    for table in soup.select("table.items"):
        header = table.find_previous(["h2", "h3"])
        if header and "Spieler" not in header.get_text():
            continue
        link = table.select_one("td.hauptlink a")
        if link and link.get("href"):
            found_url = "https://www.transfermarkt.de" + link["href"]
            logger.info(f"    TM-Profil gefunden: {found_url}")
            return found_url

    logger.info(f"    -> Kein TM-Treffer fuer '{name}' (Tabellen: {len(soup.select('table.items'))})")
    return None


def _get_player_cards_from_profile(profile_url, liga_key, saison="2025"):
    """
    Laedt die Leistungsdaten eines Spielers und gibt gelbe/rote Karten zurueck.
    URL-Format: /{slug}/leistungsdaten/spieler/{id}?saison=2025
    Spalten (td.zentriert): [0]Einsaetze [1]Tore [2]Vorlagen [3]Gelb [4]GelbRot [5]Rot [6]Min
    """
    try:
        parts = profile_url.replace("https://www.transfermarkt.de/", "").split("/")
        slug = parts[0]
        player_id = parts[-1]
        stats_url = f"https://www.transfermarkt.de/{slug}/leistungsdaten/spieler/{player_id}?saison={saison}"
        logger.info(f"    Leistungsdaten-URL: {stats_url}")

        r = _tm_get(stats_url)
        if not r:
            return 0, 0

        soup = BeautifulSoup(r.text, 'html.parser')
        tables = soup.select("table.items")
        logger.info(f"    -> {len(tables)} items-Tabellen gefunden")

        for table in tables:
            for row in table.select("tbody tr"):
                links = row.find_all("a", href=True)
                if not any(liga_key in a["href"] for a in links):
                    continue

                cols = row.select("td.zentriert")
                col_texts = [c.get_text(strip=True) for c in cols]
                logger.info(f"    -> Liga '{liga_key}' gefunden, Spalten: {col_texts}")

                if len(cols) >= 6:
                    def to_int(cell):
                        t = cell.get_text(strip=True)
                        return int(t) if t.isdigit() else 0
                    return to_int(cols[3]), to_int(cols[5])

        # Liga nicht gefunden — debug logging
        logger.info(f"    -> Liga-Key '{liga_key}' nicht gefunden")
        all_hrefs = [a["href"] for t in tables for a in t.find_all("a", href=True)]
        logger.info(f"    -> Alle hrefs (erste 10): {all_hrefs[:10]}")

    except Exception as e:
        logger.error(f"    Fehler in _get_player_cards_from_profile: {e}")
    return 0, 0


def get_transfermarkt_cards_for_players(bfv_df):
    """
    Sucht jeden BFV-Spieler auf Transfermarkt und liest seine Karten
    fuer die aktuelle Saison vom Spielerprofil aus.
    """
    results = []
    total = len(bfv_df)

    for i, (_, row) in enumerate(bfv_df.iterrows()):
        name = row["name"]
        liga = row.get("liga", "")
        liga_key = TM_LIGA_KEYS.get(liga, "")

        logger.info(f"  TM-Karten [{i+1}/{total}]: {name} (Liga: {liga}, Key: {liga_key})")
        profile_url = _search_tm_player(name)

        gelbe, rote = 0, 0
        if profile_url and liga_key:
            gelbe, rote = _get_player_cards_from_profile(profile_url, liga_key)
            logger.info(f"    -> ERGEBNIS: {gelbe} Gelb, {rote} Rot")
        elif not liga_key:
            logger.warning(f"    -> Kein Liga-Key fuer '{liga}'")
        else:
            logger.info(f"    -> Spieler nicht auf TM gefunden")

        results.append({"name": name, "gelbe_karten_tm": gelbe, "rote_karten_tm": rote})
        time.sleep(1.5)  # TM Rate-Limiting

    return pd.DataFrame(results)


def get_real_assists(bfv_df):
    """
    Hauptfunktion: BFV-Daten mit Transfermarkt-Assists und Karten anreichern.
    """
    all_assist_data = []
    for liga in bfv_df["liga"].unique():
        assists = get_transfermarkt_assists(liga)
        if assists:
            all_assist_data.extend(assists)

    df_assists = pd.DataFrame(all_assist_data) if all_assist_data else pd.DataFrame(columns=["name", "assists"])

    logger.info("Starte TM-Karten-Suche pro Spieler...")
    df_cards = get_transfermarkt_cards_for_players(bfv_df)

    if df_assists.empty and df_cards.empty:
        return pd.DataFrame()

    if not df_assists.empty and not df_cards.empty:
        df_tm = pd.merge(df_assists, df_cards, on="name", how="outer")
    elif not df_assists.empty:
        df_tm = df_assists
    else:
        df_tm = df_cards

    return df_tm


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = get_transfermarkt_assists("Regionalliga Bayern")
    print(data[:5])
