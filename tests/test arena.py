"""Pruebas automáticas de Arena Legends: cuotas, predicciones, candado, logros, roja, Mundial, administrador y PWA.
Se ejecutan con:  pip install pytest   y luego   pytest -v"""
import random
import threading
import time

from conftest import asignar_grupos


# ---------------------------------------------------------------- cuotas
def test_cuotas_cubren_el_margen_de_la_casa(m):
    """La suma de 1/cuota debe ser 1/0,95 (el 5 % de margen), es decir, las cuotas no son inventadas."""
    cuotas = m.cuotas_para("Fútbol")
    assert abs(sum(1 / c for c in cuotas.values()) - 1 / m.MARGEN_CUOTAS) < 0.02


def test_el_favorito_paga_menos(m):
    cuotas = m.cuotas_partido("Fútbol", "PD", "Real Madrid", "Racing de Santander")
    assert cuotas["local"] < cuotas["empate"] < cuotas["visita"]


def test_cuotas_fase_final_sin_empate(m):
    cuotas = m.cuotas_partido("Fútbol", "PD", "Real Madrid", "FC Barcelona", fase="cuartos")
    assert "empate" not in cuotas


# ---------------------------------------------------------------- roja
def test_roja_baja_la_probabilidad_del_expulsado(m):
    base = {"local": 0.40, "empate": 0.20, "visita": 0.40}
    ajustada = m.ajustar_por_roja(base, "home")
    assert abs(sum(ajustada.values()) - 1) < 1e-9
    assert ajustada["local"] < base["local"] and ajustada["visita"] > base["visita"]


def test_la_roja_aparece_en_la_transmision(m):
    local, visita = m.EQUIPOS_POR_LIGA["PD"][0], m.EQUIPOS_POR_LIGA["PD"][1]
    random.seed(7)
    trans = m.construir_transmision("Fútbol", local, visita, 1, 0, roja="away")
    rojas = [e for e in trans["eventos"] if e["tipo"] == "roja"]
    assert len(rojas) == 1 and rojas[0]["lado"] == "away"
    sin = m.construir_transmision("Fútbol", local, visita, 1, 0)
    assert not [e for e in sin["eventos"] if e["tipo"] == "roja"]


# ---------------------------------------------------------------- predicciones
def test_prediccion_descuenta_y_rechaza_saldo_insuficiente(m, jugador):
    asignar_grupos(jugador, "PD")
    estado = jugador("/api/load", liga="PD")["state"]
    a, b = [t for t in estado["equipos_por_liga"]["PD"] if t["group"] == "A"][:2]
    r = jugador("/api/predict", liga="PD", home=a["name"], away=b["name"], eleccion="local", monto=10_000)
    assert r["status"] == "success" and r["state"]["balance_cop"] == m.SALDO_INICIAL - 10_000 + m.PREMIOS_LOGRO["primera_prediccion"]   # la primera predicción da un logro con premio
    r = jugador("/api/predict", liga="PD", home=a["name"], away=b["name"], eleccion="local", monto=m.SALDO_INICIAL * 10)
    assert r["status"] == "error"


def test_resolver_predicciones_paga_monto_por_cuota(m):
    data = m.estado_inicial()
    data["predictions"] = [
        {"id": 1, "liga": "PD", "home": "A", "away": "B", "eleccion": "local", "cuota": 2.0, "monto": 5000, "estado": "pendiente"},
        {"id": 2, "liga": "PD", "home": "C", "away": "D", "eleccion": "local", "cuota": 3.0, "monto": 1000, "estado": "pendiente"},
    ]
    saldo = data["balance_cop"]
    m.resolver_predicciones(data, {"liga": "PD", "home": "A", "away": "B", "home_score": 2, "away_score": 0})
    m.resolver_predicciones(data, {"liga": "PD", "home": "C", "away": "D", "home_score": 0, "away_score": 1})
    assert data["predictions"][0]["estado"] == "ganada" and data["predictions"][1]["estado"] == "perdida"
    assert data["balance_cop"] == saldo + 10_000


# ---------------------------------------------------------------- candado
def test_candado_hace_esperar_al_segundo(m):
    """Dos pestañas a la vez: la segunda espera a que la primera termine (no se pisan los datos)."""
    tiempos = {}

    def primero():
        with m.app.test_request_context():
            m._tomar_candado("arena:prueba")
            tiempos["tomado"] = time.time()
            time.sleep(0.6)
        tiempos["soltado"] = time.time()

    def segundo():
        time.sleep(0.15)
        with m.app.test_request_context():
            m._tomar_candado("arena:prueba")
            tiempos["segundo"] = time.time()

    hilos = [threading.Thread(target=primero), threading.Thread(target=segundo)]
    [h.start() for h in hilos]
    [h.join() for h in hilos]
    assert tiempos["segundo"] >= tiempos["soltado"] - 0.02


# ---------------------------------------------------------------- logros
def _pred(i, estado, cuota=2.0):
    return {"id": i, "liga": "PD", "home": "A", "away": "B", "eleccion": "local", "cuota": cuota, "monto": 1000, "estado": estado}


