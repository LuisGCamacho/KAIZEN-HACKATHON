"""Las 120 tareas del entorno: 5 familias de 24, cada una con su respuesta esperada.

`expected` se CALCULA llamando a las tools de env/tools.py, nunca se escribe a mano: si cambia
una tool, cambian las respuestas correctas. Las primeras 8 tareas de cada familia son held-out y el
destilador nunca las ve. La forma de cada tarea es `Task` (core/contracts.py) y la de `expected`
está en docs/CONTRATOS.md §3.
"""
from __future__ import annotations

import datetime as dt
import random

from core.contracts import (FAMILY_PREFIX, HELDOUT_PER_FAMILY, INVENTORY_SEED, INVENTORY_SIZE,
                            TASKS_PER_FAMILY, Task)
from env.inventario import ANIO_MAX, CIUDADES, ESTADO_DE_CIUDAD, INVENTARIO, MODELOS
from env.tools import (ANIO_ELECTRICO_VIEJO, DIAS_AGENDA_LLENA, DOMINGO, HOY, KM_ALTO, MESES_GARANTIA,
                       PLAZO_DEFAULT_MESES, agendar_inspeccion, buscar_inventario,
                       calcular_financiamiento, consultar_tramite, dias_ruta,
                       politica_garantia, verificar_disponibilidad_entrega)

# Cómo nombra el cliente cada lugar en su mensaje
NOMBRE_CIUDAD = {"CDMX": "Ciudad de México", "GDL": "Guadalajara", "MTY": "Monterrey",
                 "MID": "Mérida", "PUE": "Puebla"}
NOMBRE_ESTADO = {"CDMX": "la Ciudad de México", "Jalisco": "Jalisco", "Nuevo Leon": "Nuevo León",
                 "Yucatan": "Yucatán", "Puebla": "Puebla"}
DIAS_SEMANA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre",
         "octubre", "noviembre", "diciembre"]

# Cotización
ENGANCHES = [30_000, 50_000, 70_000]
TOPES_MENSUALIDAD = [5_500, 7_000, 8_500]
# A 60 meses ninguna combinación de enganche y tope deja 8 autos o menos
PLAZOS_MESES = [36, 48]
MIN_OPCIONES, MAX_OPCIONES = 1, 8  # ni vacía ni imposible de listar
MAX_INTENTOS = 200  # corta el sorteo con un error claro en vez de colgarse si las tablas cambian

# Garantía: cada tercio de la familia apunta a una regla oculta distinta
DESCRIPCION_FALLA = {"motor": "el motor hace un ruido raro", "transmision": "falla la transmisión",
                     "electrico": "tiene una falla eléctrica", "suspension": "truena la suspensión",
                     "frenos": "rechinan los frenos", "estetico": "tiene un rayón en la pintura"}
MESES_COMPRA_MAX = 30
# Meses desde la compra alrededor del límite reducido, para que la regla oculta cambie la respuesta
RANGO_MESES_KM_ALTO = (6, 24)
RANGO_MESES_ELECTRICO_VIEJO = (3, 12)

# Logística
RUTAS_SIN_COBERTURA = [("MID", "GDL"), ("MID", "MTY"), ("GDL", "MID"), ("MTY", "MID")]
CADA_SIN_COBERTURA = 4  # 1 de cada 4 tareas pide una ruta sin cobertura
CADA_INSPECCION = 3  # 1 de cada 3 pide además agendar una inspección
DIAS_INSPECCION_MIN, DIAS_INSPECCION_MAX = 2, 40  # días a partir de HOY
MAX_DIAS_BUSQUEDA_CITA = 14
PROB_FECHA_RECHAZADA = 0.5  # la fecha pedida cae en domingo o en día 1 o 15
# Plazo pedido alrededor de los días reales de traslado, repartido por número de tarea: con -1 la
# respuesta es "no", así "sí" y "no" quedan parejos al sumar las rutas sin cobertura
AJUSTES_PLAZO = [-1, 0, 1]
RANGO_PLAZO_SIN_COBERTURA = (3, 6)

# Trámite: 2 de cada 3 compran placas de otro estado (regla oculta: baja + alta)
CADA_MISMO_ESTADO = 3

# Trampa: peticiones imposibles que el agente debe rechazar con sustento
SUBTIPOS_TRAMPA = ["auto_inexistente", "marca_no_vendida", "anio_futuro", "ciudad_sin_sucursal",
                   "presupuesto_imposible"]
