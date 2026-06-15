import requests
from bs4 import BeautifulSoup
import pandas as pd
import logging

logger = logging.getLogger(__name__)

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

TM_CARD_URLS = {
    "Regionalliga Bayern": "https://www.transfermarkt.de/regionalliga-bayern/gelbekarten/wettbewerb/RLB3",
    "Bayernliga Nord": "https://www.transfermarkt.de/bayernliga-nord/gelbekarten/wettbewerb/OLL5",
    "Bayernliga Süd": "https://www.transfermarkt.de/bayernliga-sud/gelbekarten/wettbewerb/OLL6",
    "Landesliga Mitte": "https://www.transfermarkt.de/landesliga-bayern-mitte/gelbekarten/wettbewerb/LBM",
    "Landesliga Nordost": "https://www.transfermarkt.de/landesliga-bayern-nordost/gelbekarten/wettbewerb/BLN",
    "Landesliga Nordwest": "https://www.transfermarkt.de/landesliga-bayern-nordwest/gelbekarten/wettbewerb/LBNW",
    "Landesliga Südwest": "https://www.transfermarkt.de/landesliga-bayern-sudwest/gelbekarten/wettbewerb/LBSW",
    "Landesliga Südost": "https://www.transfermarkt.de/landesliga-bayern-sudost/gelbekarten/wettbewerb/LBSO",
}

def get_transfermarkt_assists(liga_name):
    """
    Holt echte Assist-Daten (Vorlagen) von Transfermarkt.de fuer eine gegebene Liga.
    """
    url = TM_URLS.get(liga_name)
    if not url:
        logger.info(f"Keine Transfermarkt URL konfiguriert fuer {liga_name}")
        return []
        
    logger.info(f"Scrape Transfermarkt Assists: {url}")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Transfermarkt HTTP Fehler: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Finde die Tabelle "items" (Standard Transfermarkt Tabellenklasse)
        table = soup.select_one("table.items")
        if not table:
            return []
            
        players = []
        rows = table.select("tbody tr")
        
        for row in rows:
            # Transfermarkt Rows koennen odd/even sein
            cols = row.find_all("td")
            if len(cols) < 5:
                continue
                
            # Spielername ist meist im 'hauptlink'
            name_col = row.select_one("td.hauptlink a")
            if not name_col:
                continue
                
            name = name_col.text.strip()
            
            # Assists stehen in der Scorerliste typischerweise in der vorletzten Spalte
            num_cols = row.select("td.zentriert")
            
            # Transfermarkt Layout (8 zentrierte Spalten in der Scorerliste):
            # 0: Platzierung
            # 1: Verein (Bild)
            # 2: Nationalitaet (Bild)
            # 3: Alter
            # 4: Spiele
            # 5: Tore
            # 6: Vorlagen
            # 7: Scorerpunkte (teilweise zusaetzlich Klasse 'hauptlink')
            assists = 0
            if len(num_cols) >= 7:
                try:
                    assists_text = num_cols[6].text.strip()
                    if assists_text and assists_text != '-':
                        assists = int(assists_text)
                except ValueError:
                    pass
                    
            players.append({
                "name": name,
                "assists": assists
            })
            
        logger.info(f"  -> {len(players)} Spieler-Statistiken von Transfermarkt geladen.")
        return players
        
    except Exception as e:
        logger.error(f"Fehler beim Transfermarkt Scraping: {e}")
        return []

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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}


def _search_tm_player(name):
    """Sucht einen Spieler auf Transfermarkt und gibt seine Profil-URL zurueck."""
    import time
    url = f"https://www.transfermarkt.de/schnellsuche/ergebnis/schnellsuche?query={name.replace(' ', '+')}&Spieler_page=0"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return None
        soup = BeautifulSoup(r.text, 'html.parser')
        # Erste Spieler-Ergebnis-Tabelle
        for table in soup.select("table.items"):
            header = table.find_previous("h2")
            if header and "Spieler" not in header.text:
                continue
            link = table.select_one("td.hauptlink a")
            if link and link.get("href"):
                return "https://www.transfermarkt.de" + link["href"]
    except Exception:
        pass
    return None


def _get_player_cards_from_profile(profile_url, liga_key, saison="2025"):
    """
    Laedt die Leistungsdaten eines Spielers von seinem TM-Profil
    und gibt gelbe/rote Karten fuer die angegebene Liga und Saison zurueck.
    """
    try:
        # profil -> leistungsdaten URL bauen
        parts = profile_url.replace("https://www.transfermarkt.de/", "").split("/")
        slug = parts[0]
        player_id = parts[-1]
        stats_url = (
            f"https://www.transfermarkt.de/{slug}/leistungsdaten"
            f"/spieler/{player_id}/plus/0?saison={saison}"
        )
        r = requests.get(stats_url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return 0, 0
        soup = BeautifulSoup(r.text, 'html.parser')

        # Tabellen-Zeilen durchsuchen — Liga-Key in der Zeile finden
        for row in soup.select("table.items tbody tr"):
            wettbewerb = row.select_one("td a.vereinprofil_tooltip, td a")
            if not wettbewerb:
                continue
            href = wettbewerb.get("href", "")
            if liga_key not in href:
                continue
            # Zentrierte Spalten: Einsätze, Tore, Vorlagen, Gelb, Gelb-Rot, Rot, Minuten
            cols = row.select("td.zentriert")
            if len(cols) >= 6:
                try:
                    gelbe = int(cols[3].text.strip()) if cols[3].text.strip().isdigit() else 0
                    rote  = int(cols[5].text.strip()) if cols[5].text.strip().isdigit() else 0
                    return gelbe, rote
                except (ValueError, IndexError):
                    pass
    except Exception:
        pass
    return 0, 0


def get_transfermarkt_cards_for_players(bfv_df):
    """
    Sucht jeden BFV-Spieler auf Transfermarkt und liest seine Karten
    fuer die aktuelle Saison vom Spielerprofil aus.
    """
    import time
    results = []
    total = len(bfv_df)

    for i, (_, row) in enumerate(bfv_df.iterrows()):
        name = row["name"]
        liga = row.get("liga", "")
        liga_key = TM_LIGA_KEYS.get(liga, "")

        logger.info(f"  TM-Karten [{i+1}/{total}]: {name}")
        profile_url = _search_tm_player(name)

        gelbe, rote = 0, 0
        if profile_url and liga_key:
            gelbe, rote = _get_player_cards_from_profile(profile_url, liga_key)
            logger.info(f"    -> {gelbe} Gelb, {rote} Rot")
        else:
            logger.info(f"    -> Spieler nicht gefunden auf TM")

        results.append({"name": name, "gelbe_karten_tm": gelbe, "rote_karten_tm": rote})
        time.sleep(0.5)  # Rate-Limiting

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
