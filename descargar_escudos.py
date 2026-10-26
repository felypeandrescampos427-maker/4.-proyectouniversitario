"""Descarga los escudos que falten en static/escudos.

Fuente 1: TheSportsDB (clave gratuita "3").
Fuente 2 (si la primera falla, por ejemplo con error 403): imagen principal del artículo
del club en Wikipedia.

Uso (desde la carpeta del proyecto, con el entorno .venv activo):
    pip install requests
    py descargar_escudos.py

Los escudos se guardan con el mismo nombre que usa el servidor (por ejemplo realmadrid.png),
así que no hace falta cambiar nada más. Sirve para PC y móvil: ambos leen static/escudos.
Los equipos que ya tienen imagen (como los de la Liga BetPlay) se saltan.
Los que no se encuentren se listan al final.
"""
import os
import time
import unicodedata
from urllib.parse import quote

import requests

# Tu servidor de PC se llama torneo_app.py. Si lo renombras a app.py, el script también lo encuentra.
try:
    from torneo_app import EQUIPOS_POR_LIGA, resolver_escudo  # importar no inicia el servidor
except ImportError:
    from app import EQUIPOS_POR_LIGA, resolver_escudo

BASE = os.path.dirname(os.path.abspath(__file__))
CARPETA = os.path.join(BASE, "static", "escudos")
EXTENSIONES = (".png", ".jpg", ".jpeg", ".webp", ".svg")

API_SPORTSDB = "https://www.thesportsdb.com/api/v1/json/3/searchteams.php"
API_WIKI = "https://en.wikipedia.org/api/rest_v1/page/summary/"

# Algunos servidores rechazan (403) las peticiones que no parecen de un navegador.
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 ArenaLegendsProyecto/1.0"),
    "Accept": "application/json, image/*;q=0.9, */*;q=0.8",
}

# Nombre del código -> nombre con el que lo conoce TheSportsDB (solo los que difieren)
ALIAS = {
    "Atlético de Madrid": "Atletico Madrid",
    "Athletic Club": "Athletic Bilbao",
    "Celta de Vigo": "Celta Vigo",
    "Deportivo Alavés": "Alaves",
    "Deportivo La Coruña": "Deportivo La Coruna",
    "Racing de Santander": "Racing Santander",
    "RCD Espanyol": "Espanyol",
    "Brighton & Hove Albion": "Brighton",
    "AFC Bournemouth": "Bournemouth",
}

# Nombre del código -> título del artículo en Wikipedia (en inglés)
TITULO_WIKI = {
    "Real Madrid": "Real Madrid CF",
    "FC Barcelona": "FC Barcelona",
    "Atlético de Madrid": "Atlético Madrid",
    "Sevilla FC": "Sevilla FC",
    "Real Sociedad": "Real Sociedad",
    "Villarreal CF": "Villarreal CF",
    "Athletic Club": "Athletic Bilbao",
    "Real Betis": "Real Betis",
    "Valencia CF": "Valencia CF",
    "Celta de Vigo": "RC Celta de Vigo",
    "Osasuna": "CA Osasuna",
    "Getafe CF": "Getafe CF",
    "Rayo Vallecano": "Rayo Vallecano",
    "Deportivo Alavés": "Deportivo Alavés",
    "Elche CF": "Elche CF",
    "RCD Espanyol": "RCD Espanyol",
    "Levante UD": "Levante UD",
    "Deportivo La Coruña": "Deportivo de La Coruña",
    "Málaga CF": "Málaga CF",
    "Racing de Santander": "Racing de Santander",
    "Manchester City": "Manchester City F.C.",
    "Arsenal FC": "Arsenal F.C.",
    "Liverpool FC": "Liverpool F.C.",
    "Manchester United": "Manchester United F.C.",
    "Chelsea FC": "Chelsea F.C.",
    "Tottenham Hotspur": "Tottenham Hotspur F.C.",
    "Aston Villa": "Aston Villa F.C.",
    "Newcastle United": "Newcastle United F.C.",
    "Brighton & Hove Albion": "Brighton & Hove Albion F.C.",
    "Crystal Palace": "Crystal Palace F.C.",
    "Everton FC": "Everton F.C.",
    "Fulham FC": "Fulham F.C.",
    "Brentford FC": "Brentford F.C.",
    "AFC Bournemouth": "AFC Bournemouth",
    "Nottingham Forest": "Nottingham Forest F.C.",
    "Leeds United": "Leeds United F.C.",
    "Sunderland AFC": "Sunderland A.F.C.",
    "Coventry City": "Coventry City F.C.",
    "Ipswich Town": "Ipswich Town F.C.",
    "Hull City": "Hull City A.F.C.",
    "Los Angeles Lakers": "Los Angeles Lakers",
    "Golden State Warriors": "Golden State Warriors",
    "Boston Celtics": "Boston Celtics",
    "Chicago Bulls": "Chicago Bulls",
    "New York Yankees": "New York Yankees",
    "Los Angeles Dodgers": "Los Angeles Dodgers",
    "T1": "T1 (esports)",
    "Gen.G": "Gen.G",
    # Liga BetPlay
    "Inter de Bogotá": "Inter de Bogotá",
    # League of Legends (Worlds)
    "Hanwha Life Esports": "Hanwha Life Esports",
    "Dplus KIA": "Dplus KIA",
    "KT Rolster": "KT Rolster",
    "JD Gaming": "JD Gaming",
    "Bilibili Gaming": "Bilibili Gaming",
    "Top Esports": "Top Esports",
    "Weibo Gaming": "Weibo Gaming",
    "LNG Esports": "LNG Esports",
    "G2 Esports": "G2 Esports",
    "Fnatic": "Fnatic",
    "Team Vitality": "Team Vitality",
    "MAD Lions KOI": "Movistar KOI",
    "Cloud9": "Cloud9",
    "Team Liquid": "Team Liquid",
    "FlyQuest": "FlyQuest",
    "100 Thieves": "100 Thieves",
    "PSG Talon": "PSG Talon",
    "CTBC Flying Oyster": "CTBC Flying Oyster",
    # NBA / MLB: casi todos coinciden con su artículo; estos dos difieren
    "Athletics": "Oakland Athletics",
    "Philadelphia 76ers": "Philadelphia 76ers",
}