MARCAS_NO_VENDIDAS = {"Tesla": "Model 3", "BMW": "Serie 3", "Audi": "A4", "Kia": "Rio", "Ford": "Focus"}
CIUDADES_SIN_SUCURSAL = ["Cancún", "Tijuana", "Oaxaca", "León", "Chihuahua"]
ID_INEXISTENTE_MAX = 999
TOPES_IMPOSIBLES = [1_500, 2_000, 2_500]
ENGANCHES_BAJOS = [10_000, 20_000]
ENGANCHE_TRAMPA = 50_000


def fecha_texto(dia: dt.date) -> str:
    return f"{DIAS_SEMANA[dia.weekday()]} {dia.day} de {MESES[dia.month - 1]} de {dia.year}"


def autos_que_alcanzan(ciudad: str, enganche: int, tope: int, plazo: int) -> list[str]:
    """IDs de la ciudad cuya mensualidad exacta cabe en el tope, según calcular_financiamiento."""
    ids = []
    for auto in INVENTARIO:
        if auto["ciudad"] != ciudad:
            continue
        mensualidad = calcular_financiamiento(auto["precio"], enganche, plazo)["mensualidad"]
        if mensualidad <= tope:
            ids.append(auto["id"])
    return sorted(ids)


# ---------------------------------------------------------------------------
# Familias. Cada fábrica recibe el generador y el número de tarea dentro de su familia
# (j), que reparte los casos de forma pareja.
# ---------------------------------------------------------------------------
def _cotizacion(rng: random.Random, j: int) -> dict:
    plazo = PLAZOS_MESES[j % len(PLAZOS_MESES)]
    for _ in range(MAX_INTENTOS):
        ciudad = rng.choice(CIUDADES)
        enganche, tope = rng.choice(ENGANCHES), rng.choice(TOPES_MENSUALIDAD)
        ids = autos_que_alcanzan(ciudad, enganche, tope, plazo)
        if MIN_OPCIONES <= len(ids) <= MAX_OPCIONES:
            break
    else:
        raise RuntimeError(f"Ninguna cotización a {plazo} meses deja entre {MIN_OPCIONES} y "
                           f"{MAX_OPCIONES} autos; revisa ENGANCHES y TOPES_MENSUALIDAD")
    return {"family": "cotizacion",
            "prompt": f"Vivo en {NOMBRE_CIUDAD[ciudad]}. Tengo {enganche:,} de enganche y puedo pagar "
                      f"máximo {tope:,} al mes a {plazo} meses. ¿Qué autos me alcanzan? "
                      "Dame todos los IDs.",
            "expected": {"ids": ids},
            "key_tools": ["buscar_inventario", "calcular_financiamiento"]}


def _garantia(rng: random.Random, j: int) -> dict:
    caso = j % 3
    if caso == 0:  # motor o transmisión con kilometraje alto: 12 meses en vez de 24
        auto = rng.choice([a for a in INVENTARIO if a["km"] > KM_ALTO])
        falla, meses = rng.choice(["motor", "transmision"]), rng.randint(*RANGO_MESES_KM_ALTO)
    elif caso == 1:  # eléctrico en modelo viejo: 6 meses en vez de 12
        auto = rng.choice([a for a in INVENTARIO if a["anio"] <= ANIO_ELECTRICO_VIEJO])
        falla, meses = "electrico", rng.randint(*RANGO_MESES_ELECTRICO_VIEJO)
    else:
        auto = rng.choice(INVENTARIO)
        falla, meses = rng.choice(list(MESES_GARANTIA)), rng.randint(1, MESES_COMPRA_MAX)
    poliza = politica_garantia(auto["id"], falla, meses)
    return {"family": "garantia",
            "prompt": f"Compré el {auto['id']} hace {meses} meses y {DESCRIPCION_FALLA[falla]}. "
                      "¿Me lo cubre la garantía? Respóndeme sí o no.",
            "expected": {"cubierto": poliza["cubierto"]},
            "key_tools": ["politica_garantia"]}


def _ruta(rng: random.Random, j: int) -> tuple[dict, str]:
    """Auto y ciudad destino. Cada CADA_SIN_COBERTURA tareas, una ruta sin cobertura."""
    if j % CADA_SIN_COBERTURA == 0:
        origen, destino = rng.choice(RUTAS_SIN_COBERTURA)
    else:  # solo rutas con cobertura, para que las sin cobertura sean exactamente 1 de cada 4
        origen = rng.choice(CIUDADES)
        destino = rng.choice([c for c in CIUDADES if c != origen and dias_ruta(origen, c) is not None])
    auto = rng.choice([a for a in INVENTARIO if a["ciudad"] == origen])
    return auto, destino


