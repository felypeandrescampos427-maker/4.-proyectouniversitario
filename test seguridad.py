"""Pruebas de seguridad: entradas raras, límites de uso, cabeceras, sesiones y errores."""
import os

import pytest


def _post(cliente, ruta, cuerpo, ip="10.0.0.1"):
    return cliente.post(ruta, data=cuerpo, content_type="application/json",
                        headers={"X-Forwarded-For": ip})


@pytest.mark.parametrize("ruta", ["/api/auth/login", "/api/auth/registro", "/api/auth/olvide", "/api/load"])
@pytest.mark.parametrize("cuerpo", ["[1]", '"x"', "123", "null", "{no es json"])
def test_cuerpo_raro_no_tumba_el_servidor(cliente, ruta, cuerpo):
    r = _post(cliente, ruta, cuerpo, ip="10.1.%d.%d" % (hash(ruta) % 250, hash(cuerpo) % 250))
    assert r.status_code < 500, r.get_data(as_text=True)


@pytest.mark.parametrize("ruta,cuerpo", [
    ("/api/set_active_league", {"deporte": [], "codigo_liga": {}}),
    ("/api/plantillas", {"liga": []}),
    ("/api/predict", {"home": [], "away": {}, "eleccion": [], "monto": 1000}),
    ("/api/predict", {"home": "A", "away": "B", "eleccion": "local", "monto": 1000, "fase": []}),
    ("/api/assign_group", {"team_id": 1, "group": []}),
    ("/api/load", {"liga": []}),
    ("/api/deposit", {"monto": []}),
    ("/api/admin/reiniciar", {"correo": "x@y.co", "alcance": "liga", "liga": []}),
])
def test_tipos_inesperados_dan_error_controlado(jugador, ruta, cuerpo):
    from flask import json  # noqa: F401
    resp = jugador(ruta, **cuerpo)
    assert resp is not None and resp.get("status") in ("error", "success")


def test_ip_no_se_puede_falsificar_con_el_primer_valor(m, cliente):
    with m.app.test_request_context("/", headers={"X-Forwarded-For": "1.2.3.4, 9.9.9.9"}):
        assert m._ip() == "9.9.9.9"
    with m.app.test_request_context("/", headers={"X-Forwarded-For": "1.2.3.4"}):
        assert m._ip() == "1.2.3.4"


def test_limite_por_ip(m, cliente, monkeypatch):
    monkeypatch.setattr(m, "LIMITE_IP_POR_MIN", 3)
    ip = "10.9." + os.urandom(1).hex().replace("a", "1")[:2] + ".7"
    codigos = [_post(cliente, "/api/auth/logout", "{}", ip=ip).status_code for _ in range(5)]
    assert codigos[:3] == [200, 200, 200] and codigos[3:] == [429, 429]


def test_limite_por_usuario(m, cliente, jugador, monkeypatch):
    monkeypatch.setattr(m, "LIMITE_USUARIO_POR_MIN", 2)
    estados = [cliente.post("/api/auth/yo", json={"sesion": jugador.sesion},
                            headers={"X-Forwarded-For": "10.8.%d.1" % i}).status_code for i in range(4)]
    assert estados[:2] == [200, 200] and estados[2:] == [429, 429]


def test_cabeceras_de_seguridad(cliente):
    r = cliente.get("/api/health")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in (r.headers.get("Content-Security-Policy")
                                       or r.headers.get("Content-Security-Policy-Report-Only"))
    assert "Access-Control-Allow-Origin" not in r.headers      # CORS cerrado: solo el mismo origen


def test_health_publico_no_revela_configuracion(m, cliente, monkeypatch):
    assert cliente.get("/api/health").get_json() == {"funciona": True}
    monkeypatch.setattr(m, "HEALTH_TOKEN", "secreto-de-prueba")
    assert cliente.get("/api/health", headers={"X-Health-Token": "mal"}).get_json() == {"funciona": True}
    detalle = cliente.get("/api/health", headers={"X-Health-Token": "secreto-de-prueba"}).get_json()
    assert "almacenamiento" in detalle


def test_cambiar_la_clave_cierra_todas_las_sesiones(m):
    correo = "sesiones_%s@prueba.com" % os.urandom(3).hex()
    tokens = [m.crear_sesion(correo) for _ in range(3)]
    for t in tokens:
        m.codigo_de_sesion(t)
    m.cerrar_todas_las_sesiones(correo)
    for t in tokens:
        with pytest.raises(m.SesionInvalida):
            m.codigo_de_sesion(t)


def test_maximo_de_sesiones_abiertas(m):
    correo = "muchas_%s@prueba.com" % os.urandom(3).hex()
    tokens = [m.crear_sesion(correo) for _ in range(m.MAX_SESIONES_POR_CUENTA + 2)]
    with pytest.raises(m.SesionInvalida):
        m.codigo_de_sesion(tokens[0])
    m.codigo_de_sesion(tokens[-1])


def test_error_inesperado_responde_json_sin_detalles(m, cliente, jugador, monkeypatch):
    def roto():
        raise RuntimeError("DETALLE-INTERNO-SECRETO")
    monkeypatch.setattr(m, "estado_inicial", roto)
    r = cliente.post("/api/load", json={"sesion": jugador.sesion})
    assert r.status_code == 500
    assert "DETALLE-INTERNO-SECRETO" not in r.get_data(as_text=True)
    assert r.get_json()["status"] == "error"


def test_peticion_demasiado_grande_se_rechaza(cliente):
    r = _post(cliente, "/api/auth/login", '{"clave":"%s"}' % ("a" * 70000), ip="10.7.7.7")
    assert r.status_code == 413