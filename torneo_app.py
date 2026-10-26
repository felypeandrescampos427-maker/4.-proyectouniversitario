"""Arena Legends - servidor Flask (versión PC).

El progreso (saldo, grupos, partidos y predicciones) se guarda en el SERVIDOR, ligado a un
"código de jugador". Con el mismo código ves lo mismo en el celular y en el computador.

Dónde se guarda:
  - En Render: en Upstash Redis (gratis), cuando existen las variables de entorno
    UPSTASH_REDIS_REST_URL y UPSTASH_REDIS_REST_TOKEN. Render borra los archivos del
    servidor cada vez que se reinicia, por eso allí no se puede usar un archivo.
  - En tu PC (sin esas variables): en archivos dentro de la carpeta progreso_local/.
"""
import copy
import hashlib
import json
import math
import os
import random
from datetime import date

import requests
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

PLANTILLA = "index.html"
PUERTO = 5000
UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "").strip().rstrip("/")
UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "").strip()
CARPETA_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "progreso_local")
SALDO_INICIAL = 100_000.0
MAX_RECARGA = 100_000_000

LIGAS_DISPONIBLES = {
    "Fútbol": [
        {"bandera": "🇨🇴", "nombre": "Liga BetPlay Dimayor (Colombia)", "codigo": "CO_LIGA"},
        {"bandera": "🇪🇸", "nombre": "Liga Española (LaLiga)", "codigo": "PD"},
        {"bandera": "🇬🇧", "nombre": "Premier League (Inglaterra)", "codigo": "PL"},
    ],
    "Baloncesto": [
        {"bandera": "🇺🇸", "nombre": "NBA - Liga General", "codigo": "NBA"},
    ],
    "Béisbol": [
        {"bandera": "⚾", "nombre": "MLB - Grandes Ligas (USA)", "codigo": "MLB"},
    ],
    "eSports": [
        {"bandera": "🎮", "nombre": "League of Legends (Worlds)", "codigo": "lol"},
    ],
}

RANGOS_MARCADOR = {
    "Fútbol": (0, 5),
    "Baloncesto": (60, 110),
    "Béisbol": (0, 12),
    "eSports": (0, 3),
}

# En estos deportes no existe el empate, así que se repite el sorteo si salen iguales.
DEPORTES_SIN_EMPATE = {"Baloncesto", "Béisbol", "eSports"}

# Predicciones: cuota = cuánto se multiplica lo apostado si aciertas. Se calcula según las
# probabilidades reales de cada deporte (ver probabilidades()), con un 5 % de margen.
MARGEN_CUOTAS = 0.95
MONTO_MIN_PREDICCION = 1_000

NOMBRE_LIGA = {
    liga["codigo"]: liga["nombre"]
    for ligas in LIGAS_DISPONIBLES.values()
    for liga in ligas
}
DEPORTE_DE_LIGA = {
    liga["codigo"]: deporte
    for deporte, ligas in LIGAS_DISPONIBLES.items()
    for liga in ligas
}

# ---------------------------------------------------------------------------
# Escudos: se busca en static/escudos el archivo real, sea cual sea su sufijo
# (por ejemplo "nacional" -> "nacional_transparente_correcto.png").
# ---------------------------------------------------------------------------
ESCUDOS_DIR = os.path.join(app.static_folder, "escudos")
EXT_IMG = (".png", ".jpg", ".jpeg", ".webp", ".svg")
# clave del código -> prefijo del archivo real (solo los que difieren)
ALIAS_ESCUDO = {
    "deportivocali": "cali",
    "bucaramanga": "bucaros",
    "chico": "boyaca",
    "aguilas": "aguilas_doradas",
}


def resolver_escudo(archivo):
    """Devuelve el nombre del archivo que existe en static/escudos para esa clave."""
    clave = os.path.splitext(archivo or "")[0].lower()
    if not clave:
        return archivo
    clave = ALIAS_ESCUDO.get(clave, clave)
    try:
        for f in sorted(os.listdir(ESCUDOS_DIR)):
            nombre, ext = os.path.splitext(f)
            if ext.lower() in EXT_IMG and nombre.lower().startswith(clave):
                return f
    except OSError:
        pass
    return archivo


def _equipos(bandera, id_inicial, lista):
    """Crea la lista de equipos de una liga a partir de (nombre, archivo_escudo)."""
    return [
        {"id": id_inicial + i, "name": nombre, "group": None, "flag": bandera,
         "escudo": resolver_escudo(escudo)}
        for i, (nombre, escudo) in enumerate(lista)
    ]


