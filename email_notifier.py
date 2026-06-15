"""
E-Mail-Benachrichtigungsmodul.

Sendet automatische Benachrichtigungen an das Trainerteam,
wenn ein Spieler den definierten Score-Schwellenwert überschreitet.

Features:
- HTML-formatierte E-Mails mit Spieler-Zusammenfassung
- PDF-Report als Anhang
- Konfigurierbare Empfängerliste
- SMTP-Authentifizierung mit TLS
- Simulationsmodus (wenn keine E-Mail-Credentials gesetzt)
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from datetime import datetime

from config import EMAIL_CONFIG, SCORE_THRESHOLD_EMAIL, REPORT_CONFIG

logger = logging.getLogger(__name__)


def _create_html_body(player_row, report_path: str) -> str:
    """
    Erstellt den HTML-Body für die Scouting-Alert-E-Mail.

    Args:
        player_row: Series mit Spielerdaten
        report_path: Pfad zum PDF-Report

    Returns:
        HTML-String für den E-Mail-Body
    """
    score = player_row["total_score"]
    name = player_row["name"]

    # Score-Farbe
    if score >= 85:
        score_color = "#27ae60"
        urgency = "SOFORT HANDELN"
    elif score >= 70:
        score_color = "#2980b9"
        urgency = "WEITER BEOBACHTEN"
    else:
        score_color = "#f39c12"
        urgency = "ZUR KENNTNIS"

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #2c3e50;">

        <!-- Header -->
        <div style="background: linear-gradient(135deg, #004990, #2980b9);
                    padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 22px;">
                BFV Scouting Alert
            </h1>
            <p style="color: #bdc3c7; margin: 5px 0 0 0; font-size: 12px;">
                Datenquelle: www.bfv.de | Saison {REPORT_CONFIG['season']}
            </p>
        </div>

        <!-- Score Badge -->
        <div style="background: {score_color}; padding: 15px; text-align: center;">
            <span style="color: white; font-size: 28px; font-weight: bold;">
                {score:.1f}/100
            </span>
            <br>
            <span style="color: white; font-size: 14px; text-transform: uppercase;
                        letter-spacing: 2px;">
                {urgency}
            </span>
        </div>

        <!-- Spieler-Info -->
        <div style="padding: 20px; background: #f9f9f9;">
            <h2 style="color: #2c3e50; margin-top: 0;">
                {name}
            </h2>

            <table style="width: 100%; border-collapse: collapse; margin: 15px 0;">
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold; width: 40%;">
                        Verein
                    </td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">
                        {player_row.get('verein', 'N/A')}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">
                        Liga
                    </td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">
                        {player_row.get('liga', 'N/A')}
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">
                        Tore / Spiele
                    </td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">
                        {int(player_row.get('tore', 0))} Tore in
                        {int(player_row.get('spiele', 0))} Spielen
                        ({player_row.get('tore_pro_spiel', 0):.2f} T/Sp)
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee; font-weight: bold;">
                        Einsatzzeit
                    </td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">
                        {int(player_row.get('minuten', 0))} Minuten
                        ({player_row.get('minuten_pro_spiel', 0):.0f} Min/Spiel)
                    </td>
                </tr>
                <tr>
                    <td style="padding: 8px; font-weight: bold;">
                        Karten
                    </td>
                    <td style="padding: 8px;">
                        {int(player_row.get('gelbe_karten', 0))} Gelbe,
                        {int(player_row.get('rote_karten', 0))} Rote
                    </td>
                </tr>
            </table>

            <p style="color: #7f8c8d; font-size: 12px; margin-top: 15px;">
                Der vollständige Scouting-Report ist als PDF im Anhang beigefügt.
            </p>
        </div>

        <!-- Footer -->
        <div style="background: #ecf0f1; padding: 12px; text-align: center;
                    border-radius: 0 0 8px 8px; font-size: 11px; color: #95a5a6;">
            Automatisch generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}
            <br>
            {REPORT_CONFIG['author']} | Datenquelle: www.bfv.de
        </div>

    </body>
    </html>
    """
    return html


