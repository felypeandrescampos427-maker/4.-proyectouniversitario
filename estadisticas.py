import random
import json
import os

ARCHIVO_STATS = "estadisticas_torneo.json"
ARCHIVO_PLANTILLAS = "plantillas.json"

class GestorEstadisticas:
    def __init__(self):
        self.plantillas = {}
        self.goleadores = {}      # Anotadores (Fútbol/Baloncesto/Béisbol)
        self.porteros = {}        # Arqueros / Lanzadores
        self.mvp_partidos = {}
        self.conteo_mvp = {}
        
        self.tarjetas_amarillas = {} 
        self.tarjetas_rojas = {}     
        self.lesionados = {}         

        self.cargar_estadisticas()
        self.inicializar_todas_las_plantillas()

    def guardar_estadisticas(self):
        datos = {
            "plantillas": self.plantillas,
            "goleadores": self.goleadores,
            "porteros": self.porteros,
            "mvp_partidos": self.mvp_partidos,
            "conteo_mvp": self.conteo_mvp,
            "tarjetas_amarillas": self.tarjetas_amarillas,
            "tarjetas_rojas": self.tarjetas_rojas,
            "lesionados": self.lesionados
        }
        with open(ARCHIVO_STATS, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)

    def cargar_estadisticas(self):
        if os.path.exists(ARCHIVO_STATS):
            try:
                with open(ARCHIVO_STATS, "r", encoding="utf-8") as f:
                    datos = json.load(f)
                    self.plantillas = datos.get("plantillas", {})
                    self.goleadores = datos.get("goleadores", {})
                    self.porteros = datos.get("porteros", {})
                    self.mvp_partidos = datos.get("mvp_partidos", {})
                    self.conteo_mvp = datos.get("conteo_mvp", {})
                    self.tarjetas_amarillas = datos.get("tarjetas_amarillas", {})
                    self.tarjetas_rojas = datos.get("tarjetas_rojas", {})
                    self.lesionados = datos.get("lesionados", {})
            except Exception:
                pass

    def inicializar_todas_las_plantillas(self):
        """Carga las plantillas reales desde el archivo JSON externo."""
        if not os.path.exists(ARCHIVO_PLANTILLAS):
            print(f"⚠️ No se encontró {ARCHIVO_PLANTILLAS}. Se usarán plantillas genéricas.")
            return

        try:
            with open(ARCHIVO_PLANTILLAS, "r", encoding="utf-8") as f:
                datos = json.load(f)
                equipos_json = datos.get("equipos", {})

            for eq, jugadores_lista in equipos_json.items():
                portero = "Portero Desconocido"
                defensas = []
                mediocampistas = []
                delanteros = []
                todos = []

                for jugador, pos in jugadores_lista:
                    nombre_completo = f"{jugador} ({pos})"
                    todos.append(nombre_completo)
                    
                    # Clasificación de posiciones por deporte
                    if pos in ["POR"]: # Fútbol
                        portero = nombre_completo
                    elif pos in ["DEF", "LAN"]: # Fútbol / Béisbol
                        defensas.append(nombre_completo)
                    elif pos in ["MED", "IF", "OF", "DH", "REC", "TOP", "JNG", "MID", "ADC", "SUP", "B", "E"]: # Medios / Infielder / eSports / Bases
                        mediocampistas.append(nombre_completo)
                    else: # DEL, A, AP, P (Delanteros / Pívots / Aleros)
                        delanteros.append(nombre_completo)

                self.plantillas[eq] = {
                    "portero": portero,
                    "defensas": defensas,
                    "mediocampistas": mediocampistas,
                    "delanteros": delanteros,
                    "todos": todos
                }

                por_clav = f"{portero} - {eq}"
                if por_clav not in self.porteros:
                    self.porteros[por_clav] = {"vallas_invictas": 0, "goles_recibidos": 0}
                    
        except Exception as e:
            print(f"❌ Error al leer {ARCHIVO_PLANTILLAS}: {e}")

    def generar_plantilla_equipo(self, nombre_equipo):
        if nombre_equipo in self.plantillas:
            return self.plantillas[nombre_equipo]

        p_nombre = "Jugador Base (ESTELAR)"
        plantilla = {
            "portero": p_nombre,
            "defensas": [f"Defensa {i} (DEF)" for i in range(1, 5)],
            "mediocampistas": [f"Mediocampista {i} (MED)" for i in range(1, 4)],
            "delanteros": [f"Delantero {i} (DEL)" for i in range(1, 4)],
            "todos": [p_nombre] + [f"Defensa {i} (DEF)" for i in range(1, 5)] + [f"Mediocampista {i} (MED)" for i in range(1, 4)] + [f"Delantero {i} (DEL)" for i in range(1, 4)]
        }
        self.plantillas[nombre_equipo] = plantilla
        return plantilla

    def calcular_probabilidades_partido(self, cuota_local, cuota_empate, cuota_visit):
        prob_l = 1 / cuota_local
        prob_e = 1 / cuota_empate
        prob_v = 1 / cuota_visit
        suma_prob = prob_l + prob_e + prob_v
        return {
            "local": round((prob_l / suma_prob) * 100, 1),
            "empate": round((prob_e / suma_prob) * 100, 1),
            "visitante": round((prob_v / suma_prob) * 100, 1)
        }

    def registrar_estadisticas_partido(self, partido_id, local, visit, gl, gv):
        p_local = self.generar_plantilla_equipo(local)
        p_visit = self.generar_plantilla_equipo(visit)

        # Anotaciones
        for _ in range(gl):
            anotador = random.choice(p_local["delanteros"] + p_local["mediocampistas"])
            clave = f"{anotador} ({local})"
            self.goleadores[clave] = self.goleadores.get(clave, 0) + 1

        for _ in range(gv):
            anotador = random.choice(p_visit["delanteros"] + p_visit["mediocampistas"])
            clave = f"{anotador} ({visit})"
            self.goleadores[clave] = self.goleadores.get(clave, 0) + 1

        # Porteros
        por_loc = f"{p_local['portero']} - {local}"
        por_vis = f"{p_visit['portero']} - {visit}"

        if por_loc not in self.porteros:
            self.porteros[por_loc] = {"vallas_invictas": 0, "goles_recibidos": 0}
        if por_vis not in self.porteros:
            self.porteros[por_vis] = {"vallas_invictas": 0, "goles_recibidos": 0}

        self.porteros[por_loc]["goles_recibidos"] += gv
        if gv == 0:
            self.porteros[por_loc]["vallas_invictas"] += 1

        self.porteros[por_vis]["goles_recibidos"] += gl
        if gl == 0:
            self.porteros[por_vis]["vallas_invictas"] += 1

        # Tarjetas y Lesiones (Simulación rápida)
        todos_jugadores = p_local["todos"] + p_visit["todos"]
        num_amarillas = random.randint(1, 3)
        for _ in range(num_amarillas):
            j_tarjeta = random.choice(todos_jugadores)
            equipo_j = local if j_tarjeta in p_local["todos"] else visit
            clave_t = f"{j_tarjeta} ({equipo_j})"
            self.tarjetas_amarillas[clave_t] = self.tarjetas_amarillas.get(clave_t, 0) + 1

        if random.random() < 0.20:
            j_roja = random.choice(todos_jugadores)
            equipo_r = local if j_roja in p_local["todos"] else visit
            clave_r = f"{j_roja} ({equipo_r})"
            self.tarjetas_rojas[clave_r] = self.tarjetas_rojas.get(clave_r, 0) + 1

        if random.random() < 0.15:
            j_lesionado = random.choice(todos_jugadores)
            equipo_l = local if j_lesionado in p_local["todos"] else visit
            clave_les = f"{j_lesionado} ({equipo_l})"
            self.lesionados[clave_les] = random.randint(1, 3)

        # MVP
        eq_destacado = p_local if gl >= gv else p_visit
        nom_equipo = local if gl >= gv else visit
        mvp = f"{random.choice(eq_destacado['todos'])} ({nom_equipo})"
        self.mvp_partidos[str(partido_id)] = mvp
        self.conteo_mvp[mvp] = self.conteo_mvp.get(mvp, 0) + 1

        self.guardar_estadisticas()

    def obtener_top_goleadores(self, top=5):
        lista = [{"jugador": k, "goles": v} for k, v in self.goleadores.items()]
        return sorted(lista, key=lambda x: x["goles"], reverse=True)[:top]

    def obtener_mejores_porteros(self, top=5):
        lista = [
            {"portero": k, "vallas_invictas": v["vallas_invictas"], "goles_recibidos": v["goles_recibidos"]} 
            for k, v in self.porteros.items()
        ]
        return sorted(lista, key=lambda x: (x["vallas_invictas"], -x["goles_recibidos"]), reverse=True)[:top]

    def calcular_trofeos_torneo(self):
        top_goleador = "Por definir"
        if self.goleadores:
            ganador_goles = max(self.goleadores.items(), key=lambda x: x[1])
            top_goleador = f"{ganador_goles[0]} ({ganador_goles[1]} tantos)"

        top_portero = "Por definir"
        if self.porteros:
            ganador_por = max(self.porteros.items(), key=lambda x: (x[1]["vallas_invictas"], -x[1]["goles_recibidos"]))
            top_portero = f"{ganador_por[0]} ({ganador_por[1]['vallas_invictas']} vallas invictas)"

        top_mvp = "Por definir"
        if self.conteo_mvp:
            ganador_mvp = max(self.conteo_mvp.items(), key=lambda x: x[1])
            top_mvp = f"{ganador_mvp[0]} ({ganador_mvp[1]} premios MVP)"

        return {
            "balon_de_oro": top_mvp,
            "bota_de_oro": top_goleador,
            "guante_de_oro": top_portero
        }