EQUIPOS_POR_LIGA = {
    "CO_LIGA": _equipos("🇨🇴", 1, [
        ("Atlético Nacional", "nacional.png"),
        ("Millonarios FC", "millonarios.png"),
        ("América de Cali", "america.png"),
        ("Junior de Barranquilla", "junior.png"),
        ("Independiente Santa Fe", "santafe.png"),
        ("Deportivo Cali", "deportivocali.png"),
        ("Independiente Medellín", "medellin.png"),
        ("Once Caldas", "oncecaldas.png"),
        ("Deportes Tolima", "tolima.png"),
        ("Atlético Bucaramanga", "bucaramanga.png"),
        ("Envigado FC", "envigado.png"),
        ("Deportivo Pereira", "pereira.png"),
        ("Inter de Bogotá", "interbogota.png"),
        ("Águilas Doradas", "aguilas.png"),
        ("Boyacá Chicó", "chico.png"),
        ("Alianza FC", "alianza.png"),
        ("Fortaleza CEIF", "fortaleza.png"),
        ("Jaguares de Córdoba", "jaguares.png"),
        ("Patriotas Boyacá", "patriotas.png"),
        ("Deportivo Pasto", "pasto.png"),
    ]),
    "PD": _equipos("🇪🇸", 1, [
        ("Real Madrid", "realmadrid.png"),
        ("FC Barcelona", "barcelona.png"),
        ("Atlético de Madrid", "atletico.png"),
        ("Sevilla FC", "sevilla.png"),
        ("Real Sociedad", "realsociedad.png"),
        ("Villarreal CF", "villarreal.png"),
        ("Athletic Club", "athletic.png"),
        ("Real Betis", "betis.png"),
        ("Valencia CF", "valencia.png"),
        ("Celta de Vigo", "celta.png"),
        ("Osasuna", "osasuna.png"),
        ("Getafe CF", "getafe.png"),
        ("Rayo Vallecano", "rayo.png"),
        ("Deportivo Alavés", "alaves.png"),
        ("Elche CF", "elche.png"),
        ("RCD Espanyol", "espanyol.png"),
        ("Levante UD", "levante.png"),
        ("Deportivo La Coruña", "lacoruna.png"),
        ("Málaga CF", "malaga.png"),
        ("Racing de Santander", "racing.png"),
    ]),
    "PL": _equipos("🇬🇧", 101, [
        ("Manchester City", "mancity.png"),
        ("Arsenal FC", "arsenal.png"),
        ("Liverpool FC", "liverpool.png"),
        ("Manchester United", "manutd.png"),
        ("Chelsea FC", "chelsea.png"),
        ("Tottenham Hotspur", "tottenham.png"),
        ("Aston Villa", "astonvilla.png"),
        ("Newcastle United", "newcastle.png"),
        ("Brighton & Hove Albion", "brighton.png"),
        ("Crystal Palace", "crystalpalace.png"),
        ("Everton FC", "everton.png"),
        ("Fulham FC", "fulham.png"),
        ("Brentford FC", "brentford.png"),
        ("AFC Bournemouth", "bournemouth.png"),
        ("Nottingham Forest", "nottinghamforest.png"),
        ("Leeds United", "leeds.png"),
        ("Sunderland AFC", "sunderland.png"),
        ("Coventry City", "coventry.png"),
        ("Ipswich Town", "ipswich.png"),
        ("Hull City", "hull.png"),
    ]),
    "NBA": _equipos("🇺🇸", 301, [
        ("Los Angeles Lakers", "lakers.png"),
        ("Golden State Warriors", "warriors.png"),
        ("Boston Celtics", "celtics.png"),
        ("Chicago Bulls", "bulls.png"),
        ("Atlanta Hawks", "atlanta_hawks.png"),
        ("Brooklyn Nets", "brooklyn_nets.png"),
        ("Charlotte Hornets", "charlotte_hornets.png"),
        ("Cleveland Cavaliers", "cleveland_cavaliers.png"),
        ("Detroit Pistons", "detroit_pistons.png"),
        ("Indiana Pacers", "indiana_pacers.png"),
        ("Miami Heat", "miami_heat.png"),
        ("Milwaukee Bucks", "milwaukee_bucks.png"),
        ("New York Knicks", "new_york_knicks.png"),
        ("Orlando Magic", "orlando_magic.png"),
        ("Philadelphia 76ers", "philadelphia_76ers.png"),
        ("Toronto Raptors", "toronto_raptors.png"),
        ("Washington Wizards", "washington_wizards.png"),
        ("Dallas Mavericks", "dallas_mavericks.png"),
        ("Denver Nuggets", "denver_nuggets.png"),
        ("Houston Rockets", "houston_rockets.png"),
    ]),
    "MLB": _equipos("⚾", 401, [
        ("New York Yankees", "yankees.png"),
        ("Los Angeles Dodgers", "dodgers.png"),
        ("Baltimore Orioles", "baltimore_orioles.png"),
        ("Boston Red Sox", "boston_red_sox.png"),
        ("Tampa Bay Rays", "tampa_bay_rays.png"),
        ("Toronto Blue Jays", "toronto_blue_jays.png"),
        ("Chicago White Sox", "chicago_white_sox.png"),
        ("Cleveland Guardians", "cleveland_guardians.png"),
        ("Detroit Tigers", "detroit_tigers.png"),
        ("Kansas City Royals", "kansas_city_royals.png"),
        ("Minnesota Twins", "minnesota_twins.png"),
        ("Houston Astros", "houston_astros.png"),
        ("Los Angeles Angels", "los_angeles_angels.png"),
        ("Athletics", "mlb_athletics.png"),
        ("Seattle Mariners", "seattle_mariners.png"),
        ("Texas Rangers", "texas_rangers.png"),
        ("Atlanta Braves", "atlanta_braves.png"),
        ("Miami Marlins", "miami_marlins.png"),
        ("New York Mets", "new_york_mets.png"),
        ("Philadelphia Phillies", "philadelphia_phillies.png"),
    ]),
    "lol": _equipos("🎮", 501, [
        ("T1", "t1.png"),
        ("Gen.G", "geng.png"),
        ("Hanwha Life Esports", "hanwha_life_esports.png"),
        ("Dplus KIA", "dplus_kia.png"),
        ("KT Rolster", "kt_rolster.png"),
        ("JD Gaming", "jd_gaming.png"),
        ("Bilibili Gaming", "bilibili_gaming.png"),
        ("Top Esports", "top_esports.png"),
        ("Weibo Gaming", "weibo_gaming.png"),
        ("LNG Esports", "lng_esports.png"),
        ("G2 Esports", "g2_esports.png"),
        ("Fnatic", "fnatic.png"),
        ("Team Vitality", "team_vitality.png"),
        ("MAD Lions KOI", "mad_lions_koi.png"),
        ("Cloud9", "cloud9.png"),
        ("Team Liquid", "team_liquid.png"),
        ("FlyQuest", "flyquest.png"),
        ("100 Thieves", "100_thieves.png"),
        ("PSG Talon", "psg_talon.png"),
        ("CTBC Flying Oyster", "ctbc_flying_oyster.png"),
    ]),
}

DEFAULT_STATE = {
    "balance_cop": SALDO_INICIAL,
    "deporte_activo": "Fútbol",
    "liga_activa": "CO_LIGA",
    "ligas": LIGAS_DISPONIBLES,
    "equipos_por_liga": EQUIPOS_POR_LIGA,
    "groups": ["A", "B", "C", "D", "E"],
    "max_group_capacity": 4,
    "matches": [],
    "monto_min_prediccion": MONTO_MIN_PREDICCION,
    "predictions": [],
}

# Equipos que cambiaron de nombre: se actualiza lo que ya estaba guardado.
RENOMBRES = {"La Equidad": "Inter de Bogotá"}

CAMPOS_PREDICCION = ("id", "liga", "home", "away", "eleccion", "cuota", "monto", "estado")


# ---------------------------------------------------------------------------
# Estado (se guarda en el servidor, ligado al código de jugador)
# ---------------------------------------------------------------------------
def estado_inicial():
    data = copy.deepcopy(DEFAULT_STATE)
    # El calendario cuenta los días desde esta fecha; así las fechas no cambian cada día.
    data["fecha_inicio"] = date.today().isoformat()
    return data