def send_scouting_alert(player_row, report_path: str, simulate: bool = True, ai_fazit: str = "") -> bool:
    """
    Sendet eine Scouting-Alert-E-Mail an das Trainerteam.

    Args:
        player_row: Series mit Spielerdaten und Score
        report_path: Pfad zum generierten PDF-Report
        simulate: Wenn True, wird die E-Mail nur simuliert (kein Versand)

    Returns:
        True wenn erfolgreich (oder simuliert), False bei Fehler
    """
    player_name = player_row["name"]
    score = player_row["total_score"]

    # Prüfe ob Score über Schwellenwert
    if score < SCORE_THRESHOLD_EMAIL:
        logger.info(
            f"  ℹ️  {player_name}: Score {score:.1f} unter Schwellenwert "
            f"({SCORE_THRESHOLD_EMAIL}) - keine E-Mail"
        )
        return False

    subject = EMAIL_CONFIG["subject_template"].format(
        player_name=player_name,
        score=f"{score:.1f}",
    )

    logger.info(f"\n📧 E-Mail-Benachrichtigung für {player_name} (Score: {score:.1f})")
    logger.info(f"   Betreff: {subject}")
    logger.info(f"   Empfänger: {', '.join(EMAIL_CONFIG['recipients'])}")

    if simulate:
        logger.info(f"   ⚠️  SIMULATIONSMODUS - E-Mail wird nicht tatsächlich versendet")
        logger.info(f"   📎 Anhang: {report_path}")
        if ai_fazit:
            logger.info(f"   KI-Fazit: {ai_fazit[:120]}...")
        logger.info(f"   ✅ E-Mail-Simulation erfolgreich")
        return True

    # Tatsächlicher E-Mail-Versand
    try:
        msg = MIMEMultipart()
        msg["From"] = EMAIL_CONFIG["sender_email"]
        msg["To"] = ", ".join(EMAIL_CONFIG["recipients"])
        msg["Subject"] = subject

        # HTML-Body
        html_body = _create_html_body(player_row, report_path)
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        # PDF-Anhang
        if Path(report_path).exists():
            with open(report_path, "rb") as f:
                pdf_attachment = MIMEApplication(f.read(), _subtype="pdf")
                pdf_attachment.add_header(
                    "Content-Disposition",
                    "attachment",
                    filename=Path(report_path).name,
                )
                msg.attach(pdf_attachment)

        # SMTP-Verbindung
        with smtplib.SMTP(EMAIL_CONFIG["smtp_server"], EMAIL_CONFIG["smtp_port"]) as server:
            if EMAIL_CONFIG.get("use_tls", True):
                server.starttls()
            if EMAIL_CONFIG.get("sender_password"):
                server.login(EMAIL_CONFIG["sender_email"], EMAIL_CONFIG["sender_password"])
            server.send_message(msg)

        logger.info(f"   ✅ E-Mail erfolgreich versendet!")
        return True

    except Exception as e:
        logger.error(f"   ❌ E-Mail-Versand fehlgeschlagen: {e}")
        return False


def send_batch_alerts(df_scored, report_paths: dict, simulate: bool = True, ai_fazits: dict = None) -> dict:
    """
    Sendet E-Mail-Alerts für alle Spieler über dem Score-Schwellenwert.

    Args:
        df_scored: DataFrame mit allen bewerteten Spielern
        report_paths: Dict {Spielername: PDF-Pfad}
        simulate: Simulationsmodus

    Returns:
        Dict mit Ergebnissen {Spielername: bool}
    """
    logger.info("\n" + "=" * 60)
    logger.info("E-MAIL-BENACHRICHTIGUNGEN")
    logger.info("=" * 60)

    results = {}
    alert_count = 0
    if ai_fazits is None:
        ai_fazits = {}

    for _, player_row in df_scored.iterrows():
        player_name = player_row["name"]
        if player_row["total_score"] >= SCORE_THRESHOLD_EMAIL:
            report_path = report_paths.get(player_name, "")
            if not report_path:
                logger.info(f"  {player_name}: kein PDF-Report vorhanden, E-Mail wird übersprungen")
                continue
            fazit = ai_fazits.get(player_name, "")
            success = send_scouting_alert(player_row, report_path, simulate=simulate, ai_fazit=fazit)
            results[player_name] = success
            if success:
                alert_count += 1

    logger.info(f"\n📊 {alert_count} E-Mail-Alerts {'simuliert' if simulate else 'versendet'}")
    return results
