import os
import logging

try:
    from google import genai
except ImportError:
    genai = None

logger = logging.getLogger(__name__)

def generate_ai_summary(player_row):
    """
    Generiert ein kurzes 2-3 Saetze Fazit ueber den Spieler mit Hilfe der Gemini API.
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("Kein GEMINI_API_KEY gefunden. Überspringe KI-Fazit.")
        return ""

    if genai is None:
        logger.warning("google-genai nicht installiert. Überspringe KI-Fazit.")
        return ""

    try:
        client = genai.Client(api_key=api_key)
        
        name = player_row.get("name", "Unbekannt")
        alter = player_row.get("alter", 25)
        tore = player_row.get("tore", 0)
        spiele = player_row.get("spiele", 0)
        liga = player_row.get("liga", "Unbekannt")
        score = player_row.get("total_score", 0)
        min_pro_spiel = player_row.get("minuten_pro_spiel", 0)
        
        assists = player_row.get("assists", 0)
        
        prompt = f"""
        Du bist der Chef-Scout eines professionellen bayerischen Fussballvereins. 
        Schreibe ein ausführliches und detailliertes Scouting-Fazit (ca. 4 bis 6 Sätze) über folgenden Spieler:
        
        Name: {name}
        Alter: {alter} Jahre
        Liga: {liga}
        Scouting-Score: {score:.1f}/100
        Statistik: {tore} Tore und {assists} Vorlagen in {spiele} Spielen. Durchschnittlich {min_pro_spiel:.0f} Minuten Einsatzzeit pro Spiel.
        
        Gehe in deinem Fazit detailliert auf Folgendes ein:
        - Interpretation seiner Einsatzzeiten, Torquote und Teamdienlichkeit (Vorlagen)
        - Sein Alter in Bezug auf Transfer- und Entwicklungspotenzial
        - Eine konkrete Handlungsempfehlung (Verpflichten, Beobachten, oder Ignorieren)
        
        Bleibe extrem professionell und objektiv.
        Bitte gib nur das Fazit zurück, ohne Einleitung oder Begrüßung.
        """
        
        import time
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Nutzen der neuen genai API
                response = client.models.generate_content(
                    model='gemini-2.0-flash',
                    contents=prompt
                )
                
                # Kurze Pause für den naechsten Durchlauf
                time.sleep(2)
                return response.text.strip()
                
            except Exception as e:
                if "503" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Google API ueberlastet (503). Versuch {attempt+2} in 5 Sekunden...")
                    time.sleep(5)
                else:
                    raise e
        
    except Exception as e:
        logger.error(f"Fehler bei Gemini API-Aufruf: {e}")
        return ""
