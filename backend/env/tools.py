"""Las 8 herramientas base del agente (FUNCIONES + ESQUEMAS). Puras, deterministas y sin LLM.

Nunca lanzan excepción con argumentos de valor inválido: devuelven {"error": ...} o
{"ok": False, "motivo": ...} para que el agente lea el problema y se corrija. Un argumento que no
existe en la firma lo atrapa el bucle del agente (agents/agent.py) antes de llegar aquí.

Las reglas ocultas viven en el código y no en las descripciones de ESQUEMAS: el agente tiene que
descubrirlas leyendo las respuestas. Si cambias una regla, cambian las respuestas esperadas de
env/tareas.py.
"""
from __future__ import annotations

import datetime as dt

from env.inventario import ESTADO_DE_CIUDAD, INVENTARIO, POR_ID, normalizar_ciudad, sin_acentos

# Fecha real de la corrida. Las tareas calculan sus fechas a partir de aquí, así que una
# corrida que cruza la medianoche o un rescore de otro día ven otras respuestas esperadas.
HOY = dt.date.today()
MAX_RESULTADOS = 15  # regla oculta: obliga al agente a filtrar la búsqueda
PLAZO_DEFAULT_MESES = 48
TASA_ANUAL_DEFAULT = 0.16

# Días hábiles de traslado entre sucursales, en ambos sentidos. Las rutas que no aparecen no tienen
# cobertura: MID↔GDL y MID↔MTY (regla oculta).
DIAS_RUTA = {
    ("CDMX", "CDMX"): 1, ("GDL", "GDL"): 1, ("MTY", "MTY"): 1, ("MID", "MID"): 1, ("PUE", "PUE"): 1,
    ("CDMX", "PUE"): 2, ("CDMX", "GDL"): 3, ("CDMX", "MTY"): 4, ("CDMX", "MID"): 5,
    ("GDL", "MTY"): 4, ("GDL", "PUE"): 4, ("MTY", "PUE"): 5, ("MID", "PUE"): 4,
}

MESES_GARANTIA = {"motor": 24, "transmision": 24, "electrico": 12, "suspension": 6, "frenos": 3,
                  "estetico": 0}
# Fragmento que aparece en lo que escribe el cliente -> tipo de falla. "electric" cubre
# eléctrico y eléctrica; "freno", freno y frenos.
SINONIMOS_FALLA = {"motor": "motor", "transmision": "transmision", "caja": "transmision",
                   "electric": "electrico", "bateria": "electrico", "suspension": "suspension",
                   "amortiguador": "suspension", "freno": "frenos", "estetic": "estetico",
                   "pintura": "estetico", "rayon": "estetico"}
KM_ALTO = 100_000  # motor o transmisión con más km: garantía reducida
MESES_MOTOR_KM_ALTO = 12
ANIO_ELECTRICO_VIEJO = 2018  # falla eléctrica en este año o antes: garantía reducida
MESES_ELECTRICO_VIEJO = 6

DOMINGO = 6  # date.weekday(): la sucursal cierra
DIAS_AGENDA_LLENA = (1, 15)

TIPOS_TRAMITE = ("baja_placas", "alta_placas", "cambio_propietario")
REQUISITOS_TRAMITE = {
    "baja_placas": ["factura", "identificacion oficial", "tarjeta de circulacion", "placas"],
    "alta_placas": ["factura", "identificacion oficial", "comprobante de domicilio",
                    "constancia de baja"],
    "cambio_propietario": ["factura endosada", "identificacion oficial", "comprobante de domicilio",
                           "tarjeta de circulacion"],
}
REQUISITO_DEL_ESTADO = {"CDMX": "verificacion vehicular", "Jalisco": "pago de refrendo",
                        "Nuevo Leon": "pago de tenencia", "Yucatan": "constancia de no adeudo",
                        "Puebla": "pago de control vehicular"}
DIAS_TRAMITE = {  # días hábiles por estado y tipo de trámite
    "CDMX": {"baja_placas": 3, "alta_placas": 5, "cambio_propietario": 4},
    "Jalisco": {"baja_placas": 2, "alta_placas": 4, "cambio_propietario": 3},
    "Nuevo Leon": {"baja_placas": 3, "alta_placas": 4, "cambio_propietario": 5},
    "Yucatan": {"baja_placas": 4, "alta_placas": 6, "cambio_propietario": 5},
    "Puebla": {"baja_placas": 2, "alta_placas": 3, "cambio_propietario": 3},
}


