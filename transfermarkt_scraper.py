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
            # (Spiele, Tore, Vorlagen, Scorerpunkte)
            # Wir suchen die zentrierten Zahlen
            num_cols = row.select("td.zentriert")
            
            # Transfermarkt Layout:
            # 0: Alter
            # 1: Spiele
            # 2: Tore
            # 3: Vorlagen
            # 4: Scorer
            assists = 0
            if len(num_cols) >= 4:
                try:
                    assists_text = num_cols[3].text.strip()
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

def get_real_assists(bfv_df):
    """
    Hauptfunktion die BFV-Daten nimmt und mit echten Transfermarkt-Assists anreichert.
    """
    all_tm_data = []
    
    # Fuer jede einzigartige Liga im DataFrame
    ligen = bfv_df["liga"].unique()
    
    for liga in ligen:
        data = get_transfermarkt_assists(liga)
        if data:
            all_tm_data.extend(data)
            
    df_tm = pd.DataFrame(all_tm_data)
    return df_tm

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    data = get_transfermarkt_assists("Regionalliga Bayern")
    print(data[:5])
