# ⚽ BFV Scouting-Report-Generator

**Automatisierte Spielerbeobachtung & Scouting-Report-Generierung**

> Informationssysteme – Automatisierungs Use Case  
> Option A: Spielerbeobachtung & Scouting-Report-Generator

## 📋 Projektbeschreibung

Ein Python-basiertes Automatisierungssystem, das Live-Spielerstatistiken vom Bayerischen Fußball-Verband (www.bfv.de) extrahiert, normalisiert, Spieler anhand eines streng kalibrierten Modells bewertet und automatisch formatierte Scouting-Reports als PDF generiert. Bei Spielern mit einem Score über einem definierten Schwellenwert (Standard: 70) wird automatisch eine E-Mail an das Trainerteam versendet.

## 🏗️ Architektur

```text
scouting-report-generator/
├── data/                           # Datenquellen (Gescrapte BFV CSVs)
│   └── bfv_spieler.csv             # Hauptdatenbank der gescrapten Spieler
├── output/                         # Generierte Reports & Logs
├── config.py                       # Zentrale Konfiguration (Ligen, Scoring-Parameter)
├── bfv_scraper.py                  # Selenium Live-Scraper für bfv.de
├── data_loader.py                  # Datenverarbeitung & Metriken-Berechnung
├── scoring.py                      # BFV Scoring-Engine
├── report_generator.py             # PDF-Report-Generierung
├── email_notifier.py               # E-Mail-Benachrichtigungen
├── main.py                         # Hauptprogramm (Orchestrator)
├── requirements.txt                # Python-Abhängigkeiten
└── README.md                       # Diese Datei
```

## 🔧 Komplexitätsmerkmale

| Merkmal | Beschreibung |
|---------|-------------|
| **Live-Web-Scraping** | Automatisierte Navigation durch die BFV-Website mittels Selenium (inkl. JavaScript-Rendering) |
| **Metriken-Berechnung** | Ableitung komplexer Leistungsmetriken (Minuten/Spiel, Torquote) aus Rohdaten |
| **Scoring-Logik** | Gewichtetes 4-Kategorien-Scoring mit progressiver Dämpfung und Liga-Faktoren |
| **Dokumentgenerierung** | Professionelle PDF-Reports mit Radar-Charts und Vergleichstabellen |
| **E-Mail-Automatisierung** | HTML-E-Mails mit PDF-Anhang bei Schwellenwert-Überschreitung |

## 🚀 Installation & Ausführung

### Voraussetzungen
- Python 3.9 oder höher
- Google Chrome (für den Selenium Scraper)

### Installation

```bash
# Abhängigkeiten installieren
pip install -r requirements.txt
```

### Ausführung

```bash
# Standard-Analyse (nimmt vorhandene CSV-Daten, erstellt Top 5 Reports)
python main.py

# Live-Scraping von www.bfv.de vor der Analyse erzwingen
python main.py --scrape

# Nur eine bestimmte Liga analysieren (rl = Regionalliga, bl = Bayernliga, ll = Landesliga)
python main.py --liga rl

# Nur Top 3 Spieler generieren
python main.py --top 3

# Nur Spieler mit Score >= 75
python main.py --min-score 75

# E-Mails tatsächlich senden (nicht nur simulieren)
python main.py --send-emails
```

## 📊 Das BFV Scoring-System

Das Scoring-Modell ist absichtlich so kalibriert, dass es **sehr schwer** ist, einen Wert über 70 zu erreichen. Ein Spieler muss in allen Kategorien überdurchschnittlich abliefern (z.B. absoluter Stammspieler sein, kaum Karten sammeln und eine hohe Torquote aufweisen).

### Kategorien & Gewichtungen

| Kategorie | Gewichtung | Benchmark / Zielwert |
|-----------|-----------|-------------|
| **Torquote** | 30% | 1.0 Tore / Spiel = 100 Punkte (mit exponentieller Dämpfung) |
| **Einsatzzeit** | 25% | 90 Min / Spiel = 100 Punkte (Streng: gute Scores erst ab >81 Min) |
| **Spielpraxis** | 20% | 30 Spiele (Sigmoid-Kurve, belohnt Konstanz) |
| **Disziplin** | 25% | 100 Startpunkte (-8 pro Gelb, -35 pro Rot) |

### Liga-Faktoren

Damit Tore in der Regionalliga höher bewertet werden als in der Landesliga, gibt es Multiplikatoren:
- **Regionalliga Bayern**: x1.00
- **Bayernliga (Nord/Süd)**: x0.92
- **Landesligen**: x0.85

### Schwellenwerte

- **≥ 75**: ⭐ Herausragend (Extrem selten, sofort verpflichten)
- **≥ 70**: ✅ Gut (Scouting-Alert E-Mail wird ausgelöst)
- **≥ 45**: ➡️ Durchschnittlich
- **< 45**: ⬇️ Unter Durchschnitt

## 📧 E-Mail-Konfiguration

Für den tatsächlichen E-Mail-Versand Umgebungsvariablen in der Kommandozeile setzen:

**Windows:**
```cmd
set SCOUTING_EMAIL=ihre-email@gmail.com
set SCOUTING_EMAIL_PW=ihr-app-passwort
```

**Hinweis:** Standardmäßig läuft das System im Simulationsmodus – E-Mails werden nur geloggt, nicht versendet. Zum echten Senden `--send-emails` anhängen.

## ⚙️ Konfiguration anpassen

Die Kern-Logik kann in der `config.py` gesteuert werden:
- `BFV_SCORING_WEIGHTS`: Die prozentuale Gewichtung der Kategorien
- `SCORING_BENCHMARKS`: Härtegrad der Bewertung (z.B. wie viel Abzug pro Gelber Karte)
- `LIGA_FAKTOREN`: Bewertung der Ligen zueinander
- `SCORE_THRESHOLD_EMAIL`: Ab welchem Score eine E-Mail verschickt wird