# ---------------------------------------------------------------------------
# Normalización de lo que escribe el modelo
# ---------------------------------------------------------------------------
def a_numero(valor, tipo: type = float) -> float | int | None:
    """float o int de lo que mande el modelo ("48", 48.0). None si no es un número."""
    try:
        return tipo(float(valor)) if tipo is int else tipo(valor)
    except (TypeError, ValueError, OverflowError):
        return None


def a_fraccion(valor: float) -> float:
    """El modelo escribe 16 o 0.16 para el mismo 16 %; se acepta cualquiera de los dos."""
    return valor / 100 if valor > 1 else valor


def buscar_auto(auto_id) -> dict | None:
    return POR_ID.get(str(auto_id).strip().upper())


def normalizar_estado(estado: str | None) -> str | None:
    """'Nuevo León', 'MTY' o 'Monterrey' -> 'Nuevo Leon'. None si no hay servicio en ese estado."""
    texto = sin_acentos(estado or "")
    for nombre in DIAS_TRAMITE:
        if texto == sin_acentos(nombre):
            return nombre
    ciudad = normalizar_ciudad(estado)
    if ciudad is None:
        return None
    return ESTADO_DE_CIUDAD[ciudad]


def normalizar_falla(tipo_falla: str | None) -> str | None:
    """'falla de la transmisión' -> 'transmision'. None si no se reconoce."""
    texto = sin_acentos(tipo_falla or "")
    for fragmento, falla in SINONIMOS_FALLA.items():
        if fragmento in texto:
            return falla
    return None


def dias_ruta(origen: str, destino: str) -> int | None:
    """Días hábiles entre dos sucursales. None si la ruta no tiene cobertura."""
    return DIAS_RUTA.get((origen, destino)) or DIAS_RUTA.get((destino, origen))


def folio_inspeccion(auto_id: str, dia: dt.date, sucursal: str) -> str:
    """Folio determinista: la misma cita siempre da el mismo folio, así la tarea puede esperarlo."""
    return f"INS-{sucursal}-{dia:%Y%m%d}-{auto_id}"


# ---------------------------------------------------------------------------
# Las 8 herramientas
# ---------------------------------------------------------------------------
def buscar_inventario(marca=None, modelo=None, anio_min=None, precio_max=None, ciudad=None) -> dict:
    ciudad_buscada = normalizar_ciudad(ciudad) if ciudad else None
    if ciudad and ciudad_buscada is None:
        return {"error": "ciudad_sin_sucursal", "ciudades": list(ESTADO_DE_CIUDAD)}
    anio = a_numero(anio_min, int) if anio_min is not None else None
    precio = a_numero(precio_max) if precio_max is not None else None
    if (anio_min is not None and anio is None) or (precio_max is not None and precio is None):
        return {"error": "anio_min y precio_max deben ser numeros"}
    autos = [a for a in INVENTARIO
             if (not marca or sin_acentos(a["marca"]) == sin_acentos(marca))
             and (not modelo or sin_acentos(a["modelo"]) == sin_acentos(modelo))
             and (anio is None or a["anio"] >= anio)
             and (precio is None or a["precio"] <= precio)
             and (ciudad_buscada is None or a["ciudad"] == ciudad_buscada)]
    autos.sort(key=lambda a: (a["precio"], a["id"]))
    return {"total": len(autos), "truncado": len(autos) > MAX_RESULTADOS,
            "autos": autos[:MAX_RESULTADOS]}


def calcular_enganche(precio, porcentaje) -> dict:
    precio, porcentaje = a_numero(precio), a_numero(porcentaje)
    if precio is None or porcentaje is None:
        return {"error": "precio y porcentaje deben ser numeros"}
    return {"enganche": round(precio * a_fraccion(porcentaje), 2)}