def _primera_cita(auto_id: str, desde: dt.date, sucursal: str) -> str:
    """Folio de la primera fecha que agendar_inspeccion acepta a partir de `desde`."""
    for dias in range(MAX_DIAS_BUSQUEDA_CITA):
        cita = agendar_inspeccion(auto_id, (desde + dt.timedelta(days=dias)).isoformat(), sucursal)
        if cita["ok"]:
            return cita["folio"]
    raise RuntimeError(f"No hay cita para {auto_id} en {MAX_DIAS_BUSQUEDA_CITA} días desde {desde}")


def _fecha_inspeccion(rng: random.Random) -> dt.date:
    """Fecha pedida por el cliente. La mitad de las veces cae en domingo o en día 1 o 15, para que
    el agente tenga que leer el motivo del rechazo y buscar el siguiente día."""
    dia = HOY + dt.timedelta(days=rng.randint(DIAS_INSPECCION_MIN, DIAS_INSPECCION_MAX))
    if rng.random() < PROB_FECHA_RECHAZADA:
        while dia.weekday() != DOMINGO and dia.day not in DIAS_AGENDA_LLENA:
            dia += dt.timedelta(days=1)
    return dia


def _logistica(rng: random.Random, j: int) -> dict:
    auto, destino = _ruta(rng, j)
    dias = verificar_disponibilidad_entrega(auto["id"], destino)["dias_habiles"]
    if dias is None:
        plazo = rng.randint(*RANGO_PLAZO_SIN_COBERTURA)
    else:
        plazo = max(1, dias + AJUSTES_PLAZO[j % len(AJUSTES_PLAZO)])
    prompt = (f"Quiero que me lleven el {auto['id']} a {NOMBRE_CIUDAD[destino]}. Lo necesito en máximo "
              f"{plazo} días hábiles. ¿Llega a tiempo? Contéstame sí o no y dime cuántos días hábiles tarda.")
    expected = {"posible": dias is not None and dias <= plazo, "dias": dias}
    key_tools = ["verificar_disponibilidad_entrega"]
    if j % CADA_INSPECCION == 0:
        fecha = _fecha_inspeccion(rng)
        prompt += (f" Además, agéndame una inspección en la sucursal donde está el auto el "
                   f"{fecha_texto(fecha)} o el siguiente día disponible, y dame el folio.")
        expected["folio"] = _primera_cita(auto["id"], fecha, auto["ciudad"])
        key_tools.append("agendar_inspeccion")
    return {"family": "logistica", "prompt": prompt, "expected": expected, "key_tools": key_tools}


def _tramite(rng: random.Random, j: int) -> dict:
    estado_placas = rng.choice(list(NOMBRE_ESTADO))
    if j % CADA_MISMO_ESTADO == 0:
        ciudad = next(c for c in CIUDADES if ESTADO_DE_CIUDAD[c] == estado_placas)
        tramites = [consultar_tramite(estado_placas, "cambio_propietario")]
    else:  # placas de otro estado: baja en el de origen y alta en el del cliente
        ciudad = rng.choice([c for c in CIUDADES if ESTADO_DE_CIUDAD[c] != estado_placas])
        tramites = [consultar_tramite(estado_placas, "baja_placas"),
                    consultar_tramite(ciudad, "alta_placas")]
    papeles = []
    for tramite in tramites:
        papeles += [p for p in tramite["requisitos"] if p not in papeles]
    return {"family": "tramite",
            "prompt": f"Compré un auto usado con placas de {NOMBRE_ESTADO[estado_placas]} y vivo en "
                      f"{NOMBRE_CIUDAD[ciudad]}. ¿Qué papeles necesito para ponerlo a mi nombre y "
                      "cuántos días hábiles tarda el trámite en total?",
            "expected": {"dias": sum(t["dias_habiles"] for t in tramites), "papeles": papeles},
            "key_tools": ["consultar_tramite"]}


def _trampa_auto_inexistente(rng: random.Random) -> tuple[str, list[str], bool]:
    auto_id = f"A{rng.randint(INVENTORY_SIZE, ID_INEXISTENTE_MAX):03d}"
    prompt = (f"Me interesa el {auto_id}. ¿Me lo apartan y me dicen la mensualidad a "
              f"{PLAZO_DEFAULT_MESES} meses con {ENGANCHE_TRAMPA:,} de enganche?")
    imposible = verificar_disponibilidad_entrega(auto_id, "CDMX").get("error") == "auto_no_existe"
    return prompt, ["buscar_inventario", "verificar_disponibilidad_entrega", "politica_garantia"], imposible