def normalizar(data):
    """Pone al día el estado que manda el navegador: la configuración manda el código,
    pero se conservan el saldo, los grupos asignados, los partidos y las predicciones."""
    base = estado_inicial()
    data.pop("api_keys", None)
    data.pop("logs", None)

    data.pop("cuotas", None)  # las cuotas se calculan al responder, según el deporte
    data.pop("partidos_cuotas", None)
    data.pop("eliminatorias", None)
    data.pop("campeon", None)
    for clave in ("ligas", "groups", "max_group_capacity", "monto_min_prediccion"):
        data[clave] = base[clave]

    try:
        saldo = float(data.get("balance_cop", base["balance_cop"]))
        data["balance_cop"] = saldo if math.isfinite(saldo) and saldo >= 0 else base["balance_cop"]
    except (TypeError, ValueError):
        data["balance_cop"] = base["balance_cop"]

    if data.get("deporte_activo") not in LIGAS_DISPONIBLES:
        data["deporte_activo"] = base["deporte_activo"]
    if data.get("liga_activa") not in EQUIPOS_POR_LIGA:
        data["liga_activa"] = base["liga_activa"]

    try:
        date.fromisoformat(str(data.get("fecha_inicio")))
    except ValueError:
        data["fecha_inicio"] = base["fecha_inicio"]

    guardados_por_liga = data.get("equipos_por_liga", {})
    data["equipos_por_liga"] = {}
    for codigo, equipos_base in base["equipos_por_liga"].items():
        guardados = {t["id"]: t for t in guardados_por_liga.get(codigo, [])}
        data["equipos_por_liga"][codigo] = [
            {**equipo, "group": guardados.get(equipo["id"], {}).get("group")}
            for equipo in equipos_base
        ]

    partidos = data.get("matches")
    data["matches"] = [m for m in partidos if isinstance(m, dict) and "liga" in m] \
        if isinstance(partidos, list) else []
    # Los partidos guardados pueden traer nombres de escudo antiguos: se actualizan.
    for m in data["matches"]:
        for lado in ("home", "away"):
            if m.get(lado) in RENOMBRES:
                m[lado] = RENOMBRES[m[lado]]
                m[lado + "_escudo"] = "interbogota.png"
        m["home_escudo"] = resolver_escudo(m.get("home_escudo", ""))
        m["away_escudo"] = resolver_escudo(m.get("away_escudo", ""))

    predicciones = data.get("predictions")
    data["predictions"] = [
        p for p in predicciones
        if isinstance(p, dict) and all(c in p for c in CAMPOS_PREDICCION)
    ] if isinstance(predicciones, list) else []
    for p in data["predictions"]:
        for lado in ("home", "away"):
            p[lado] = RENOMBRES.get(p[lado], p[lado])
    return data


class CodigoInvalido(Exception):
    pass


class ErrorAlmacenamiento(Exception):
    pass


def limpiar_codigo(valor):
    """El código no distingue mayúsculas y debe tener entre 4 y 40 caracteres."""
    codigo = str(valor or "").strip().lower()
    return codigo if 4 <= len(codigo) <= 40 else None


def clave_de(codigo):
    """Lo que se guarda no lleva el código en claro, sino su huella (SHA-256)."""
    return "arena:" + hashlib.sha256(codigo.encode("utf-8")).hexdigest()[:40]


def usa_upstash():
    return bool(UPSTASH_URL and UPSTASH_TOKEN)


def _redis(comando):
    """Ejecuta un comando de Redis por la API REST de Upstash."""
    try:
        r = requests.post(UPSTASH_URL, headers={"Authorization": f"Bearer {UPSTASH_TOKEN}"},
                          json=comando, timeout=8)
        r.raise_for_status()
        return r.json().get("result")
    except (requests.RequestException, ValueError) as e:
        raise ErrorAlmacenamiento(str(e)) from e


def _ruta_local(clave):
    return os.path.join(CARPETA_LOCAL, clave.split(":", 1)[1] + ".json")