def calcular_financiamiento(precio, enganche, plazo_meses=PLAZO_DEFAULT_MESES,
                            tasa_anual=TASA_ANUAL_DEFAULT) -> dict:
    precio, enganche = a_numero(precio), a_numero(enganche)
    plazo, tasa = a_numero(plazo_meses, int), a_numero(tasa_anual)
    if None in (precio, enganche, plazo, tasa):
        return {"error": "precio, enganche, plazo_meses y tasa_anual deben ser numeros"}
    monto = precio - enganche
    if monto <= 0:
        return {"error": "el enganche cubre el precio; no hay nada que financiar"}
    if plazo <= 0:
        return {"error": "plazo_meses debe ser mayor que 0"}
    tasa_mensual = a_fraccion(tasa) / 12
    if tasa_mensual == 0:
        mensualidad = monto / plazo
    else:
        mensualidad = monto * tasa_mensual / (1 - (1 + tasa_mensual) ** -plazo)
    return {"mensualidad": round(mensualidad, 2),
            "costo_total": round(mensualidad * plazo + enganche, 2)}


def verificar_disponibilidad_entrega(auto_id, ciudad_destino) -> dict:
    auto = buscar_auto(auto_id)
    if auto is None:
        return {"error": "auto_no_existe"}
    destino = normalizar_ciudad(ciudad_destino)
    if destino is None:
        return {"error": "ciudad_sin_sucursal", "ciudades": list(ESTADO_DE_CIUDAD)}
    dias = dias_ruta(auto["ciudad"], destino)
    if dias is None:
        return {"dias_habiles": None, "origen": auto["ciudad"], "estado": "sin_cobertura"}
    return {"dias_habiles": dias, "origen": auto["ciudad"]}


def politica_garantia(auto_id, tipo_falla, meses_desde_compra) -> dict:
    auto = buscar_auto(auto_id)
    if auto is None:
        return {"error": "auto_no_existe"}
    falla = normalizar_falla(tipo_falla)
    if falla is None:
        return {"error": "tipo_falla_desconocido", "tipos": list(MESES_GARANTIA)}
    meses = a_numero(meses_desde_compra, int)
    if meses is None or meses < 0:
        return {"error": "meses_desde_compra debe ser un entero mayor o igual a 0"}
    limite, sustento = MESES_GARANTIA[falla], f"{falla} cubre {MESES_GARANTIA[falla]} meses"
    if falla in ("motor", "transmision") and auto["km"] > KM_ALTO:
        limite, sustento = MESES_MOTOR_KM_ALTO, f"{falla} con mas de 100,000 km cubre 12 meses"
    if falla == "electrico" and auto["anio"] <= ANIO_ELECTRICO_VIEJO:
        limite, sustento = MESES_ELECTRICO_VIEJO, "electrico en modelos 2018 o anteriores cubre 6 meses"
    cubierto = meses <= limite
    return {"cubierto": cubierto, "sustento": sustento,
            "procede": "reparacion_sin_costo" if cubierto else "cotizar_reparacion"}


def agendar_inspeccion(auto_id, fecha, sucursal) -> dict:
    auto = buscar_auto(auto_id)
    if auto is None:
        return {"ok": False, "motivo": "auto_no_existe"}
    ciudad = normalizar_ciudad(sucursal)
    if ciudad is None:
        return {"ok": False, "motivo": "sucursal_no_existe", "sucursales": list(ESTADO_DE_CIUDAD)}
    try:
        dia = dt.date.fromisoformat(str(fecha).strip())
    except ValueError:
        return {"ok": False, "motivo": "fecha debe tener el formato AAAA-MM-DD"}
    if dia <= HOY:
        return {"ok": False, "motivo": f"la fecha debe ser posterior a hoy ({HOY.isoformat()})"}
    if dia.weekday() == DOMINGO:
        return {"ok": False, "motivo": "domingo: sucursal cerrada"}
    if dia.day in DIAS_AGENDA_LLENA:
        return {"ok": False, "motivo": f"agenda llena el dia {dia.day}"}
    return {"ok": True, "folio": folio_inspeccion(auto["id"], dia, ciudad)}


