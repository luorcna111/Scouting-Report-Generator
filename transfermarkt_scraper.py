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
    "Regionalliga Bayern": "https://www.transfermarkt.de/regionalliga-bayern/verwarnungen/wettbewerb/RLB3",
    "Bayernliga Nord": "https://www.transfermarkt.de/bayernliga-nord/verwarnungen/wettbewerb/OLL5",
    "Bayernliga Süd": "https://www.transfermarkt.de/bayernliga-sud/verwarnungen/wettbewerb/OLL6",
    "Landesliga Mitte": "https://www.transfermarkt.de/landesliga-bayern-mitte/verwarnungen/wettbewerb/LBM",
    "Landesliga Nordost": "https://www.transfermarkt.de/landesliga-bayern-nordost/verwarnungen/wettbewerb/BLN",
    "Landesliga Nordwest": "https://www.transfermarkt.de/landesliga-bayern-nordwest/verwarnungen/wettbewerb/LBNW",
    "Landesliga Südwest": "https://www.transfermarkt.de/landesliga-bayern-sudwest/verwarnungen/wettbewerb/LBSW",
    "Landesliga Südost": "https://www.transfermarkt.de/landesliga-bayern-sudost/verwarnungen/wettbewerb/LBSO",
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

def get_transfermarkt_cards(liga_name):
    """
    Holt Karten-Daten (Gelbe/Rote Karten) von der Transfermarkt Verwarnungs-Seite.
    """
    url = TM_CARD_URLS.get(liga_name)
    if not url:
        return []

    logger.info(f"Scrape Transfermarkt Karten: {url}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            logger.error(f"Transfermarkt Karten HTTP Fehler: {response.status_code}")
            return []

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.select_one("table.items")
        if not table:
            return []

        players = []
        for row in table.select("tbody tr"):
            name_col = row.select_one("td.hauptlink a")
            if not name_col:
                continue

            name = name_col.text.strip()
            num_cols = row.select("td.zentriert")

            # Transfermarkt Verwarnungs-Layout:
            # 0: Platzierung, 1: Verein, 2: Nationalität, 3: Alter,
            # 4: Spiele, 5: Gelbe, 6: Gelb-Rot, 7: Rote
            gelbe = 0
            rote = 0
            if len(num_cols) >= 8:
                try:
                    g = num_cols[5].text.strip()
                    gelbe = int(g) if g.isdigit() else 0
                except (ValueError, IndexError):
                    pass
                try:
                    r = num_cols[7].text.strip()
                    rote = int(r) if r.isdigit() else 0
                except (ValueError, IndexError):
                    pass

            players.append({"name": name, "gelbe_karten_tm": gelbe, "rote_karten_tm": rote})

        logger.info(f"  -> {len(players)} Spieler-Karten von Transfermarkt geladen.")
        return players

    except Exception as e:
        logger.error(f"Fehler beim Transfermarkt Karten-Scraping: {e}")
        return []


def get_real_assists(bfv_df):
    """
    Hauptfunktion die BFV-Daten nimmt und mit echten Transfermarkt-Assists und Karten anreichert.
    """
    all_assist_data = []
    all_card_data = []

    ligen = bfv_df["liga"].unique()

    for liga in ligen:
        assists = get_transfermarkt_assists(liga)
        if assists:
            all_assist_data.extend(assists)
        cards = get_transfermarkt_cards(liga)
        if cards:
            all_card_data.extend(cards)

    df_assists = pd.DataFrame(all_assist_data) if all_assist_data else pd.DataFrame(columns=["name", "assists"])
    df_cards = pd.DataFrame(all_card_data) if all_card_data else pd.DataFrame(columns=["name", "gelbe_karten_tm", "rote_karten_tm"])

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
