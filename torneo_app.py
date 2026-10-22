"""Arena Legends - servidor Flask (versión PC)."""
import copy
import json
import math
import os
import random

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

DATA_FILE = "progreso_torneo.json"
PLANTILLA = "index.html"
PUERTO = 5000
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

NOMBRE_LIGA = {
    liga["codigo"]: liga["nombre"]
    for ligas in LIGAS_DISPONIBLES.values()
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
    "laequidad": "equidad",
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
        ("La Equidad", "laequidad.png"),
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
    ]),
    "MLB": _equipos("⚾", 401, [
        ("New York Yankees", "yankees.png"),
        ("Los Angeles Dodgers", "dodgers.png"),
    ]),
    "lol": _equipos("🎮", 501, [
        ("T1", "t1.png"),
        ("Gen.G", "geng.png"),
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
}


# ---------------------------------------------------------------------------
# Persistencia
# ---------------------------------------------------------------------------
def estado_inicial():
    return copy.deepcopy(DEFAULT_STATE)


def normalizar(data):
    """Pone al día un archivo guardado: la configuración manda el código,
    pero se conservan el saldo, los grupos asignados y los partidos jugados."""
    base = estado_inicial()
    data.pop("api_keys", None)  # las claves nunca deben viajar al navegador
    data.pop("logs", None)

    for clave in ("ligas", "groups", "max_group_capacity"):
        data[clave] = base[clave]
    for clave in ("balance_cop", "deporte_activo", "liga_activa", "matches"):
        data.setdefault(clave, base[clave])

    guardados_por_liga = data.get("equipos_por_liga", {})
    data["equipos_por_liga"] = {}
    for codigo, equipos_base in base["equipos_por_liga"].items():
        guardados = {t["id"]: t for t in guardados_por_liga.get(codigo, [])}
        data["equipos_por_liga"][codigo] = [
            {**equipo, "group": guardados.get(equipo["id"], {}).get("group")}
            for equipo in equipos_base
        ]

    data["matches"] = [m for m in data["matches"] if "liga" in m]
    # Los partidos guardados pueden traer nombres de escudo antiguos: se actualizan.
    for m in data["matches"]:
        m["home_escudo"] = resolver_escudo(m.get("home_escudo", ""))
        m["away_escudo"] = resolver_escudo(m.get("away_escudo", ""))
    return data


def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return normalizar(json.load(f))
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            pass
    data = estado_inicial()
    save_data(data)
    return data


# ---------------------------------------------------------------------------
# Respuestas
# ---------------------------------------------------------------------------
def ok(data, **extra):
    return jsonify({"status": "success", "state": data, **extra})


def error(mensaje, titulo="Ups, algo salió mal", tipo="error", codigo=400):
    """tipo: 'error' o 'aviso'. El navegador lo usa para elegir el color del mensaje."""
    return jsonify({"status": "error", "tipo": tipo, "titulo": titulo, "message": mensaje}), codigo


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
# Rutas
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return render_template(PLANTILLA, state=load_data())


@app.route("/api/get_state", methods=["GET"])
def get_state():
    return jsonify(load_data())


@app.route("/api/reset", methods=["POST"])
def reset_state():
    """Reinicia grupos y partidos, pero conserva el saldo del usuario."""
    saldo = load_data()["balance_cop"]
    data = estado_inicial()
    data["balance_cop"] = saldo
    save_data(data)
    return ok(data)


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

    data = load_data()
    data["balance_cop"] = round(data["balance_cop"] + monto, 2)
    save_data(data)
    return ok(data)


@app.route("/api/set_active_league", methods=["POST"])
def set_active_league():
    req = request.get_json(silent=True) or {}
    deporte = req.get("deporte")
    codigo = req.get("codigo_liga")

    codigos_validos = {liga["codigo"] for liga in LIGAS_DISPONIBLES.get(deporte, [])}
    if codigo not in codigos_validos:
        return error("Esa liga no existe para el deporte elegido.", "Liga no encontrada")

    data = load_data()
    data["deporte_activo"] = deporte
    data["liga_activa"] = codigo
    save_data(data)
    return ok(data)


@app.route("/api/assign_group", methods=["POST"])
def assign_group():
    req = request.get_json(silent=True) or {}
    team_id = req.get("team_id")
    grupo = req.get("group")

    data = load_data()
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
    save_data(data)
    return ok(data)


@app.route("/api/simulate_match", methods=["POST"])
def simulate_match():
    data = load_data()
    liga = data["liga_activa"]
    deporte = data["deporte_activo"]
    equipos = data["equipos_por_liga"].get(liga, [])

    por_grupo = {g: [t for t in equipos if t["group"] == g] for g in data["groups"]}
    grupos_validos = [g for g, miembros in por_grupo.items() if len(miembros) >= 2]
    if not grupos_validos:
        return error(f"Para simular partidos en {NOMBRE_LIGA.get(liga, 'esta liga')} necesitas "
                     "al menos 2 equipos en el mismo grupo. Toca un equipo de la lista y "
                     "asígnale un grupo.", "No se puede iniciar el torneo", "aviso")

    # Solo se simulan cruces que aún no se han jugado, para que cuadre con el calendario.
    jugados = {frozenset((m["home"], m["away"])) for m in data["matches"] if m["liga"] == liga}
    pendientes = [
        (g, a, b)
        for g, miembros in por_grupo.items()
        for i, a in enumerate(miembros)
        for b in miembros[i + 1:]
        if frozenset((a["name"], b["name"])) not in jugados
    ]
    if not pendientes:
        return error("Ya se jugaron todos los partidos de la fase de grupos.",
                     "Fase de grupos completa", "aviso")

    grupo, local, visitante = random.choice(pendientes)
    goles_local, goles_visitante = generar_marcador(deporte)

    nuevo_id = max((m["id"] for m in data["matches"]), default=100) + 1
    data["matches"].insert(0, {
        "id": nuevo_id,
        "liga": liga,
        "group": grupo,
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
    save_data(data)
    transmision = construir_transmision(deporte, local, visitante, goles_local, goles_visitante)
    return ok(data, live=transmision)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PUERTO, debug=True)