def leer_crudo(clave):
    if usa_upstash():
        return _redis(["GET", clave])
    try:
        with open(_ruta_local(clave), "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ErrorAlmacenamiento(str(e)) from e


def guardar_crudo(clave, texto):
    if usa_upstash():
        _redis(["SET", clave, texto])
        return
    try:
        os.makedirs(CARPETA_LOCAL, exist_ok=True)
        with open(_ruta_local(clave), "w", encoding="utf-8") as f:
            f.write(texto)
    except OSError as e:
        raise ErrorAlmacenamiento(str(e)) from e


def leer_estado(codigo):
    crudo = leer_crudo(clave_de(codigo))
    if not crudo:
        return None
    try:
        return json.loads(crudo)
    except ValueError:
        return None


def guardar_estado(codigo, data):
    guardar_crudo(clave_de(codigo), json.dumps(data, ensure_ascii=False))


def abrir(req):
    """Lee el progreso del código que mandó el navegador (o crea uno nuevo).
    Si el navegador dice en qué liga está, esa pasa a ser la liga activa: así el celular
    y el PC pueden estar en ligas distintas sin pisarse."""
    codigo = limpiar_codigo(req.get("codigo"))
    if not codigo:
        raise CodigoInvalido()

    guardado = leer_estado(codigo)
    data = None
    if isinstance(guardado, dict):
        try:
            data = normalizar(guardado)
        except (KeyError, TypeError, ValueError, AttributeError):
            data = None
    if data is None:
        data = estado_inicial()

    liga = req.get("liga")
    if liga in DEPORTE_DE_LIGA:
        data["liga_activa"] = liga
        data["deporte_activo"] = DEPORTE_DE_LIGA[liga]
    return codigo, data


def responder(codigo, data, **extra):
    """Guarda el progreso y responde con el estado nuevo."""
    guardar_estado(codigo, data)
    return ok(data, **extra)


# ---------------------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------------------
TITULOS_FASE = {"previa": "Previa", "octavos": "Octavos de final", "cuartos": "Cuartos de final",
                "semis": "Semifinales", "final": "Final"}
_BYE = object()


def _es_grupos(m):
    return m.get("fase", "grupos") == "grupos"


def clasificados(data, liga):
    """Los primeros de cada grupo, de mejor a peor (puntos, diferencia de gol, goles a favor).
    Devuelve [] mientras falten partidos de la fase de grupos."""
    grupos = {}
    for t in data["equipos_por_liga"].get(liga, []):
        if t["group"]:
            grupos.setdefault(t["group"], []).append(t)
    jugados = [m for m in data["matches"] if m["liga"] == liga and _es_grupos(m)]
    vistos = {frozenset((m["home"], m["away"])) for m in jugados}
    primeros = []
    for g, miembros in grupos.items():
        if len(miembros) < 2:
            continue
        for i, a in enumerate(miembros):
            for b in miembros[i + 1:]:
                if frozenset((a["name"], b["name"])) not in vistos:
                    return []
        tabla = {t["name"]: [0, 0, 0] for t in miembros}  # puntos, diferencia, goles a favor
        for m in jugados:
            if m["home"] in tabla and m["away"] in tabla:
                gh, ga = m["home_score"], m["away_score"]
                for nombre, gf, gc in ((m["home"], gh, ga), (m["away"], ga, gh)):
                    tabla[nombre][0] += 3 if gf > gc else (1 if gf == gc else 0)
                    tabla[nombre][1] += gf - gc
                    tabla[nombre][2] += gf
        mejor = min(miembros, key=lambda t: (-tabla[t["name"]][0], -tabla[t["name"]][1],
                                              -tabla[t["name"]][2], t["name"]))
        primeros.append((tuple(-x for x in tabla[mejor["name"]]), mejor["name"], mejor))
    primeros.sort(key=lambda x: (x[0], x[1]))
    return [x[2] for x in primeros]


def eliminatorias(data, liga):
    """Cruces de las fases finales: clasifican los primeros de cada grupo. Si no son una
    potencia de 2 (con 5 grupos, por ejemplo) los mejores pasan directo: hay una previa
    antes de las semifinales. Devuelve (lista de cruces, campeón o None)."""
    sembrados = clasificados(data, liga)
    n = len(sembrados)
    if n < 2:
        return [], None
    tam = 2
    while tam < n:
        tam *= 2
    orden = [1]
    while len(orden) < tam:
        total = len(orden) * 2 + 1
        orden = [x for s in orden for x in (s, total - s)]
    entradas = [sembrados[s - 1] if s <= n else _BYE for s in orden]
    jugados = [m for m in data["matches"] if m["liga"] == liga and not _es_grupos(m)]
    lista = []
    while True:
        if _BYE in entradas and len(entradas) != 4:
            fase = "previa"          # algunos equipos pasan directo y juegan una ronda antes
        else:                        # con 3 equipos, la primera ronda ya es la semifinal
            fase = {2: "final", 4: "semis", 8: "cuartos", 16: "octavos"}[len(entradas)]
        siguientes = []
        for i in range(0, len(entradas), 2):
            a, b = entradas[i], entradas[i + 1]
            if a is _BYE or b is _BYE:
                siguientes.append(b if a is _BYE else a)  # pasa directo a la siguiente ronda
                continue
            partido, ganador, estado = None, None, "por_definir"
            if a and b:
                estado = "pendiente"
                partido = next((m for m in jugados if m.get("fase") == fase and
                                frozenset((m["home"], m["away"])) == frozenset((a["name"], b["name"]))),
                               None)
            if partido:
                estado = "jugado"
                gana_local = partido["home_score"] > partido["away_score"]
                nombre = partido["home"] if gana_local else partido["away"]
                ganador = a if a["name"] == nombre else b
            lista.append({
                "fase": fase, "titulo": TITULOS_FASE[fase], "estado": estado,
                "home": a["name"] if a else None, "home_escudo": a["escudo"] if a else "",
                "home_flag": a["flag"] if a else "",
                "away": b["name"] if b else None, "away_escudo": b["escudo"] if b else "",
                "away_flag": b["flag"] if b else "",
                "home_score": partido["home_score"] if partido else None,
                "away_score": partido["away_score"] if partido else None,
            })
            siguientes.append(ganador)
        if len(entradas) == 2:
            return lista, siguientes[0]
        entradas = siguientes


def probabilidades(deporte):
    """Probabilidad real de local / empate / visita según cómo se genera el marcador."""
    if deporte in DEPORTES_SIN_EMPATE:
        return {"local": 0.5, "empate": 0.0, "visita": 0.5}
    minimo, maximo = RANGOS_MARCADOR.get(deporte, (0, 5))
    empate = 1 / (maximo - minimo + 1)  # los dos lados sortean entre N valores iguales
    return {"local": (1 - empate) / 2, "empate": empate, "visita": (1 - empate) / 2}


def cuotas_para(deporte):
    """Cuota de cada resultado (en deportes sin empate no existe la clave 'empate')."""
    return {r: round(MARGEN_CUOTAS / p, 2) for r, p in probabilidades(deporte).items() if p > 0}


def probs_partido(deporte, liga, home, away, fase="grupos"):
    """Probabilidades de ESTE partido. Salen de una "semilla" hecha con la liga y los dos
    equipos: cada partido tiene las suyas (unos los gana más el local, otros el visitante),
    pero para el mismo partido siempre son las mismas, no cambian al recargar la página."""
    a, b = sorted((home, away))
    semilla = f"{liga}|{a}|{b}" if fase == "grupos" else f"{liga}|{fase}|{a}|{b}"
    h = hashlib.sha256(semilla.encode("utf-8")).hexdigest()
    r1 = int(h[:8], 16) / 0xFFFFFFFF
    r2 = int(h[8:16], 16) / 0xFFFFFFFF
    fuerza_a = 0.20 + 0.60 * r1            # parte del reparto que se lleva el equipo "a"
    if deporte in DEPORTES_SIN_EMPATE or fase != "grupos":
        empate = 0.0                       # en las fases finales siempre hay un ganador
    else:
        empate = 0.15 + 0.15 * r2          # entre 15 % y 30 %
    pa = (1 - empate) * fuerza_a
    pb = (1 - empate) - pa
    local, visita = (pa, pb) if home == a else (pb, pa)
    return {"local": local, "empate": empate, "visita": visita}


def cuotas_partido(deporte, liga, home, away, fase="grupos"):
    probs = probs_partido(deporte, liga, home, away, fase)
    return {r: round(MARGEN_CUOTAS / p, 2) for r, p in probs.items() if p > 0}


def resumen_partidos(data):
    """Cuotas y porcentajes de todos los partidos posibles de la liga activa
    (clave "local|visitante", en los dos órdenes)."""
    liga, deporte = data["liga_activa"], data["deporte_activo"]
    equipos = data["equipos_por_liga"].get(liga, [])
    salida = {}
    for g in data["groups"]:
        miembros = [t for t in equipos if t["group"] == g]
        for i, a in enumerate(miembros):
            for b in miembros[i + 1:]:
                for h, v in ((a["name"], b["name"]), (b["name"], a["name"])):
                    p = probs_partido(deporte, liga, h, v)
                    salida[f"{h}|{v}"] = {
                        "cuotas": cuotas_partido(deporte, liga, h, v),
                        "probs": {r: round(x * 100, 1) for r, x in p.items()},
                    }
    for x in eliminatorias(data, liga)[0]:
        if x["home"] and x["away"]:
            h, v, f = x["home"], x["away"], x["fase"]
            p = probs_partido(deporte, liga, h, v, f)
            salida[f"{h}|{v}|{f}"] = {
                "cuotas": cuotas_partido(deporte, liga, h, v, f),
                "probs": {r: round(y * 100, 1) for r, y in p.items()},
            }
    return salida


def ok(data, **extra):
    cruces, campeon = eliminatorias(data, data["liga_activa"])
    estado = {**data, "cuotas": cuotas_para(data["deporte_activo"]),
              "partidos_cuotas": resumen_partidos(data),
              "eliminatorias": cruces, "campeon": campeon["name"] if campeon else None}
    return jsonify({"status": "success", "state": estado, **extra})


def error(mensaje, titulo="Ups, algo salió mal", tipo="error", codigo=400):
    """tipo: 'error' o 'aviso'. El navegador lo usa para elegir el color del mensaje."""
    return jsonify({"status": "error", "tipo": tipo, "titulo": titulo, "message": mensaje}), codigo


@app.errorhandler(CodigoInvalido)
def _codigo_invalido(_):
    return error("Escribe un código de jugador de al menos 4 caracteres.",
                 "Código no válido", "aviso", 401)


@app.errorhandler(ErrorAlmacenamiento)
def _almacenamiento(_):
    return error("No pudimos leer o guardar tu progreso. Intenta de nuevo en unos segundos.",
                 "Problema al guardar", "error", 503)


def generar_marcador_para(deporte, probs):
    """Sortea el resultado con las probabilidades del partido y luego un marcador que lo cumpla."""
    resultado = random.choices(["local", "empate", "visita"],
                               weights=[probs["local"], probs["empate"], probs["visita"]])[0]
    for _ in range(500):
        local, visitante = generar_marcador(deporte)
        if (resultado == "local" and local > visitante) or \
           (resultado == "visita" and local < visitante) or \
           (resultado == "empate" and local == visitante):
            return local, visitante
    minimo, maximo = RANGOS_MARCADOR.get(deporte, (0, 5))
    return {"local": (minimo + 1, minimo), "visita": (minimo, minimo + 1),
            "empate": (minimo, minimo)}[resultado]


def generar_marcador(deporte):
    minimo, maximo = RANGOS_MARCADOR.get(deporte, (0, 5))
    local = random.randint(minimo, maximo)
    visitante = random.randint(minimo, maximo)
    while deporte in DEPORTES_SIN_EMPATE and local == visitante:
        visitante = random.randint(minimo, maximo)
    return local, visitante


# ---------------------------------------------------------------------------
# Transmisión en vivo: genera la lista de eventos que el navegador reproduce
# ---------------------------------------------------------------------------
NOMBRES = ["Mateo", "Daniel", "David", "Juan", "Santiago", "Sebastián", "Alejandro", "Andrés",
           "Carlos", "Luis", "Mauricio", "Felipe", "Nicolás", "Camilo", "Jorge", "Diego",
           "Samuel", "Julián", "Esteban", "Miguel"]
APELLIDOS = ["González", "Rodríguez", "López", "Pérez", "Martínez", "Castro", "Gómez", "Ramírez",
             "Torres", "Díaz", "Vargas", "Moreno", "Rojas", "Herrera", "Muñoz", "Ortiz",
             "Suárez", "Cardona", "Mejía", "Ríos"]

JUGADAS_FUTBOL = [
    "Disparo de {j} ({eq}) que se va por encima del arco.",
    "¡Atajadón! El portero de {rival} evita el gol de {eq}.",
    "Tiro de esquina para {eq}.",
    "¡Al palo! El remate de {j} ({eq}) pega en el poste.",
    "Falta peligrosa cerca del área de {rival}.",
]

CONFIG_GENERICA = {
    "Baloncesto": {
        "periodos": 4, "etiqueta": "Cuarto", "cierre": True,
        "opciones": [(3, "¡Triple de {j}!"), (2, "Canasta de {j}."),
                     (2, "¡Mate espectacular de {j}!"), (1, "Tiro libre convertido por {j}.")],
        "pesos": [3, 6, 2, 3],
        "jugadas": ["¡Tapón de {j}!", "Robo de balón de {j}.", "Rebote ofensivo de {j}.",
                    "Tiempo muerto pedido por {eq}."],
    },
    "Béisbol": {
        "periodos": 9, "etiqueta": "Entrada", "cierre": False,
        "opciones": [(1, "Carrera anotada por {j}."), (1, "Sencillo productor de {j}."),
                     (2, "¡Jonrón de dos carreras de {j}!"),
                     (3, "¡Cuadrangular con bases llenas de {j}!")],
        "pesos": [6, 5, 2, 1],
        "jugadas": ["Ponche de {j}.", "Doble matanza de {eq}.", "Elevado de {j} atrapado en el jardín."],
    },
    "eSports": {
        "periodos": None, "etiqueta": "Mapa", "cierre": False,
        "opciones": [(1, "{eq} se lleva el mapa gracias a {j}.")],
        "pesos": [1],
        "jugadas": [],
    },
}


def _plantilla(cantidad=16):
    nombres = set()
    while len(nombres) < cantidad:
        nombres.add(f"{random.choice(NOMBRES)} {random.choice(APELLIDOS)}")
    return list(nombres)


def _evento(eventos, marcador, t, corto, tipo, texto, lado=None, reloj=None):
    eventos.append({"t": t, "corto": corto, "reloj": reloj or corto, "tipo": tipo,
                    "texto": texto, "lado": lado, "marcador": list(marcador)})


def _eventos_futbol(local, visitante, goles_local, goles_visitante):
    nombres = {"home": local["name"], "away": visitante["name"]}
    rival = {"home": visitante["name"], "away": local["name"]}
    plantillas = {lado: _plantilla() for lado in nombres}
    titulares = {lado: plantillas[lado][:11] for lado in nombres}
    suplentes = {lado: plantillas[lado][11:] for lado in nombres}  # el índice 0 es el arquero

    cambios = []  # (minuto, lado, sale, entra)
    for lado in nombres:
        cantidad = random.randint(1, 3)
        salen = random.sample(titulares[lado][1:], cantidad)
        entran = random.sample(suplentes[lado], cantidad)
        minutos = sorted(random.sample(range(46, 86), cantidad))
        cambios += list(zip(minutos, [lado] * cantidad, salen, entran))

    expulsados = {}  # jugador -> minuto
    if random.random() < 0.12:
        lado = random.choice(list(nombres))
        ya_cambiados = {c[2] for c in cambios}
        candidatos = [j for j in titulares[lado][1:] if j not in ya_cambiados]
        expulsados[random.choice(candidatos)] = (random.randint(20, 85), lado)

    def en_cancha(lado, minuto):
        activos = list(titulares[lado])
        for m, l, sale, entra in cambios:
            if l == lado and m <= minuto:
                activos[activos.index(sale)] = entra
        return [j for j in activos if not (j in expulsados and expulsados[j][0] <= minuto)]

    crudos = [(0, -2, "inicio", None, None), (45, 0, "descanso", None, None),
              (46, -1, "info", None, None), (90, 9, "fin", None, None)]

    orden = ["home"] * goles_local + ["away"] * goles_visitante
    random.shuffle(orden)
    minutos_gol = sorted(random.sample([m for m in range(2, 90) if m != 45], len(orden)))
    crudos += [(m, 0, "gol", lado, None) for m, lado in zip(minutos_gol, orden)]

    libres = [m for m in range(5, 90) if m != 45]
    for _ in range(random.randint(0, 4)):
        crudos.append((random.choice(libres), 0, "amarilla", random.choice(list(nombres)), None))
    for _ in range(random.randint(3, 5)):
        crudos.append((random.choice(libres), 0, "jugada", random.choice(list(nombres)), None))
    crudos += [(m, 0, "cambio", lado, (sale, entra)) for m, lado, sale, entra in cambios]
    for jugador, (minuto, lado) in expulsados.items():
        crudos.append((minuto, 0, "roja", lado, jugador))

    eventos, marcador = [], [0, 0]
    amonestados = set()
    for minuto, _, tipo, lado, dato in sorted(crudos, key=lambda c: (c[0], c[1])):
        eq = nombres.get(lado)
        corto = f"{minuto}'"
        if tipo == "inicio":
            texto = "¡Inicia el partido! Los 22 jugadores pisan el césped."
        elif tipo == "descanso":
            texto = "¡FIN DEL PRIMER TIEMPO / DESCANSO!"
        elif tipo == "info":
            texto = "Comienza el segundo tiempo."
        elif tipo == "fin":
            texto = "¡Silbatazo final! Partido concluido."
        elif tipo == "gol":
            marcador[0 if lado == "home" else 1] += 1
            autor = random.choice(en_cancha(lado, minuto)[1:])
            texto = f"¡GOL! Anotación de {autor} ({eq}) [{marcador[0]}-{marcador[1]}]"
        elif tipo == "amarilla":
            jugador = random.choice([j for j in en_cancha(lado, minuto)[1:] if j not in amonestados])
            amonestados.add(jugador)
            texto = f"Tarjeta amarilla para {jugador} ({eq}) por falta fuerte en el medio campo."
        elif tipo == "roja":
            texto = f"¡Tarjeta roja directa para {dato} ({eq})! Se queda con diez."
        elif tipo == "cambio":
            texto = f"Cambio en {eq}: Sale {dato[0]}, entra {dato[1]}."
        else:  # jugada
            jugador = random.choice(en_cancha(lado, minuto)[1:])
            texto = random.choice(JUGADAS_FUTBOL).format(j=jugador, eq=eq, rival=rival[lado])
        _evento(eventos, marcador, minuto, corto, tipo, texto, lado)
    return eventos


def _descomponer(total, opciones, pesos):
    """Reparte un marcador en jugadas (por ejemplo, 98 puntos en triples, canastas y libres)."""
    jugadas = []
    while total > 0:
        validas = [(o, p) for o, p in zip(opciones, pesos) if o[0] <= total]
        jugada = random.choices([v[0] for v in validas], [v[1] for v in validas])[0]
        jugadas.append(jugada)
        total -= jugada[0]
    return jugadas


def _eventos_genericos(deporte, local, visitante, puntos_local, puntos_visitante):
    cfg = CONFIG_GENERICA[deporte]
    nombres = {"home": local["name"], "away": visitante["name"]}
    jugadores = {lado: _plantilla(8) for lado in nombres}

    anotaciones = []  # [periodo, lado, valor, texto]
    for lado, total in (("home", puntos_local), ("away", puntos_visitante)):
        for valor, texto in _descomponer(total, cfg["opciones"], cfg["pesos"]):
            anotaciones.append([0, lado, valor, texto])
    random.shuffle(anotaciones)

    if cfg["periodos"] is None:  # eSports: cada punto es un mapa
        periodos = max(1, len(anotaciones))
        for i, a in enumerate(anotaciones):
            a[0] = i + 1
    else:
        periodos = cfg["periodos"]
        for p, a in zip(sorted(random.randint(1, periodos) for _ in anotaciones), anotaciones):
            a[0] = p

    etiqueta = cfg["etiqueta"]
    eventos, marcador = [], [0, 0]
    _evento(eventos, marcador, 0, "0", "inicio", "¡Comienza el partido!", reloj="Inicio")

    for p in range(1, periodos + 1):
        t = round(p / periodos * 90)
        corto = f"{etiqueta} {p}"
        if cfg["jugadas"] and random.random() < 0.6:
            lado = random.choice(list(nombres))
            texto = random.choice(cfg["jugadas"]).format(j=random.choice(jugadores[lado]), eq=nombres[lado])
            _evento(eventos, marcador, t, corto, "jugada", texto, lado)
        for _, lado, valor, plantilla_texto in [a for a in anotaciones if a[0] == p]:
            marcador[0 if lado == "home" else 1] += valor
            texto = plantilla_texto.format(j=random.choice(jugadores[lado]), eq=nombres[lado])
            _evento(eventos, marcador, t, corto, "gol", f"{texto} [{marcador[0]}-{marcador[1]}]", lado)
        if cfg["cierre"] and p < periodos:
            _evento(eventos, marcador, t, corto, "descanso", f"Fin del {etiqueta.lower()} {p}.")

    ganador = nombres["home"] if marcador[0] > marcador[1] else nombres["away"]
    _evento(eventos, marcador, 90, "Final", "fin", f"¡Final del partido! {ganador} se lleva la victoria.")
    return eventos


def construir_transmision(deporte, local, visitante, puntos_local, puntos_visitante):
    if deporte == "Fútbol":
        eventos = _eventos_futbol(local, visitante, puntos_local, puntos_visitante)
    else:
        eventos = _eventos_genericos(deporte, local, visitante, puntos_local, puntos_visitante)
    resumen = lambda t: {"name": t["name"], "escudo": t["escudo"], "flag": t["flag"]}
    return {"deporte": deporte, "home": resumen(local), "away": resumen(visitante), "eventos": eventos}


# ---------------------------------------------------------------------------
# Predicciones
# ---------------------------------------------------------------------------
def resolver_predicciones(data, partido):
    """Cierra las predicciones pendientes de este partido, guarda el resultado
    y paga las acertadas."""
    par = frozenset((partido["home"], partido["away"]))
    for p in data["predictions"]:
        if p["estado"] != "pendiente" or p["liga"] != partido["liga"]:
            continue
        if frozenset((p["home"], p["away"])) != par:
            continue
        if p.get("fase", "grupos") != partido.get("fase", "grupos"):
            continue

        # Los goles se miran desde el equipo "local" de la predicción.
        if p["home"] == partido["home"]:
            goles_home, goles_away = partido["home_score"], partido["away_score"]
        else:
            goles_home, goles_away = partido["away_score"], partido["home_score"]

        if goles_home > goles_away:
            resultado = "local"
        elif goles_home < goles_away:
            resultado = "visita"
        else:
            resultado = "empate"

        p["marcador"] = [goles_home, goles_away]
        p["resultado"] = resultado
        if p["eleccion"] == resultado:
            p["estado"] = "ganada"
            p["premio"] = round(p["monto"] * p["cuota"], 2)
            data["balance_cop"] = round(data["balance_cop"] + p["premio"], 2)
        else:
            p["estado"] = "perdida"


# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template(PLANTILLA, state=estado_inicial())


@app.route("/api/health", methods=["GET"])
def health():
    """Sirve para comprobar dónde se está guardando el progreso (no muestra secretos)."""
    try:
        guardar_crudo("arena:ping", "ok")
        funciona = leer_crudo("arena:ping") == "ok"
    except ErrorAlmacenamiento:
        funciona = False
    return jsonify({"almacenamiento": "upstash" if usa_upstash() else "archivo local",
                    "funciona": funciona})


@app.route("/api/load", methods=["POST"])
def load_state():
    """Entrega el progreso guardado con este código (o crea uno nuevo)."""
    req = request.get_json(silent=True) or {}
    codigo, data = abrir(req)
    return responder(codigo, data)


@app.route("/api/reset", methods=["POST"])
def reset_state():
    """Reinicia SOLO la liga que está abierta: borra sus grupos, partidos y predicciones.
    Conserva el saldo y devuelve lo apostado en predicciones que aún no se habían jugado.
    Las demás ligas no se tocan."""
    req = request.get_json(silent=True) or {}
    codigo, data = abrir(req)
    liga = data["liga_activa"]
    reembolso = sum(p["monto"] for p in data["predictions"]
                    if p["estado"] == "pendiente" and p["liga"] == liga)
    data["balance_cop"] = round(data["balance_cop"] + reembolso, 2)
    for t in data["equipos_por_liga"].get(liga, []):
        t["group"] = None
    data["matches"] = [m for m in data["matches"] if m["liga"] != liga]
    data["predictions"] = [p for p in data["predictions"] if p["liga"] != liga]
    return responder(codigo, data)


@app.route("/api/deposit", methods=["POST"])
def deposit():
    req = request.get_json(silent=True) or {}
    try:
        monto = float(req.get("monto"))
    except (TypeError, ValueError):
        return error("Escribe un monto válido, solo con números.", "Monto no válido", "aviso")

    if not math.isfinite(monto) or monto <= 0:
        return error("El monto debe ser mayor a 0.", "Monto no válido", "aviso")
    if monto > MAX_RECARGA:
        return error(f"Por recarga puedes agregar hasta $ {MAX_RECARGA:,.0f}.".replace(",", "."),
                     "Monto demasiado alto", "aviso")

    codigo, data = abrir(req)
    data["balance_cop"] = round(data["balance_cop"] + monto, 2)
    return responder(codigo, data)


@app.route("/api/set_active_league", methods=["POST"])
def set_active_league():
    req = request.get_json(silent=True) or {}
    deporte = req.get("deporte")
    codigo_liga = req.get("codigo_liga")

    codigos_validos = {liga["codigo"] for liga in LIGAS_DISPONIBLES.get(deporte, [])}
    if codigo_liga not in codigos_validos:
        return error("Esa liga no existe para el deporte elegido.", "Liga no encontrada")

    codigo, data = abrir(req)
    data["deporte_activo"] = deporte
    data["liga_activa"] = codigo_liga
    return responder(codigo, data)


@app.route("/api/assign_group", methods=["POST"])
def assign_group():
    req = request.get_json(silent=True) or {}
    team_id = req.get("team_id")
    grupo = req.get("group")

    codigo, data = abrir(req)
    liga = data["liga_activa"]
    equipos = data["equipos_por_liga"].get(liga, [])

    if grupo not in data["groups"]:
        return error("Elige un grupo entre A y E.", "Grupo no válido")

    equipo = next((t for t in equipos if t["id"] == team_id), None)
    if equipo is None:
        return error("No encontramos ese equipo en la liga activa.", "Equipo no encontrado")

    if any(m["liga"] == liga for m in data["matches"]):
        return error("Ya hay partidos jugados en esta liga. Reinicia el torneo si quieres "
                     "armar los grupos de nuevo.", "El torneo ya comenzó", "aviso")

    ocupados = sum(1 for t in equipos if t["group"] == grupo and t["id"] != team_id)
    if ocupados >= data["max_group_capacity"]:
        return error(f"El Grupo {grupo} ya tiene {data['max_group_capacity']} equipos. "
                     "Elige otro grupo.", "Grupo lleno", "aviso")

    equipo["group"] = grupo
    return responder(codigo, data)


@app.route("/api/predict", methods=["POST"])
def predict():
    req = request.get_json(silent=True) or {}
    home, away, eleccion = req.get("home"), req.get("away"), req.get("eleccion")
    fase = req.get("fase") or "grupos"
    try:
        monto = float(req.get("monto"))
    except (TypeError, ValueError):
        return error("Escribe un monto válido, solo con números.", "Monto no válido", "aviso")

    codigo, data = abrir(req)
    liga = data["liga_activa"]
    deporte = data["deporte_activo"]
    equipos = data["equipos_por_liga"].get(liga, [])

    if eleccion not in cuotas_para(deporte):
        return error("Elige un resultado válido para este deporte.", "Resultado no válido", "aviso")
    if not math.isfinite(monto) or monto < MONTO_MIN_PREDICCION:
        return error(f"El monto mínimo es $ {MONTO_MIN_PREDICCION:,.0f}.".replace(",", "."),
                     "Monto no válido", "aviso")
    if monto > data["balance_cop"]:
        return error("No tienes saldo suficiente. Recarga e intenta de nuevo.",
                     "Saldo insuficiente", "aviso")

    par = frozenset((home, away))
    if fase == "grupos":
        a = next((t for t in equipos if t["name"] == home), None)
        b = next((t for t in equipos if t["name"] == away), None)
        if a is None or b is None or a is b or a["group"] is None or a["group"] != b["group"]:
            return error("Ese partido no existe en el calendario.", "Partido no encontrado")
        if any(frozenset((m["home"], m["away"])) == par
               for m in data["matches"] if m["liga"] == liga and _es_grupos(m)):
            return error("Ese partido ya se jugó.", "Partido jugado", "aviso")
        grupo_pred = a["group"]
    else:
        if not any(x["fase"] == fase and x["home"] == home and x["away"] == away
                   and x["estado"] == "pendiente" for x in eliminatorias(data, liga)[0]):
            return error("Ese partido no está disponible para predecir.", "Partido no encontrado")
        grupo_pred = None
    if any(p["estado"] == "pendiente" and p["liga"] == liga and p.get("fase", "grupos") == fase
           and frozenset((p["home"], p["away"])) == par for p in data["predictions"]):
        return error("Ya tienes una predicción para este partido.", "Predicción repetida", "aviso")

    cuotas_p = cuotas_partido(deporte, liga, home, away, fase)
    if eleccion not in cuotas_p:
        return error("En las fases finales no hay empate: elige Local o Visita.",
                     "Resultado no válido", "aviso")
    cuota = cuotas_p[eleccion]
    data["balance_cop"] = round(data["balance_cop"] - monto, 2)
    data["predictions"].append({
        "id": max((p["id"] for p in data["predictions"]), default=0) + 1,
        "liga": liga,
        "deporte": deporte,
        "group": grupo_pred,
        "fase": fase,
        "home": home,
        "away": away,
        "eleccion": eleccion,
        "cuota": cuota,
        "monto": monto,
        "estado": "pendiente",
        "premio": 0,
        "marcador": None,
        "resultado": None,
    })
    return responder(codigo, data)


@app.route("/api/simulate_match", methods=["POST"])
def simulate_match():
    req = request.get_json(silent=True) or {}
    codigo, data = abrir(req)
    liga = data["liga_activa"]
    deporte = data["deporte_activo"]
    equipos = data["equipos_por_liga"].get(liga, [])

    por_grupo = {g: [t for t in equipos if t["group"] == g] for g in data["groups"]}
    grupos_validos = [g for g, miembros in por_grupo.items() if len(miembros) >= 2]
    if not grupos_validos:
        return error(f"Para simular partidos en {NOMBRE_LIGA.get(liga, 'esta liga')} necesitas "
                     "al menos 2 equipos en el mismo grupo. Toca un equipo de la lista y "
                     "asígnale un grupo.", "No se puede iniciar el torneo", "aviso")

    # Los partidos se juegan en el MISMO orden del calendario (grupo A, B, C...).
    jugados = {frozenset((m["home"], m["away"])) for m in data["matches"] if m["liga"] == liga}
    pendientes = [
        (g, a, b)
        for g, miembros in por_grupo.items()
        for i, a in enumerate(miembros)
        for b in miembros[i + 1:]
        if frozenset((a["name"], b["name"])) not in jugados
    ]
    fase = "grupos"
    if pendientes:
        grupo, local, visitante = pendientes[0]
    else:
        cruces, campeon = eliminatorias(data, liga)
        siguiente = next((x for x in cruces if x["estado"] == "pendiente"), None)
        if siguiente is None:
            if campeon:
                return error(f"El torneo terminó. ¡{campeon['name']} es el campeón!",
                             "Torneo terminado", "aviso")
            return error("Ya se jugaron todos los partidos de la fase de grupos.",
                         "Fase de grupos completa", "aviso")
        fase, grupo = siguiente["fase"], None
        local = next(t for t in equipos if t["name"] == siguiente["home"])
        visitante = next(t for t in equipos if t["name"] == siguiente["away"])
    goles_local, goles_visitante = generar_marcador_para(
        deporte, probs_partido(deporte, liga, local["name"], visitante["name"], fase))

    nuevo_id = max((m["id"] for m in data["matches"]), default=100) + 1
    data["matches"].insert(0, {
        "id": nuevo_id,
        "liga": liga,
        "group": grupo,
        "fase": fase,
        "deporte": deporte,
        "home": local["name"],
        "home_escudo": local["escudo"],
        "home_flag": local["flag"],
        "away": visitante["name"],
        "away_escudo": visitante["escudo"],
        "away_flag": visitante["flag"],
        "home_score": goles_local,
        "away_score": goles_visitante,
        "played": True,
    })
    resolver_predicciones(data, data["matches"][0])
    transmision = construir_transmision(deporte, local, visitante, goles_local, goles_visitante)
    return responder(codigo, data, live=transmision)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PUERTO, debug=True)