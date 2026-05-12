import sqlite3
import logging
from datetime import datetime
from pathlib import Path
from config import DATA_DIR
import pandas as pd

logger = logging.getLogger(__name__)

DB_PATH = DATA_DIR / "scouting_db.sqlite"

def init_db():
    """Initialisiert die Datenbank und erstellt die Tabelle, falls nicht vorhanden."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS players (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        verein TEXT,
        liga TEXT,
        liga_faktor REAL,
        spiele INTEGER,
        tore INTEGER,
        gelbe_karten INTEGER,
        rote_karten INTEGER,
        minuten INTEGER,
        "alter" INTEGER,
        scouted_at TIMESTAMP
    )
    ''')
    conn.commit()
    conn.close()

def save_players_to_db(players):
    """Speichert eine Liste von Spieler-Dictionaries in die SQLite Datenbank."""
    init_db()
    if not players:
        return
        
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    timestamp = datetime.now()
    
    for p in players:
        cursor.execute('''
        INSERT INTO players
        (name, verein, liga, liga_faktor, spiele, tore, gelbe_karten, rote_karten, minuten, "alter", scouted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            p.get("name"),
            p.get("verein"),
            p.get("liga"),
            p.get("liga_faktor"),
            p.get("spiele", 0),
            p.get("tore", 0),
            p.get("gelbe_karten", 0),
            p.get("rote_karten", 0),
            p.get("minuten", 0),
            p.get("alter", None),
            timestamp
        ))
        
    conn.commit()
    conn.close()
    logger.info(f"{len(players)} Spieler erfolgreich in der Datenbank {DB_PATH.name} gespeichert.")

def load_latest_players_from_db():
    """
    Laedt die jeweils AKTUELLSTEN Eintraege jedes Spielers aus der Datenbank
    (falls ein Spieler mehrfach gescoutet wurde, wird nur der neueste Eintrag genommen).
    Gibt ein pandas DataFrame zurueck.
    """
    init_db()
    conn = sqlite3.connect(DB_PATH)
    
    # SQL Query: Wir nehmen nur den neuesten Eintrag pro (name, verein)
    query = '''
    SELECT * FROM players p1
    WHERE scouted_at = (
        SELECT MAX(scouted_at) 
        FROM players p2 
        WHERE p1.name = p2.name AND p1.verein = p2.verein
    )
    '''
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    return df
