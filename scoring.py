"""
Scoring-Engine fuer BFV-Spielerbewertung.

Implementiert ein gewichtetes 4-Kategorien-Scoring-System,
basierend auf echten BFV-Daten:

  1. Torquote (30%) - Tore pro Spiel
  2. Einsatzzeit (25%) - Minuten pro Spiel
  3. Spielpraxis (20%) - Anzahl absolvierter Spiele
  4. Disziplin (25%) - Karten-Strafabzuege

KALIBRIERUNG: Der Score ist so eingestellt, dass es SCHWER ist,
ueber 70 Punkte zu kommen. Ein Spieler muss in ALLEN Kategorien
ueberdurchschnittlich sein:
- >0.5 Tore/Spiel (Top-Stuermer-Niveau)
- >80 Min/Spiel (Stammspieler)
- >25 Spiele (fast jedes Spiel mitgemacht)
- Maximal 2-3 Gelbe Karten und keine Rote

Zusaetzlich wird ein Liga-Faktor angewendet:
- Regionalliga Bayern: x1.00
- Bayernliga: x0.92
- Landesliga: x0.85
"""

import pandas as pd
import numpy as np
import logging
from config import (
    BFV_SCORING_WEIGHTS,
    SCORING_BENCHMARKS,
    LIGA_FAKTOREN,
    SCORE_THRESHOLD_EXCELLENT,
    SCORE_THRESHOLD_GOOD,
    SCORE_THRESHOLD_AVERAGE,
)

logger = logging.getLogger(__name__)


def score_scorer_pro_spiel(df):
    """
    Bewertet die Scorerquote (Tore + Assists pro Spiel).

    Formel: ((tore + assists) / spiele) / benchmark * 100
    Benchmark: 1.0 Scorerpunkte/Spiel = Score 100
    """
    benchmark = SCORING_BENCHMARKS.get("scorer_pro_spiel_max", 1.0)
    
    # Sicherstellen, dass Assists vorhanden sind
    if "assists" not in df.columns:
        df["assists"] = 0
        
    scorer_pro_spiel = (df["tore"] + df["assists"]) / df["spiele"].replace(0, 1)

    # Quadratische Daempfung
    raw = scorer_pro_spiel / benchmark
    scores = (raw ** 0.70) * 100

    return scores.clip(0, 100).round(1)




def score_einsatzzeit(df):
    """
    Bewertet die durchschnittliche Einsatzzeit pro Spiel.

    Ein Stammspieler spielt ~90 Minuten pro Spiel.
    Einwechselspieler oder rotierte Spieler deutlich weniger.

    Formel: (minuten_pro_spiel / 90) * 100
    Mit Daempfung: Erst ab 75+ Minuten wirklich gute Scores

    Returns:
        pandas Series mit Scores (0-100)
    """
    benchmark = SCORING_BENCHMARKS["minuten_pro_spiel_max"]

    raw_ratio = df["minuten_pro_spiel"] / benchmark

    # Streng: Nur echte Stammspieler (85+ Min) bekommen gute Scores
    scores = pd.Series(0.0, index=df.index)
    for idx, ratio in raw_ratio.items():
        if ratio >= 0.97:  # 87+ Min/Spiel
            scores[idx] = 90 + (ratio - 0.97) * 333  # 90-100
        elif ratio >= 0.90:  # 81+ Min/Spiel
            scores[idx] = 70 + (ratio - 0.90) * 286  # 70-90
        elif ratio >= 0.80:  # 72+ Min/Spiel
            scores[idx] = 45 + (ratio - 0.80) * 250  # 45-70
        elif ratio >= 0.65:  # 58.5+ Min/Spiel
            scores[idx] = 20 + (ratio - 0.65) * 167  # 20-45
        else:
            scores[idx] = ratio * 31  # 0-20

    return scores.clip(0, 100).round(1)


def score_spielpraxis(df):
    """
    Bewertet die Anzahl absolvierter Spiele.

    Verwendet eine Sigmoid-Funktion:
    - Wenige Spiele (<15) = niedriger Score
    - Mittelfeld (15-25) = ansteigend
    - Viele Spiele (25+) = hoher Score, flacht ab

    Die Sigmoid-Kurve stellt sicher, dass ein Spieler nicht nur
    durch Masse (viele Spiele) einen hohen Score bekommt, sondern
    ein Mindestmass an Einsaetzen nachweisen muss.

    Returns:
        pandas Series mit Scores (0-100)
    """
    optimal = SCORING_BENCHMARKS["spiele_optimal"]
    k = SCORING_BENCHMARKS["spiele_sigmoid_k"]

    # Sigmoid-Funktion - schwerer kalibriert
    midpoint = optimal * 0.6  # ~18 Spiele = 50% Score
    sigmoid = 1 / (1 + np.exp(-k * (df["spiele"] - midpoint)))

    # Skalieren auf 0-100, aber Maximum bei ~85
    scores = sigmoid * 85

    # Kleiner Bonus fuer Spieler die ALLE Spiele gemacht haben (30+)
    bonus = (df["spiele"] >= optimal).astype(float) * 5
    scores = scores + bonus

    return scores.clip(0, 100).round(1)


