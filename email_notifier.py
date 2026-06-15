"""
E-Mail-Benachrichtigungsmodul.

Sendet automatische Benachrichtigungen an das Trainerteam,
wenn ein Spieler den definierten Score-Schwellenwert überschreitet.
Sendet zusätzlich simulierte Terminvorschlag-Mails an die Spieler.

Features:
- HTML-formatierte E-Mails mit Spieler-Zusammenfassung
- PDF-Report als Anhang
- Automatische Terminvorschlag-Mails an Spieler (simuliert)
- Konfigurierbare Empfängerliste
- SMTP-Authentifizierung mit TLS
- Simulationsmodus (wenn keine E-Mail-Credentials gesetzt)
"""

import logging
import json
import base64
import requests as http_requests
from pathlib import Path
from datetime import datetime, timedelta

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


def _create_player_invitation_html(player_row, termin_str: str) -> str:
    """
    Erstellt den HTML-Body für die Terminvorschlag-Mail an den Spieler.

    Args:
        player_row: Series mit Spielerdaten
        termin_str: Formatiertes Datum des Terminvorschlags

    Returns:
        HTML-String für den E-Mail-Body
    """
    name = player_row["name"]
    verein = player_row.get("verein", "Ihrem Verein")
    liga = player_row.get("liga", "")

    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; color: #2c3e50;">

        <!-- Header -->
        <div style="background: linear-gradient(135deg, #004990, #2980b9);
                    padding: 20px; text-align: center; border-radius: 8px 8px 0 0;">
            <h1 style="color: white; margin: 0; font-size: 22px;">
                Einladung zum Probetraining
            </h1>
            <p style="color: #bdc3c7; margin: 5px 0 0 0; font-size: 12px;">
                Scouting-Abteilung | Saison {REPORT_CONFIG['season']}
            </p>
        </div>

        <!-- Inhalt -->
        <div style="padding: 25px; background: #f9f9f9;">
            <p style="font-size: 15px;">Sehr geehrter <strong>{name}</strong>,</p>

            <p>wir haben Ihre Leistungen beim <strong>{verein}</strong>
            in der <strong>{liga}</strong> aufmerksam verfolgt und sind
            von Ihrem Potenzial überzeugt.</p>

            <p>Wir möchten Sie herzlich zu einem <strong>Probetraining</strong>
            bei uns einladen:</p>

            <!-- Termin-Box -->
            <div style="background: #004990; color: white; padding: 20px;
                        border-radius: 8px; text-align: center; margin: 25px 0;">
                <p style="margin: 0; font-size: 13px; letter-spacing: 1px;">
                    TERMINVORSCHLAG
                </p>
                <p style="margin: 8px 0 4px 0; font-size: 24px; font-weight: bold;">
                    {termin_str}
                </p>
                <p style="margin: 0; font-size: 14px;">
                    10:00 Uhr | Trainingsgelände
                </p>
            </div>

            <p>Bitte bestätigen Sie Ihre Teilnahme durch eine Antwort auf
            diese E-Mail. Bei Fragen stehen wir Ihnen gerne zur Verfügung.</p>

            <p style="margin-top: 25px;">
                Mit freundlichen Grüßen,<br>
                <strong>Scouting-Abteilung</strong><br>
                {REPORT_CONFIG['club_name']}
            </p>
        </div>

        <!-- Simulations-Hinweis -->
        <div style="background: #f39c12; padding: 10px; text-align: center;
                    font-size: 11px; color: white;">
            SIMULATION – Im Produktivbetrieb würde diese Mail direkt an den Spieler gesendet
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


def _sendgrid_send(api_key, from_email, to_emails, subject, html_content, attachments=None):
    """Sendet eine E-Mail ueber die SendGrid HTTP API (Port 443, kein SMTP)."""
    payload = {
        "personalizations": [{"to": [{"email": e} for e in to_emails]}],
        "from": {"email": from_email},
        "subject": subject,
        "content": [{"type": "text/html", "value": html_content}],
    }
    if attachments:
        payload["attachments"] = attachments

    resp = http_requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        data=json.dumps(payload),
        timeout=15,
    )
    if resp.status_code in (200, 202):
        return True
    logger.error(f"   SendGrid API Fehler {resp.status_code}: {resp.text[:200]}")
    return False


