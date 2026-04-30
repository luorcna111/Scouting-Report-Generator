"""
Datenlade- und Verarbeitungsmodul fuer BFV-Spielerdaten.

Verantwortlich fuer:
1. Laden der BFV-Spielerdaten aus CSV (vorgescrapt oder frisch gescrapt)
2. Berechnung abgeleiteter Metriken (Tore/Spiel, Minuten/Spiel, etc.)
3. Datenvalidierung und Bereinigung
4. Optionaler Live-Scraping-Modus ueber bfv_scraper.py

Datenformat (CSV-Spalten):
    name, verein, liga, liga_faktor, spiele, tore,
    gelbe_karten, rote_karten, minuten
"""

import pandas as pd
import logging
from pathlib import Path
from config import BFV_DATA_PATH, SEARCH_CRITERIA

logger = logging.getLogger(__name__)

def restore_umlauts(df):
    """Stellt in den Daten fehlende Umlaute wieder her."""
    if df.empty:
        return df
        
    replacements = {
        "Muenchen": "München",
        "Wuerzburg": "Würzburg",
        "Wuerzburger": "Würzburger",
        "Fuerth": "Fürth",
        "Nuernberg": "Nürnberg",
        "Noerdlingen": "Nördlingen",
        "Kirchanschoering": "Kirchanschöring",
        "Tuerkguecue": "Türkgücü",
        "Guenes": "Günes",
        "Sued": "Süd",
        "Juergen": "Jürgen",
        "Bjoern": "Björn"
    }
    for old, new in replacements.items():
        if "name" in df.columns:
            df["name"] = df["name"].str.replace(old, new, regex=False)
        if "verein" in df.columns:
            df["verein"] = df["verein"].str.replace(old, new, regex=False)
        if "liga" in df.columns:
            df["liga"] = df["liga"].str.replace(old, new, regex=False)
            
    return df

def load_bfv_data(csv_path=None):
    """
    Laedt BFV-Spielerdaten bevorzugt aus der SQLite Datenbank,
    mit Fallback auf eine CSV-Datei.

    Args:
        csv_path: Pfad zur CSV-Datei (Standard: aus config.py)

    Returns:
        pandas DataFrame mit Rohdaten
    """
    # 1. Versuch: Aus der Datenbank laden
    try:
        from database import load_latest_players_from_db
        df = load_latest_players_from_db()
        if not df.empty:
            logger.info("BFV-Daten erfolgreich aus der lokalen SQLite-Datenbank geladen.")
            logger.info(f"  -> {len(df)} aktuelle Spieler geladen")
            logger.info(f"  -> Ligen: {df['liga'].unique().tolist()}")
            return df
        else:
            logger.info("Datenbank ist noch leer. Fallback auf CSV...")
    except Exception as e:
        logger.warning(f"Konnte nicht aus SQLite-Datenbank laden: {e}")
        logger.info("Fallback auf CSV-Datei...")

    # 2. Fallback: Aus der CSV laden
    path = Path(csv_path) if csv_path else BFV_DATA_PATH

    if not path.exists():
        logger.error(f"BFV-Datendatei nicht gefunden: {path}")
        logger.info("Tipp: Fuehre 'python bfv_scraper.py' aus oder pruefe den Pfad")
        return pd.DataFrame()

    logger.info(f"Lade BFV-Daten aus: {path}")

    df = pd.read_csv(path, encoding="utf-8")

    logger.info(f"  -> {len(df)} Spieler geladen")
    logger.info(f"  -> Ligen: {df['liga'].unique().tolist()}")

    return df