def score_disziplin(df):
    """
    Bewertet die Karten-Disziplin.

    Startpunktzahl: 100
    Abzuege:
    - Gelbe Karte: -6 Punkte
    - Rote Karte: -30 Punkte

    Beispiele:
    - 0 Karten = 100 (perfekte Disziplin)
    - 2 Gelbe = 88 (gut)
    - 4 Gelbe = 76 (okay)
    - 6 Gelbe = 64 (problematisch)
    - 8 Gelbe = 52 (schlecht)
    - 1 Rote = 70 (schwer)
    - 1 Rote + 4 Gelbe = 46 (sehr schlecht)

    Returns:
        pandas Series mit Scores (0-100)
    """
    basis = SCORING_BENCHMARKS["karten_basis"]
    gelb_strafe = SCORING_BENCHMARKS["karten_gelb_strafe"]
    rot_strafe = SCORING_BENCHMARKS["karten_rot_strafe"]

    scores = basis - (df["gelbe_karten"] * gelb_strafe) - (df["rote_karten"] * rot_strafe)

    return scores.clip(0, 100).round(1)


def score_alter(df):
    """
    Bewertet das Alter (Erfahrungs- und Potenzial-Mix).
    Bis zum optimalen Alter (z.B. 28 Jahre): 100 Punkte.
    Danach stetiger Abfall (erst ab knapp 30 wird es bestraft).
    """
    optimal = SCORING_BENCHMARKS.get("alter_optimal", 28)
    
    # 10 Punkte Abzug pro Jahr ueber dem optimalen Alter
    # 28=100, 29=90, 31=70, 33=50
    scores = 100 - (df["alter"] - optimal).clip(lower=0) * 10
    
    return scores.clip(0, 100).round(1)


def calculate_scores(df):
    """
    Hauptfunktion: Berechnet den Gesamtscore fuer alle Spieler.

    Ablauf:
    1. Vier Kategorie-Scores berechnen (Tore, Einsatzzeit, Praxis, Disziplin)
    2. Gewichteten Gesamtscore berechnen
    3. Liga-Faktor anwenden (hoehere Liga = hoeherer Score)
    4. Spieler nach Score ranken
    5. Bewertungskategorie zuweisen

    Args:
        df: DataFrame mit allen Spielerdaten und abgeleiteten Metriken

    Returns:
        DataFrame mit zusaetzlichen Score-Spalten und Ranking
    """
    logger.info("=" * 60)
    logger.info("SCORING-ENGINE GESTARTET (BFV-Modell)")
    logger.info("=" * 60)

    # Schritt 1: Einzelne Kategorie-Scores berechnen
    logger.info("Berechne Kategorie-Scores...")

    df["score_scorer"] = score_scorer_pro_spiel(df)
    df["score_einsatz"] = score_einsatzzeit(df)
    df["score_praxis"] = score_spielpraxis(df)
    df["score_disziplin"] = score_disziplin(df)
    df["score_alter"] = score_alter(df)

    logger.info(f"  Scorerquote-Scores: Min={df['score_scorer'].min():.1f}, "
                f"Max={df['score_scorer'].max():.1f}, "
                f"Mittel={df['score_scorer'].mean():.1f}")
    logger.info(f"  Einsatzzeit-Scores: Min={df['score_einsatz'].min():.1f}, "
                f"Max={df['score_einsatz'].max():.1f}, "
                f"Mittel={df['score_einsatz'].mean():.1f}")

    # Schritt 2: Gewichteten Gesamtscore berechnen
    logger.info("\nBerechne gewichteten Gesamtscore...")

    weights = BFV_SCORING_WEIGHTS
    df["raw_score"] = (
        df["score_scorer"] * weights.get("scorerquote", 0) +
        df["score_einsatz"] * weights.get("einsatzzeit", 0) +
        df["score_praxis"] * weights.get("spielpraxis", 0) +
        df["score_disziplin"] * weights.get("disziplin", 0) +
        df["score_alter"] * weights.get("alter", 0)
    ).round(1)

    # Schritt 3: Liga-Faktor anwenden
    logger.info("Wende Liga-Faktor an...")
    df["liga_faktor_applied"] = df["liga"].map(LIGA_FAKTOREN).fillna(0.85)
    
    # Globaler Daempfungsfaktor (macht es generell schwerer >70 zu kommen)
    dampening = SCORING_BENCHMARKS.get("score_dampening", 1.0)
    df["total_score"] = (df["raw_score"] * df["liga_faktor_applied"] * dampening).round(1)

    # Schritt 4: Ranking
    df["rank"] = df["total_score"].rank(ascending=False, method="min").astype(int)

    # Schritt 5: Bewertungskategorie
    def categorize(score):
        if score >= SCORE_THRESHOLD_EXCELLENT:
            return "Herausragend"
        elif score >= SCORE_THRESHOLD_GOOD:
            return "Gut"
        elif score >= SCORE_THRESHOLD_AVERAGE:
            return "Durchschnittlich"
        else:
            return "Unter Durchschnitt"

    df["rating"] = df["total_score"].apply(categorize)

    # Sortieren nach Score (absteigend)
    df = df.sort_values("total_score", ascending=False).reset_index(drop=True)

    # Score-Verteilung loggen
    above_70 = len(df[df["total_score"] >= 70])
    above_60 = len(df[df["total_score"] >= 60])
    above_50 = len(df[df["total_score"] >= 50])

    logger.info(f"\n{'=' * 50}")
    logger.info("SCORE-VERTEILUNG:")
    logger.info(f"{'=' * 50}")
    logger.info(f"  Score >= 70: {above_70} Spieler ({above_70/len(df)*100:.1f}%)")
    logger.info(f"  Score >= 60: {above_60} Spieler ({above_60/len(df)*100:.1f}%)")
    logger.info(f"  Score >= 50: {above_50} Spieler ({above_50/len(df)*100:.1f}%)")
    logger.info(f"  Score <  50: {len(df) - above_50} Spieler ({(len(df)-above_50)/len(df)*100:.1f}%)")

    # Top 10 loggen
    logger.info(f"\n{'_' * 50}")
    logger.info("TOP 10 SPIELER:")
    logger.info(f"{'_' * 50}")
    for i, row in df.head(10).iterrows():
        logger.info(
            f"  #{row['rank']:2d} | {row['name']:<25s} | "
            f"{row['liga']:<22s} | Score: {row['total_score']:5.1f} | "
            f"{row['rating']}"
        )
    logger.info(f"{'_' * 50}\n")

    return df


