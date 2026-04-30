"""
PDF-Report-Generator fuer BFV Scouting-Reports.

Erstellt professionell formatierte PDF-Dokumente mit:
- Kopfzeile mit BFV-Branding und Saison
- Spieler-Profiluebersicht (Steckbrief mit BFV-Daten)
- Radar-Chart (4 Kategorien: Tore, Einsatzzeit, Praxis, Disziplin)
- Detaillierte Score-Aufschluesselung
- Bewertungsempfehlung
- Uebersichts-Report mit Top-Spieler-Ranking

Version 2.0: Angepasst fuer BFV-Daten (Tore, Minuten, Karten)
"""

import io
import re
import logging
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from fpdf import FPDF

from config import OUTPUT_DIR, REPORT_CONFIG, SCORE_THRESHOLD_EMAIL
from scoring import get_score_breakdown

logger = logging.getLogger(__name__)


def _strip_special(text):
    """Entfernt Sonderzeichen und Emojis, behaelt aber echte Umlaute."""
    replacements = {
        '€': 'EUR', '⚽': '', '✅': '[OK]', '⭐': '[*]',
        '➡️': '[-]', '⬇️': '[v]', '📧': '[Mail]',
        '🏆': '[Pokal]', '📊': '', '📋': '', '📂': '',
        '📄': '', '❌': '[X]', '✓': '[OK]',
    }
    result = str(text)
    for old, new in replacements.items():
        result = result.replace(old, new)
    # Entferne alle nicht-latin1 Zeichen
    try:
        result.encode('latin-1')
    except UnicodeEncodeError:
        result = result.encode('latin-1', errors='replace').decode('latin-1')
    return result