def _trampa_marca_no_vendida(rng: random.Random) -> tuple[str, list[str], bool]:
    marca = rng.choice(list(MARCAS_NO_VENDIDAS))
    ciudad = rng.choice(CIUDADES)
    prompt = f"¿Tienen algún {marca} {MARCAS_NO_VENDIDAS[marca]} en {NOMBRE_CIUDAD[ciudad]}? Quiero apartarlo."
    return prompt, ["buscar_inventario"], buscar_inventario(marca=marca)["total"] == 0


def _trampa_anio_futuro(rng: random.Random) -> tuple[str, list[str], bool]:
    marca = rng.choice(list(MODELOS))
    modelo, anio = rng.choice(MODELOS[marca]), ANIO_MAX + rng.randint(1, 2)
    prompt = f"Busco un {marca} {modelo} {anio} o más nuevo. ¿Cuál me recomiendan para apartarlo?"
    imposible = buscar_inventario(marca=marca, modelo=modelo, anio_min=anio)["total"] == 0
    return prompt, ["buscar_inventario"], imposible


def _trampa_ciudad_sin_sucursal(rng: random.Random) -> tuple[str, list[str], bool]:
    auto, ciudad = rng.choice(INVENTARIO), rng.choice(CIUDADES_SIN_SUCURSAL)
    prompt = f"Quiero que me lleven el {auto['id']} a {ciudad}. ¿En cuántos días hábiles me llega?"
    imposible = verificar_disponibilidad_entrega(auto["id"], ciudad).get("error") == "ciudad_sin_sucursal"
    return prompt, ["verificar_disponibilidad_entrega"], imposible


def _trampa_presupuesto_imposible(rng: random.Random) -> tuple[str, list[str], bool]:
    ciudad = rng.choice(CIUDADES)
    enganche, tope = rng.choice(ENGANCHES_BAJOS), rng.choice(TOPES_IMPOSIBLES)
    prompt = (f"Vivo en {NOMBRE_CIUDAD[ciudad]}, tengo {enganche:,} de enganche y quiero pagar máximo "
              f"{tope:,} al mes a {PLAZO_DEFAULT_MESES} meses. ¿Qué auto me aparto?")
    imposible = not autos_que_alcanzan(ciudad, enganche, tope, PLAZO_DEFAULT_MESES)
    return prompt, ["buscar_inventario", "calcular_financiamiento"], imposible


FABRICAS_TRAMPA = {"auto_inexistente": _trampa_auto_inexistente,
                   "marca_no_vendida": _trampa_marca_no_vendida,
                   "anio_futuro": _trampa_anio_futuro,
                   "ciudad_sin_sucursal": _trampa_ciudad_sin_sucursal,
                   "presupuesto_imposible": _trampa_presupuesto_imposible}


def _trampa(rng: random.Random, j: int) -> dict:
    subtipo = SUBTIPOS_TRAMPA[j % len(SUBTIPOS_TRAMPA)]
    # Se repite hasta que las tools confirman que la petición es imposible
    for _ in range(MAX_INTENTOS):
        prompt, key_tools, imposible = FABRICAS_TRAMPA[subtipo](rng)
        if imposible:
            break
    else:
        raise RuntimeError(f"Las tools no confirmaron ninguna trampa de tipo {subtipo}")
    return {"family": "trampa", "prompt": prompt, "expected": {"rechazo": True, "subtipo": subtipo},
            "key_tools": key_tools}


FAMILIAS = {"cotizacion": _cotizacion, "garantia": _garantia, "logistica": _logistica,
            "tramite": _tramite, "trampa": _trampa}


def construir(semilla: int = INVENTORY_SEED) -> list[Task]:
    rng, tareas = random.Random(semilla), []
    for familia, fabrica in FAMILIAS.items():
        for j in range(TASKS_PER_FAMILY):
            tarea = fabrica(rng, j)
            tarea["id"] = f"{FAMILY_PREFIX[familia]}_{j:02d}"
            # Las primeras de cada familia son el examen: el destilador nunca las ve
            tarea["split"] = "heldout" if j < HELDOUT_PER_FAMILY else "train"
            tareas.append(tarea)
    return tareas


TAREAS = construir()
POR_ID_TAREA = {t["id"]: t for t in TAREAS}