def consultar_tramite(estado, tipo_tramite) -> dict:
    nombre = normalizar_estado(estado)
    if nombre is None:
        return {"error": "estado_sin_servicio", "estados": list(DIAS_TRAMITE)}
    tipo = sin_acentos(tipo_tramite or "").replace(" ", "_")
    if tipo not in TIPOS_TRAMITE:
        return {"error": "tipo_tramite_desconocido", "tipos": list(TIPOS_TRAMITE)}
    return {"estado": nombre, "tipo_tramite": tipo, "dias_habiles": DIAS_TRAMITE[nombre][tipo],
            "requisitos": REQUISITOS_TRAMITE[tipo] + [REQUISITO_DEL_ESTADO[nombre]]}


def escalar_humano(motivo="") -> dict:
    # El verificador marca como fallo cualquier episodio que la use (escalado_innecesario)
    return {"escalado": True}


FUNCIONES = {
    "buscar_inventario": buscar_inventario,
    "calcular_enganche": calcular_enganche,
    "calcular_financiamiento": calcular_financiamiento,
    "verificar_disponibilidad_entrega": verificar_disponibilidad_entrega,
    "politica_garantia": politica_garantia,
    "agendar_inspeccion": agendar_inspeccion,
    "consultar_tramite": consultar_tramite,
    "escalar_humano": escalar_humano,
}


# ---------------------------------------------------------------------------
# Esquemas para function calling de OpenAI: lo que el modelo lee para saber qué existe
# ---------------------------------------------------------------------------
def _fn(name: str, description: str, props: dict, required: tuple = ()) -> dict:
    return {"type": "function", "function": {"name": name, "description": description,
            "parameters": {"type": "object", "properties": props, "required": list(required)}}}


S, N, I = {"type": "string"}, {"type": "number"}, {"type": "integer"}
SUCURSALES = {"type": "string", "description": "CDMX, GDL, MTY, MID o PUE"}
AUTO_ID = {"type": "string", "description": "Formato A000"}

ESQUEMAS = {
    "buscar_inventario": _fn(
        "buscar_inventario",
        "Busca autos en el inventario. Todos los filtros son opcionales. Ordena por precio ascendente.",
        {"marca": S, "modelo": S, "anio_min": I, "precio_max": N, "ciudad": SUCURSALES}),
    "calcular_enganche": _fn(
        "calcular_enganche", "Enganche en pesos para un porcentaje del precio.",
        {"precio": N, "porcentaje": {"type": "number", "description": "20 para 20 %"}},
        ("precio", "porcentaje")),
    "calcular_financiamiento": _fn(
        "calcular_financiamiento",
        "Mensualidad exacta y costo total de un crédito. Plazo por defecto 48 meses y tasa anual 0.16.",
        {"precio": N, "enganche": N, "plazo_meses": I, "tasa_anual": N}, ("precio", "enganche")),
    "verificar_disponibilidad_entrega": _fn(
        "verificar_disponibilidad_entrega",
        "Días hábiles para trasladar un auto desde su sucursal a otra ciudad.",
        {"auto_id": AUTO_ID, "ciudad_destino": SUCURSALES}, ("auto_id", "ciudad_destino")),
    "politica_garantia": _fn(
        "politica_garantia", "Indica si una falla está cubierta por la garantía y con qué sustento.",
        {"auto_id": AUTO_ID,
         "tipo_falla": {"type": "string",
                        "description": "motor, transmision, electrico, suspension, frenos o estetico"},
         "meses_desde_compra": I},
        ("auto_id", "tipo_falla", "meses_desde_compra")),
    "agendar_inspeccion": _fn(
        "agendar_inspeccion", "Agenda una inspección del auto en una sucursal y devuelve un folio.",
        {"auto_id": AUTO_ID, "fecha": {"type": "string", "description": "AAAA-MM-DD"},
         "sucursal": SUCURSALES},
        ("auto_id", "fecha", "sucursal")),
    "consultar_tramite": _fn(
        "consultar_tramite", "Requisitos y días hábiles de un trámite vehicular en un estado.",
        {"estado": S, "tipo_tramite": {"type": "string", "enum": list(TIPOS_TRAMITE)}},
        ("estado", "tipo_tramite")),
    "escalar_humano": _fn(
        "escalar_humano", "Pasa el caso a un asesor humano.", {"motivo": S}, ("motivo",)),
}