def get_score_breakdown(player_row):
    """
    Erstellt eine detaillierte Aufschluesselung des Scores eines Spielers.

    Returns:
        Dictionary mit Kategorie -> {score, value, weight, beschreibung}
    """
    breakdown = {
        "Scorerquote": {
            "score": player_row.get("score_scorer", 0),
            "value": f"{player_row.get('tore', 0) + player_row.get('assists', 0)} Scorer ({(player_row.get('tore', 0) + player_row.get('assists', 0)) / max(1, player_row.get('spiele', 1)):.2f}/Sp)",
            "raw_value": f"{int(player_row.get('tore', 0))} Tore, {int(player_row.get('assists', 0))} Assists (TM.de)",
            "weight": BFV_SCORING_WEIGHTS.get("scorerquote", 0),
        },
        "Einsatzzeit": {
            "score": player_row.get("score_einsatz", 0),
            "value": f"{player_row.get('minuten_pro_spiel', 0):.0f} Min/Spiel",
            "raw_value": f"{int(player_row.get('minuten', 0))} Minuten gesamt",
            "weight": BFV_SCORING_WEIGHTS["einsatzzeit"],
        },
        "Spielpraxis": {
            "score": player_row.get("score_praxis", 0),
            "value": f"{int(player_row.get('spiele', 0))} Spiele",
            "raw_value": f"Saison 2025/2026",
            "weight": BFV_SCORING_WEIGHTS["spielpraxis"],
        },
        "Disziplin": {
            "score": player_row.get("score_disziplin", 0),
            "value": f"{int(player_row.get('gelbe_karten', 0))}x Gelb, {int(player_row.get('rote_karten', 0))}x Rot",
            "raw_value": f"{int(player_row.get('karten_gesamt', 0))} Karten gesamt",
            "weight": BFV_SCORING_WEIGHTS.get("disziplin", 0),
        },
        "Youngstar-Faktor": {
            "score": player_row.get("score_alter", 0),
            "value": f"{int(player_row.get('alter', 25))} Jahre",
            "raw_value": "Potenzial-Bonus",
            "weight": BFV_SCORING_WEIGHTS.get("alter", 0),
        },
    }

    # Liga-Faktor Info
    liga_faktor = player_row.get("liga_faktor_applied", 1.0)
    breakdown["Liga-Faktor"] = {
        "score": liga_faktor * 100,
        "value": f"x{liga_faktor:.2f}",
        "raw_value": player_row.get("liga", "Unbekannt"),
        "weight": 0,  # Kein Gewicht, ist Multiplikator
    }

    return breakdown