def send_player_invitation(player_row, simulate: bool = True) -> bool:
    """
    Sendet einen automatischen Terminvorschlag an den Spieler (simuliert).
    Im Simulationsmodus geht die Mail an die konfigurierten Scout-Adressen,
    aber mit dem Inhalt als wäre sie an den Spieler gerichtet.

    Args:
        player_row: Series mit Spielerdaten
        simulate: Wenn True, wird die E-Mail nur simuliert (kein Versand)

    Returns:
        True wenn erfolgreich (oder simuliert), False bei Fehler
    """
    name = player_row["name"]

    # Nächsten Montag als Terminvorschlag berechnen
    heute = datetime.now()
    tage_bis_montag = (7 - heute.weekday()) % 7 or 7
    termin = heute + timedelta(days=tage_bis_montag)
    termin_str = termin.strftime("%d.%m.%Y")

    subject = f"Einladung zum Probetraining – {name} [{termin_str}]"

    logger.info(f"\n📅 Terminvorschlag-Mail für {name} (Termin: {termin_str})")
    logger.info(f"   Betreff: {subject}")
    logger.info(f"   Empfänger (simuliert): {name} <spieler@beispiel.de>")
    logger.info(f"   Tatsächlich an: {', '.join(EMAIL_CONFIG['recipients'])}")

    if simulate:
        logger.info(f"   ⚠️  SIMULATIONSMODUS - Mail geht an Scout-Adressen mit Spieler-Inhalt")
        logger.info(f"   ✅ Terminvorschlag-Simulation erfolgreich")
        return True

    # Credentials prüfen bevor eine SMTP-Verbindung versucht wird
    sender_password = EMAIL_CONFIG.get("sender_password", "")
    if not sender_password:
        logger.warning(
            "   ⚠️  Kein SENDGRID_API_KEY konfiguriert. "
            "Terminvorschlag-Mail nicht möglich – bitte Secret in GitHub setzen."
        )
        return False

    try:
        html_body = _create_player_invitation_html(player_row, termin_str)
        success = _sendgrid_send(
            api_key=sender_password,
            from_email=EMAIL_CONFIG["sender_email"],
            to_emails=EMAIL_CONFIG["recipients"],
            subject=subject,
            html_content=html_body,
        )
        if success:
            logger.info(f"   ✅ Terminvorschlag-Mail erfolgreich versendet!")
        return success

    except Exception as e:
        logger.error(f"   ❌ Terminvorschlag-Mail fehlgeschlagen: {e}")
        return False


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
    # Credentials prüfen bevor eine SMTP-Verbindung versucht wird
    sender_password = EMAIL_CONFIG.get("sender_password", "")
    if not sender_password:
        logger.warning(
            "   ⚠️  Kein SENDGRID_API_KEY konfiguriert. "
            "E-Mail-Versand nicht möglich – bitte Secret in GitHub setzen."
        )
        return False

    try:
        html_body = _create_html_body(player_row, report_path)

        # PDF als Base64-Anhang
        attachments = []
        if Path(report_path).exists():
            with open(report_path, "rb") as f:
                attachments.append({
                    "content": base64.b64encode(f.read()).decode(),
                    "type": "application/pdf",
                    "filename": Path(report_path).name,
                    "disposition": "attachment",
                })

        success = _sendgrid_send(
            api_key=sender_password,
            from_email=EMAIL_CONFIG["sender_email"],
            to_emails=EMAIL_CONFIG["recipients"],
            subject=subject,
            html_content=html_body,
            attachments=attachments,
        )
        if success:
            logger.info(f"   ✅ E-Mail erfolgreich versendet!")
        return success

    except Exception as e:
        logger.error(f"   ❌ E-Mail-Versand fehlgeschlagen: {e}")
        return False


def send_batch_alerts(df_scored, report_paths: dict, simulate: bool = True, ai_fazits: dict = None) -> dict:
    """
    Sendet E-Mail-Alerts für alle Spieler über dem Score-Schwellenwert.
    Pro Spieler werden zwei Mails versendet:
    1. Scout-Alert mit PDF-Report an das Trainerteam
    2. Simulierter Terminvorschlag an den Spieler

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
    invitation_count = 0
    if ai_fazits is None:
        ai_fazits = {}

    for _, player_row in df_scored.iterrows():
        player_name = player_row["name"]
        if player_row["total_score"] >= SCORE_THRESHOLD_EMAIL:
            report_path = report_paths.get(player_name, "")
            if not report_path:
                logger.info(f"  {player_name}: kein PDF-Report vorhanden, E-Mail wird übersprungen")
                continue

            # 1. Scout-Alert Mail
            fazit = ai_fazits.get(player_name, "")
            success = send_scouting_alert(player_row, report_path, simulate=simulate, ai_fazit=fazit)
            results[player_name] = success
            if success:
                alert_count += 1

            # 2. Terminvorschlag-Mail an Spieler (simuliert)
            invite_success = send_player_invitation(player_row, simulate=simulate)
            if invite_success:
                invitation_count += 1

    logger.info(f"\n📊 {alert_count} Scout-Alerts {'simuliert' if simulate else 'versendet'}")
    logger.info(f"📅 {invitation_count} Terminvorschläge {'simuliert' if simulate else 'versendet'}")
    return results