def test_logros_rachas_y_cuota_alta(m):
    data = m.estado_inicial()
    data["predictions"] = [_pred(1, "ganada"), _pred(2, "ganada"), _pred(3, "ganada", 3.5), _pred(4, "perdida")]
    lista, rachas = m.calcular_logros(data)
    ok = {x["id"] for x in lista if x["ok"]}
    assert {"primera_prediccion", "primer_acierto", "racha_3", "cuota_alta"} <= ok
    assert "racha_5" not in ok and rachas["mejor_racha"] == 3 and rachas["racha_actual"] == 0


def test_un_logro_conseguido_no_se_pierde(m):
    data = m.estado_inicial()
    data["predictions"] = [_pred(1, "ganada")]
    m.actualizar_logros(data)
    data["predictions"] = []        # aunque cambie el progreso, el logro ya ganado se conserva
    assert "primer_acierto" in {x["id"] for x in m.calcular_logros(data)[0] if x["ok"]}


# ---------------------------------------------------------------- Mundial
def test_mundial_es_un_torneo_completo_de_20_selecciones(m, jugador):
    assert len(m.EQUIPOS_POR_LIGA["MUNDIAL"]) == 20 and m.DEPORTE_DE_LIGA["MUNDIAL"] == "Fútbol"
    asignar_grupos(jugador, "MUNDIAL")
    r = jugador("/api/simulate_all", liga="MUNDIAL")
    assert r["status"] == "success" and r["state"]["campeon"] in {t["name"] for t in m.EQUIPOS_POR_LIGA["MUNDIAL"]}
    assert any(x["id"] == "mundialista" and x["ok"] for x in r["state"]["logros"])


# ---------------------------------------------------------------- administrador
def test_solo_el_administrador_entra_al_panel(m, cliente, jugador):
    r = cliente.post("/api/admin/usuarios", json={"sesion": jugador.sesion})
    assert r.status_code == 403
    r = cliente.post("/api/admin/reiniciar", json={"sesion": jugador.sesion, "correo": jugador.correo, "alcance": "todo"})
    assert r.status_code == 403
    assert cliente.post("/api/admin/usuarios", json={"sesion": "x" * 40}).status_code == 401


def test_admin_lista_y_reinicia_con_su_correo(m, cliente, jugador):
    jugador("/api/load")                                  # la cuenta existe y tiene progreso
    asignar_grupos(jugador, "PD")
    jugador("/api/simulate_match", liga="PD")
    m._guardar_cuenta(jugador.correo, {"correo": jugador.correo, "nombre": "Ana", "apellido": "Prueba", "verificada": True})
    sesion_admin = m.crear_sesion("admin@prueba.com")
    assert cliente.post("/api/auth/yo", json={"sesion": sesion_admin}).get_json()["admin"] is True
    assert cliente.post("/api/auth/yo", json={"sesion": jugador.sesion}).get_json()["admin"] is False
    lista = cliente.post("/api/admin/usuarios", json={"sesion": sesion_admin}).get_json()
    assert jugador.correo in [u["correo"] for u in lista["usuarios"]]
    r = cliente.post("/api/admin/reiniciar", json={"sesion": sesion_admin, "correo": jugador.correo, "alcance": "liga", "liga": "PD"})
    assert r.get_json()["status"] == "success"
    estado = jugador("/api/load", liga="PD")["state"]
    assert estado["matches"] == []


# ---------------------------------------------------------------- app instalable y sesión
def test_pwa_manifiesto_y_service_worker(cliente):
    manifiesto = cliente.get("/manifest.webmanifest").get_json()
    assert manifiesto["display"] == "standalone" and len(manifiesto["icons"]) >= 2
    sw = cliente.get("/sw.js")
    assert sw.status_code == 200 and "/api/" in sw.get_data(as_text=True)   # el service worker nunca guarda /api


def test_sin_sesion_valida_no_se_entra(cliente):
    assert cliente.post("/api/load", json={"sesion": "no-sirve"}).status_code == 401


# ---------------------------------------------------------------- premio por logro
def test_cada_logro_paga_su_premio_una_sola_vez(m):
    data = m.estado_inicial()
    data["predictions"] = [_pred(1, "ganada")]
    saldo = data["balance_cop"]
    m.actualizar_logros(data)
    esperado = m.PREMIOS_LOGRO["primera_prediccion"] + m.PREMIOS_LOGRO["primer_acierto"]
    assert data["balance_cop"] == saldo + esperado
    assert [x["detalle"] for x in data["movimientos"] if x["tipo"] == "premio"] == ["Logro: Ojo clínico", "Logro: Primera predicción"]
    m.actualizar_logros(data)           # volver a calcular NO vuelve a pagar
    assert data["balance_cop"] == saldo + esperado


def test_el_premio_no_se_repite_al_perder_el_progreso_de_la_liga(m):
    data = m.estado_inicial()
    data["predictions"] = [_pred(1, "ganada")]
    m.actualizar_logros(data)
    saldo = data["balance_cop"]
    m.reiniciar_liga(data, "PD")        # reiniciar el torneo borra predicciones, pero el logro ya se cobró
    data["predictions"] = [_pred(2, "ganada")]
    m.actualizar_logros(data)
    assert data["balance_cop"] == saldo