class ScoutingPDF(FPDF):
    """Erweiterte FPDF-Klasse mit BFV-Branding."""

    def header(self):
        """Seitenkopf mit BFV-Styling."""
        # Blauer Header-Balken
        r, g, b = REPORT_CONFIG["primary_color"]
        self.set_fill_color(r, g, b)
        self.rect(0, 0, 210, 25, "F")

        # Titel
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(255, 255, 255)
        self.set_y(5)
        self.cell(0, 8, _strip_special(f"BFV SCOUTING REPORT | Saison {REPORT_CONFIG['season']}"), 0, 1, "C")

        # Untertitel
        self.set_font("Helvetica", "", 8)
        self.cell(0, 5, _strip_special(f"Datenquelle: {REPORT_CONFIG['data_source']} | {REPORT_CONFIG['author']}"), 0, 1, "C")

        self.ln(8)

    def footer(self):
        """Seitenfuss."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 7)
        r, g, b = REPORT_CONFIG["text_color"]
        self.set_text_color(r, g, b)
        self.cell(0, 10,
                  _strip_special(f"Seite {self.page_no()} | Generiert: {datetime.now().strftime('%d.%m.%Y %H:%M')} | www.bfv.de"),
                  0, 0, "C")


def _create_radar_chart(player_row, output_path):
    """
    Erstellt ein Radar-Chart mit den Scoring-Kategorien.

    Args:
        player_row: Series mit Spielerdaten und Scores
        output_path: Pfad zum Speichern des Chart-Bildes
    """
    categories = ["Scorerquote", "Einsatzzeit", "Spielpraxis", "Disziplin", "Alter", "Elf d. Woche"]
    scores = [
        player_row.get("score_scorer", 0),
        player_row.get("score_einsatz", 0),
        player_row.get("score_praxis", 0),
        player_row.get("score_disziplin", 0),
        player_row.get("score_alter", 0),
        player_row.get("score_edw", 0),
    ]

    # Anzahl Achsen
    N = len(categories)
    angles = np.linspace(0, 2 * np.pi, N, endpoint=False).tolist()
    scores_plot = scores + [scores[0]]
    angles += [angles[0]]

    fig, ax = plt.subplots(figsize=(5, 5), subplot_kw=dict(polar=True))

    # Stil
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)

    # Achsen-Labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=10, fontweight="bold")

    # Y-Achse (Score 0-100)
    ax.set_ylim(0, 100)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], fontsize=7, color="gray")

    # Farbverlauf basierend auf Gesamtscore
    total = player_row.get("total_score", 0)
    if total >= 70:
        fill_color = "#27ae60"  # Gruen
        line_color = "#1e8449"
    elif total >= 55:
        fill_color = "#3498db"  # Blau
        line_color = "#2471a3"
    elif total >= 40:
        fill_color = "#f39c12"  # Orange
        line_color = "#d68910"
    else:
        fill_color = "#e74c3c"  # Rot
        line_color = "#c0392b"

    # Plot
    ax.plot(angles, scores_plot, "o-", linewidth=2.5, color=line_color)
    ax.fill(angles, scores_plot, alpha=0.25, color=fill_color)

    # Score-Werte an den Punkten
    for angle, score in zip(angles[:-1], scores):
        ax.annotate(f"{score:.0f}",
                    xy=(angle, score),
                    xytext=(5, 5),
                    textcoords="offset points",
                    fontsize=9,
                    fontweight="bold",
                    color=line_color)

    # Titel
    name = player_row.get("name", "Spieler")
    ax.set_title(f"{name}\nGesamtscore: {total:.1f}/100",
                 fontsize=12, fontweight="bold", pad=20)

    # Gitter-Styling
    ax.grid(True, alpha=0.3)
    ax.spines["polar"].set_visible(False)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight",
                facecolor="white", edgecolor="none")
    plt.close()

    return output_path


def generate_single_report(player_row, all_players_df, rank, ai_fazit: str = ""):
    """
    Generiert einen individuellen Scouting-Report als PDF.

    Args:
        player_row: Series mit Spielerdaten
        all_players_df: DataFrame mit allen Spielern (fuer Vergleich)
        rank: Platzierung des Spielers

    Returns:
        Pfad zur generierten PDF-Datei
    """
    name = player_row["name"]
    safe_name = re.sub(r'[^\w\s-]', '', name).replace(' ', '_')
    date_str = datetime.now().strftime("%Y%m%d")
    pdf_path = OUTPUT_DIR / f"Scouting_Report_{safe_name}_{date_str}.pdf"
    chart_path = OUTPUT_DIR / f"_chart_{safe_name}.png"

    logger.info(f"Generiere Report: {name} (Rang #{rank})")

    # Radar-Chart erstellen
    _create_radar_chart(player_row, str(chart_path))

    # PDF erstellen
    pdf = ScoutingPDF()
    pdf.add_page()

    # === STECKBRIEF ===
    pdf.set_font("Helvetica", "B", 16)
    r, g, b = REPORT_CONFIG["secondary_color"]
    pdf.set_text_color(r, g, b)
    pdf.cell(0, 10, _strip_special(f"Spieler-Profil: {name}"), 0, 1)

    # Trennlinie
    pdf.set_draw_color(*REPORT_CONFIG["primary_color"])
    pdf.set_line_width(0.8)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    # Steckbrief-Tabelle
    pdf.set_font("Helvetica", "", 10)
    r, g, b = REPORT_CONFIG["text_color"]
    pdf.set_text_color(r, g, b)

    steckbrief = [
        ("Verein", _strip_special(str(player_row.get("verein", "-")))),
        ("Liga", _strip_special(str(player_row.get("liga", "-")))),
        ("Saison", REPORT_CONFIG["season"]),
        ("Rang", f"#{rank} von {len(all_players_df)} analysierten Spielern"),
        ("Gesamtscore", f"{player_row.get('total_score', 0):.1f} / 100"),
        ("Bewertung", _strip_special(str(player_row.get("rating", "-")))),
    ]

    for label, value in steckbrief:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(50, 7, f"{label}:", 0, 0)
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 7, str(value), 0, 1)

    pdf.ln(3)

    # === STATISTIK-UEBERSICHT ===
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_fill_color(*REPORT_CONFIG["light_bg"])

    stats = [
        ("Spiele", str(int(player_row.get("spiele", 0)))),
        ("Tore", str(int(player_row.get("tore", 0)))),
        ("Tore/Spiel", f"{player_row.get('tore_pro_spiel', 0):.2f}"),
        ("Minuten", str(int(player_row.get("minuten", 0)))),
        ("Min/Spiel", f"{player_row.get('minuten_pro_spiel', 0):.0f}"),
        ("Gelbe Karten", str(int(player_row.get("gelbe_karten", 0)))),
        ("Rote Karten", str(int(player_row.get("rote_karten", 0)))),
    ]

    # 2 Spalten fuer Stats
    col_width = 45
    for i, (label, value) in enumerate(stats):
        x_offset = 10 + (i % 2) * 95
        if i % 2 == 0 and i > 0:
            pass  # Gleiche Zeile
        pdf.set_x(x_offset)
        pdf.set_font("Helvetica", "B", 9)
        pdf.cell(col_width, 6, f"{label}:", 0, 0)
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(col_width, 6, value, 0)
        if i % 2 == 1:
            pdf.ln()

    if len(stats) % 2 == 1:
        pdf.ln()

    pdf.ln(5)

    # === RADAR-CHART ===
    if Path(chart_path).exists():
        pdf.image(str(chart_path), x=30, w=150)
        pdf.ln(5)

    # === SCORE-BREAKDOWN TABELLE ===
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(*REPORT_CONFIG["secondary_color"])
    pdf.cell(0, 10, "Score-Aufschlüsselung", 0, 1)

    pdf.set_draw_color(*REPORT_CONFIG["primary_color"])
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(5)

    breakdown = get_score_breakdown(player_row)

    # Tabellen-Header
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*REPORT_CONFIG["primary_color"])
    pdf.set_text_color(255, 255, 255)
    pdf.cell(45, 8, " Kategorie", 1, 0, "L", True)
    pdf.cell(50, 8, " Wert", 1, 0, "L", True)
    pdf.cell(25, 8, " Score", 1, 0, "C", True)
    pdf.cell(25, 8, " Gewicht", 1, 0, "C", True)
    pdf.cell(45, 8, " Detail", 1, 1, "L", True)

    # Tabellen-Zeilen
    pdf.set_text_color(*REPORT_CONFIG["text_color"])
    for cat_name, cat_data in breakdown.items():
        score = cat_data.get("score", 0)
        weight = cat_data.get("weight", 0)

        # Farbe basierend auf Score
        if score >= 75:
            pdf.set_fill_color(*REPORT_CONFIG["success_color"])
        elif score >= 50:
            pdf.set_fill_color(241, 196, 15)  # Gelb
        elif score >= 25:
            pdf.set_fill_color(*REPORT_CONFIG["warning_color"])
        else:
            pdf.set_fill_color(*REPORT_CONFIG["accent_color"])

        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*REPORT_CONFIG["text_color"])
        pdf.cell(45, 7, f" {_strip_special(cat_name)}", 1, 0, "L")

        pdf.set_font("Helvetica", "", 8)
        pdf.cell(50, 7, f" {_strip_special(str(cat_data.get('value', '')))}", 1, 0, "L")

        # Score-Zelle mit Farbbalken
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(255, 255, 255)
        bar_width = max(score / 100 * 25, 2)
        pdf.cell(25, 7, f" {score:.0f}", 1, 0, "C", True)

        pdf.set_text_color(*REPORT_CONFIG["text_color"])
        pdf.set_fill_color(*REPORT_CONFIG["light_bg"])
        pdf.set_font("Helvetica", "", 8)
        if weight > 0:
            pdf.cell(25, 7, f" {weight*100:.0f}%", 1, 0, "C")
        else:
            pdf.cell(25, 7, " Faktor", 1, 0, "C")

        pdf.cell(45, 7, f" {_strip_special(str(cat_data.get('raw_value', '')))}", 1, 1, "L")

    # Gesamt-Score Zeile
    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 12)
    total = player_row.get("total_score", 0)

    if total >= 70:
        pdf.set_text_color(*REPORT_CONFIG["success_color"])
        empfehlung = "EMPFEHLUNG: Sofort kontaktieren!"
    elif total >= 55:
        pdf.set_text_color(*REPORT_CONFIG["primary_color"])
        empfehlung = "EINSCHÄTZUNG: Beobachtenswert"
    elif total >= 40:
        pdf.set_text_color(*REPORT_CONFIG["warning_color"])
        empfehlung = "EINSCHÄTZUNG: Durchschnittlich"
    else:
        pdf.set_text_color(*REPORT_CONFIG["accent_color"])
        empfehlung = "EINSCHÄTZUNG: Nicht empfohlen"

    pdf.cell(0, 10, f"GESAMTSCORE: {total:.1f} / 100", 0, 1, "C")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 8, _strip_special(empfehlung), 0, 1, "C")

    # KI-Fazit einbinden (wird von aussen uebergeben)
    if ai_fazit:
        pdf.ln(3)
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*REPORT_CONFIG["secondary_color"])
        pdf.multi_cell(0, 5, _strip_special(f"KI-Scouting-Fazit: {ai_fazit}"), 0, "C")

    # Liga-Faktor Hinweis
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*REPORT_CONFIG["text_color"])
    liga_faktor = player_row.get("liga_faktor_applied", 1.0)
    raw_score = player_row.get("raw_score", 0)
    pdf.cell(0, 6,
             f"(Rohscore: {raw_score:.1f} x Liga-Faktor {liga_faktor:.2f} = {total:.1f})",
             0, 1, "C")

    # Speichern
    pdf.output(str(pdf_path))

    # Chart-Bild aufraeumen
    try:
        Path(chart_path).unlink()
    except Exception:
        pass

    logger.info(f"  -> Report gespeichert: {pdf_path.name}")
    return str(pdf_path)


def generate_overview_report(df):
    """
    Generiert einen Uebersichts-Report mit dem Ranking aller Spieler.

    Args:
        df: Sortierter DataFrame mit allen Spieler-Scores

    Returns:
        Pfad zur generierten PDF-Datei
    """
    date_str = datetime.now().strftime("%Y%m%d")
    pdf_path = OUTPUT_DIR / f"BFV_Scouting_Uebersicht_{date_str}.pdf"

    logger.info("Generiere Uebersichts-Report...")

    pdf = ScoutingPDF()
    pdf.add_page()

    # Titel
    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*REPORT_CONFIG["secondary_color"])
    pdf.cell(0, 12, "BFV Scouting-Analyse", 0, 1, "C")
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 8, _strip_special(f"Saison {REPORT_CONFIG['season']} | {len(df)} Spieler analysiert"), 0, 1, "C")

    pdf.set_draw_color(*REPORT_CONFIG["primary_color"])
    pdf.set_line_width(1)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(8)

    # Score-Verteilung
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Score-Verteilung:", 0, 1)
    pdf.set_font("Helvetica", "", 10)

    above_70 = len(df[df["total_score"] >= 70])
    above_60 = len(df[df["total_score"] >= 60])
    above_50 = len(df[df["total_score"] >= 50])

    pdf.cell(0, 6, f"  Score >= 70 (Herausragend): {above_70} Spieler ({above_70/len(df)*100:.1f}%)", 0, 1)
    pdf.cell(0, 6, f"  Score >= 60 (Gut): {above_60} Spieler ({above_60/len(df)*100:.1f}%)", 0, 1)
    pdf.cell(0, 6, f"  Score >= 50 (Durchschnittlich): {above_50} Spieler ({above_50/len(df)*100:.1f}%)", 0, 1)
    pdf.cell(0, 6, f"  Score < 50: {len(df)-above_50} Spieler ({(len(df)-above_50)/len(df)*100:.1f}%)", 0, 1)
    pdf.ln(5)

    # Ligen-Uebersicht
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Ligen:", 0, 1)
    pdf.set_font("Helvetica", "", 10)
    for liga in df["liga"].unique():
        liga_count = len(df[df["liga"] == liga])
        liga_top = df[df["liga"] == liga].iloc[0]
        pdf.cell(0, 6,
                 _strip_special(f"  {liga}: {liga_count} Spieler | "
                               f"Top: {liga_top['name']} ({liga_top['total_score']:.1f})"),
                 0, 1)
    pdf.ln(5)

    # Ranking-Tabelle
    pdf.set_font("Helvetica", "B", 13)
    pdf.cell(0, 10, "Spieler-Ranking (Top 30):", 0, 1)
    pdf.ln(2)

    # Tabellen-Header
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*REPORT_CONFIG["primary_color"])
    pdf.set_text_color(255, 255, 255)
    pdf.cell(10, 7, " #", 1, 0, "C", True)
    pdf.cell(40, 7, " Spieler", 1, 0, "L", True)
    pdf.cell(40, 7, " Verein", 1, 0, "L", True)
    pdf.cell(30, 7, " Liga", 1, 0, "L", True)
    pdf.cell(12, 7, " Tore", 1, 0, "C", True)
    pdf.cell(12, 7, " Sp.", 1, 0, "C", True)
    pdf.cell(12, 7, " T/Sp", 1, 0, "C", True)
    pdf.cell(14, 7, " Kart.", 1, 0, "C", True)
    pdf.cell(20, 7, " Score", 1, 1, "C", True)

    # Tabellen-Zeilen
    pdf.set_text_color(*REPORT_CONFIG["text_color"])

    for i, (_, row) in enumerate(df.head(30).iterrows()):
        if i >= 30:
            break

        # Zeilenhintergrund alternierend
        if i % 2 == 0:
            pdf.set_fill_color(*REPORT_CONFIG["light_bg"])
        else:
            pdf.set_fill_color(255, 255, 255)

        # Score-bedingte Hervorhebung
        score = row["total_score"]
        if score >= SCORE_THRESHOLD_EMAIL:
            pdf.set_font("Helvetica", "B", 7)
        else:
            pdf.set_font("Helvetica", "", 7)

        pdf.cell(10, 6, f" {row['rank']}", 1, 0, "C", True)
        pdf.cell(40, 6, f" {_strip_special(row['name'][:22])}", 1, 0, "L", True)
        pdf.cell(40, 6, f" {_strip_special(str(row['verein'])[:22])}", 1, 0, "L", True)

        # Liga abkuerzen
        liga_short = str(row["liga"]).replace("Regionalliga ", "RL ").replace("Bayernliga ", "BL ").replace("Landesliga ", "LL ")
        pdf.cell(30, 6, f" {_strip_special(liga_short[:16])}", 1, 0, "L", True)

        pdf.cell(12, 6, f" {int(row['tore'])}", 1, 0, "C", True)
        pdf.cell(12, 6, f" {int(row['spiele'])}", 1, 0, "C", True)
        pdf.cell(12, 6, f" {row['tore_pro_spiel']:.2f}", 1, 0, "C", True)

        karten = f"{int(row['gelbe_karten'])}G"
        if row["rote_karten"] > 0:
            karten += f"+{int(row['rote_karten'])}R"
        pdf.cell(14, 6, f" {karten}", 1, 0, "C", True)

        # Score mit Farbe
        if score >= 70:
            pdf.set_text_color(*REPORT_CONFIG["success_color"])
        elif score >= 55:
            pdf.set_text_color(*REPORT_CONFIG["primary_color"])
        else:
            pdf.set_text_color(*REPORT_CONFIG["text_color"])

        pdf.set_font("Helvetica", "B", 8)
        pdf.cell(20, 6, f" {score:.1f}", 1, 1, "C", True)

        pdf.set_text_color(*REPORT_CONFIG["text_color"])

        # Seitenumbruch wenn noetig
        if pdf.get_y() > 265:
            pdf.add_page()
            # Header nochmal
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_fill_color(*REPORT_CONFIG["primary_color"])
            pdf.set_text_color(255, 255, 255)
            pdf.cell(10, 7, " #", 1, 0, "C", True)
            pdf.cell(40, 7, " Spieler", 1, 0, "L", True)
            pdf.cell(40, 7, " Verein", 1, 0, "L", True)
            pdf.cell(30, 7, " Liga", 1, 0, "L", True)
            pdf.cell(12, 7, " Tore", 1, 0, "C", True)
            pdf.cell(12, 7, " Sp.", 1, 0, "C", True)
            pdf.cell(12, 7, " T/Sp", 1, 0, "C", True)
            pdf.cell(14, 7, " Kart.", 1, 0, "C", True)
            pdf.cell(20, 7, " Score", 1, 1, "C", True)
            pdf.set_text_color(*REPORT_CONFIG["text_color"])

    # Footer-Info
    pdf.ln(8)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*REPORT_CONFIG["text_color"])
    pdf.cell(0, 5, "Scoring-Modell: Torquote (30%) + Einsatzzeit (25%) + Spielpraxis (20%) + Disziplin (25%)", 0, 1, "C")
    pdf.cell(0, 5, "Liga-Faktor: Regionalliga x1.00 | Bayernliga x0.92 | Landesliga x0.85", 0, 1, "C")
    pdf.cell(0, 5, f"E-Mail-Alert Schwellenwert: Score >= {SCORE_THRESHOLD_EMAIL}", 0, 1, "C")

    pdf.output(str(pdf_path))
    logger.info(f"  -> Uebersicht gespeichert: {pdf_path.name}")
    return str(pdf_path)
