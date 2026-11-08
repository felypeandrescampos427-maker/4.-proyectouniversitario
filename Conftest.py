"""Configuración de las pruebas: usa el servidor PC con una carpeta temporal (nunca toca tu progreso real)."""
import importlib
import os
import sys
import tempfile

import pytest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)
for v in ("UPSTASH_REDIS_REST_URL", "UPSTASH_REDIS_REST_TOKEN", "BREVO_API_KEY", "EMAIL_REMITENTE", "EMAIL_AVISOS"):
    os.environ.pop(v, None)
os.environ["ADMIN_EMAIL"] = "admin@prueba.com"


@pytest.fixture(scope="session")
def m():
    modulo = importlib.import_module("torneo_app")
    modulo.CARPETA_LOCAL = tempfile.mkdtemp(prefix="arena_tests_")
    modulo.app.config["TESTING"] = True
    return modulo


@pytest.fixture()
def cliente(m):
    return m.app.test_client()


@pytest.fixture()
def jugador(m, cliente):
    """Una cuenta nueva con sesión abierta: devuelve una función post(ruta, **datos)."""
    correo = f"jugador_{os.urandom(4).hex()}@prueba.com"
    sesion = m.crear_sesion(correo)

    def post(ruta, **datos):
        return cliente.post(ruta, json={"sesion": sesion, **datos}).get_json()
    post.sesion, post.correo = sesion, correo
    return post


def asignar_grupos(post, liga):
    """Reparte los equipos de la liga en grupos de 4 (A a E), como haría el jugador."""
    estado = post("/api/load", liga=liga)["state"]
    for i, t in enumerate(estado["equipos_por_liga"][liga]):
        post("/api/assign_group", liga=liga, team_id=t["id"], group="ABCDE"[i // 4])