def sin_tildes(texto):
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def ya_existe(archivo):
    """True si en static/escudos ya hay una imagen para ese escudo (usa la misma
    búsqueda que el servidor, así los de BetPlay con otros nombres también cuentan)."""
    if not os.path.isdir(CARPETA):
        return False
    real = resolver_escudo(archivo)
    return real in os.listdir(CARPETA) and real.lower().endswith(EXTENSIONES)


def url_sportsdb(nombre):
    consulta = ALIAS.get(nombre, sin_tildes(nombre))
    r = requests.get(API_SPORTSDB, params={"t": consulta}, headers=CABECERAS, timeout=15)
    r.raise_for_status()
    for e in (r.json().get("teams") or []):
        if e.get("strBadge"):
            return e["strBadge"]
    raise ValueError("sin resultados en TheSportsDB")


def url_wikipedia(nombre):
    titulo = TITULO_WIKI.get(nombre, nombre)
    r = requests.get(API_WIKI + quote(titulo.replace(" ", "_"), safe=""), headers=CABECERAS, timeout=15)
    r.raise_for_status()
    datos = r.json()
    imagen = datos.get("thumbnail") or datos.get("originalimage")
    if not imagen or not imagen.get("source"):
        raise ValueError("el artículo de Wikipedia no tiene imagen")
    return imagen["source"]


def obtener_url(nombre):
    """Prueba las fuentes en orden y devuelve (url, fuente)."""
    errores = []
    for fuente, funcion in (("TheSportsDB", url_sportsdb), ("Wikipedia", url_wikipedia)):
        try:
            return funcion(nombre), fuente
        except Exception as e:  # noqa: BLE001
            errores.append(f"{fuente}: {e}")
    raise RuntimeError(" | ".join(errores))


def main():
    os.makedirs(CARPETA, exist_ok=True)
    faltan = []
    for liga, equipos in EQUIPOS_POR_LIGA.items():
        for eq in equipos:
            if ya_existe(eq["escudo"]):
                continue
            try:
                url, fuente = obtener_url(eq["name"])
                img = requests.get(url, headers=CABECERAS, timeout=20)
                img.raise_for_status()
                ext = os.path.splitext(url.split("?")[0])[1].lower()
                if ext not in EXTENSIONES:
                    ext = ".png"
                destino = os.path.join(CARPETA, os.path.splitext(eq["escudo"])[0] + ext)
                with open(destino, "wb") as f:
                    f.write(img.content)
                print(f"OK    {eq['name']} ({fuente}) -> {destino}")
            except Exception as e:  # noqa: BLE001
                print(f"FALTA {eq['name']} ({liga}): {e}")
                faltan.append(eq["name"])
            time.sleep(1.5)  # pausa corta para no saturar los servidores

    if faltan:
        print("\nNo se pudieron descargar:", ", ".join(faltan))
        print("Ponlos a mano en static/escudos con el nombre que usa el servidor "
              "(por ejemplo realmadrid.png).")
    else:
        print("\nListo: todos los equipos tienen escudo.")


if __name__ == "__main__":
    main()