def validate_data(df):
    """
    Validiert und bereinigt die geladenen Daten.

    Prueft auf:
    - Fehlende Pflichtfelder
    - Ungueltige Zahlenwerte
    - Mindestanzahl Spiele (Konfigurierbar)

    Args:
        df: DataFrame mit Rohdaten

    Returns:
        Bereinigter DataFrame
    """
    logger.info("Validiere Daten...")
    
    # Umlaute direkt beim Laden wiederherstellen
    df = restore_umlauts(df)

    # Pflichtfelder pruefen
    required_cols = ["name", "verein", "liga", "spiele", "tore", "minuten"]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        logger.error(f"Fehlende Spalten: {missing}")
        return pd.DataFrame()

    # Zahlenwerte sicherstellen
    numeric_cols = ["spiele", "tore", "gelbe_karten", "rote_karten", "minuten", "liga_faktor"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    # Gelbe/Rote Karten: Fehlende Werte mit 0 fuellen
    if "gelbe_karten" not in df.columns:
        df["gelbe_karten"] = 0
    if "rote_karten" not in df.columns:
        df["rote_karten"] = 0
    if "liga_faktor" not in df.columns:
        df["liga_faktor"] = 1.0
        
    # Alter verarbeiten (Fallback falls nicht verfuegbar)
    from config import SCORING_BENCHMARKS
    fallback_alter = SCORING_BENCHMARKS.get("alter_fallback", 25)
    if "alter" not in df.columns:
        df["alter"] = fallback_alter
    else:
        df["alter"] = pd.to_numeric(df["alter"], errors="coerce").fillna(fallback_alter)

    # Spieler ohne Spiele entfernen
    min_spiele = SEARCH_CRITERIA.get("min_spiele", 5)
    before = len(df)
    df = df[df["spiele"] >= min_spiele].copy()
    removed = before - len(df)
    if removed > 0:
        logger.info(f"  -> {removed} Spieler entfernt (weniger als {min_spiele} Spiele)")

    # Spieler ohne Minuten entfernen
    df = df[df["minuten"] > 0].copy()

    # Duplikate entfernen (gleicher Name + gleicher Verein)
    df = df.drop_duplicates(subset=["name", "verein"], keep="first")

    logger.info(f"  -> {len(df)} Spieler nach Validierung")
    return df


def calculate_derived_metrics(df):
    """
    Berechnet abgeleitete Metriken aus den Rohdaten.

    Metriken:
    - tore_pro_spiel: Tore / Spiele
    - minuten_pro_spiel: Minuten / Spiele
    - karten_gesamt: Gelbe + Rote Karten
    - minuten_pro_tor: Minuten pro erzieltem Tor

    Args:
        df: Validierter DataFrame

    Returns:
        DataFrame mit zusaetzlichen Metrik-Spalten
    """
    logger.info("Berechne abgeleitete Metriken...")

    # Tore pro Spiel
    df["tore_pro_spiel"] = (df["tore"] / df["spiele"]).round(3)

    # Minuten pro Spiel (max 90)
    df["minuten_pro_spiel"] = (df["minuten"] / df["spiele"]).clip(0, 90).round(1)

    # Karten gesamt (fuer Disziplin-Score)
    df["karten_gesamt"] = df["gelbe_karten"] + df["rote_karten"]

    # Minuten pro Tor (Effizienz-Metrik, nur fuer Spieler mit Toren)
    df["minuten_pro_tor"] = df.apply(
        lambda row: round(row["minuten"] / row["tore"], 1) if row["tore"] > 0 else 9999,
        axis=1
    )

    # Logging der Top-Statistiken
    top_scorer = df.nlargest(3, "tore_pro_spiel")
    logger.info(f"\n  Top 3 Torquote:")
    for _, p in top_scorer.iterrows():
        logger.info(f"    {p['name']} ({p['verein']}): {p['tore_pro_spiel']:.2f} Tore/Spiel")

    return df


def apply_filters(df):
    """
    Wendet optionale Filter aus der Konfiguration an.

    Filter:
    - ligen: Nur bestimmte Ligen
    - min_spiele: Mindestanzahl Spiele

    Args:
        df: DataFrame mit berechneten Metriken

    Returns:
        Gefilterter DataFrame
    """
    ligen_filter = SEARCH_CRITERIA.get("ligen")
    if ligen_filter:
        df = df[df["liga"].isin(ligen_filter)].copy()
        logger.info(f"  -> Liga-Filter: {ligen_filter} ({len(df)} Spieler)")

    return df


def load_and_process_all_data(csv_path=None):
    """
    Hauptfunktion: Laedt und verarbeitet alle BFV-Spielerdaten.

    Ablauf:
    1. CSV laden
    2. Daten validieren und bereinigen
    3. Abgeleitete Metriken berechnen
    4. Optional: Filter anwenden

    Args:
        csv_path: Optionaler Pfad zur CSV-Datei

    Returns:
        Vollstaendig verarbeiteter DataFrame
    """
    logger.info("=" * 60)
    logger.info("DATENVERARBEITUNG GESTARTET")
    logger.info("=" * 60)

    # Schritt 1: Daten laden
    df = load_bfv_data(csv_path)
    if df.empty:
        return df

    # Schritt 2: Validieren
    df = validate_data(df)
    if df.empty:
        logger.error("Keine gueltigen Daten nach Validierung!")
        return df

    # Schritt 3: Metriken berechnen
    df = calculate_derived_metrics(df)

    # Schritt 4: Filter anwenden
    df = apply_filters(df)

    # Zusammenfassung
    logger.info(f"\nDatenverarbeitung abgeschlossen:")
    logger.info(f"  Spieler gesamt:     {len(df)}")
    logger.info(f"  Ligen:              {df['liga'].nunique()}")
    logger.info(f"  Vereine:            {df['verein'].nunique()}")
    logger.info(f"  Tore gesamt:        {df['tore'].sum()}")
    logger.info(f"  Durchschn. Spiele:  {df['spiele'].mean():.1f}")
    logger.info(f"  Durchschn. Tore:    {df['tore'].mean():.1f}")

    return df
