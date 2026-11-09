"""Tests del entorno. Sin LLM: corren en segundos y vigilan que el mundo sea determinista."""
from __future__ import annotations

import datetime as dt

import pytest

from core.contracts import (BASE_TOOLS, FAMILIES, FAMILY_PREFIX, HELDOUT_PER_FAMILY, INVENTORY_SIZE,
                            REASONS, TASKS_PER_FAMILY)
from env.inventario import CIUDADES, ESTADO_DE_CIUDAD, INVENTARIO, POR_ID, construir, normalizar_ciudad
from env.tareas import TAREAS, construir as construir_tareas
from env.verificador import verificar
from env.tools import (DIAS_AGENDA_LLENA, DOMINGO, ESQUEMAS, FUNCIONES, HOY, MAX_RESULTADOS, agendar_inspeccion, buscar_inventario,
                       calcular_enganche, calcular_financiamiento, consultar_tramite, escalar_humano,
                       politica_garantia, verificar_disponibilidad_entrega)


def _auto(condicion) -> dict:
    return next(a for a in INVENTARIO if condicion(a))


def test_inventario_tiene_200_autos_con_ids_unicos():
    assert len(INVENTARIO) == INVENTORY_SIZE
    assert len(POR_ID) == INVENTORY_SIZE


def test_inventario_es_reproducible():
    assert construir() == INVENTARIO


def test_autos_con_campos_del_contrato():
    campos = {"id", "marca", "modelo", "anio", "km", "precio", "ciudad"}
    assert all(set(a) == campos for a in INVENTARIO)
    assert all(a["ciudad"] in CIUDADES for a in INVENTARIO)


def test_cada_ciudad_tiene_estado():
    assert set(ESTADO_DE_CIUDAD) == set(CIUDADES)


def test_alias_de_ciudad():
    assert normalizar_ciudad("Guadalajara") == "GDL"
    assert normalizar_ciudad("Mérida") == "MID"
    assert normalizar_ciudad("cdmx") == "CDMX"
    assert normalizar_ciudad("Cancún") is None
    assert normalizar_ciudad(None) is None


# ---------------------------------------------------------------------------
# Herramientas
# ---------------------------------------------------------------------------
def test_las_8_tools_tienen_funcion_y_esquema():
    assert list(FUNCIONES) == BASE_TOOLS
    assert list(ESQUEMAS) == BASE_TOOLS
    for nombre, esquema in ESQUEMAS.items():
        assert esquema["function"]["name"] == nombre


def test_busqueda_trunca_a_15_ordenada_por_precio():
    r = buscar_inventario()
    assert r["total"] == INVENTORY_SIZE and r["truncado"]
    assert len(r["autos"]) == MAX_RESULTADOS
    precios = [a["precio"] for a in r["autos"]]
    assert precios == sorted(precios)


def test_busqueda_filtra_y_acepta_alias():
    r = buscar_inventario(marca="nissan", ciudad="Guadalajara", precio_max="300000")
    assert all(a["marca"] == "Nissan" and a["ciudad"] == "GDL" and a["precio"] <= 300_000
               for a in r["autos"])
    assert buscar_inventario(ciudad="Cancún")["error"] == "ciudad_sin_sucursal"
    assert buscar_inventario(marca="Tesla")["total"] == 0


def test_enganche_acepta_porcentaje_o_fraccion():
    assert calcular_enganche(300_000, 20) == calcular_enganche(300_000, 0.2) == {"enganche": 60_000.0}


def test_financiamiento_tasa_16():
    r = calcular_financiamiento(250_000, 50_000, 48)
    assert r["mensualidad"] == 5668.06
    assert r["costo_total"] == pytest.approx(5668.06 * 48 + 50_000, abs=1)
    assert "error" in calcular_financiamiento(100_000, 100_000)


def test_entrega_sin_cobertura_mid_gdl():
    auto = _auto(lambda a: a["ciudad"] == "MID")
    assert verificar_disponibilidad_entrega(auto["id"], "GDL")["estado"] == "sin_cobertura"
    assert verificar_disponibilidad_entrega(auto["id"], "Monterrey")["dias_habiles"] is None
    assert verificar_disponibilidad_entrega(auto["id"], "PUE")["dias_habiles"] == 4
    assert verificar_disponibilidad_entrega("A999", "PUE")["error"] == "auto_no_existe"


def test_garantia_motor_con_mas_de_100k_km_cubre_12_meses():
    auto = _auto(lambda a: a["km"] > 100_000)
    assert not politica_garantia(auto["id"], "falla de motor", 18)["cubierto"]
    assert politica_garantia(auto["id"], "transmisión", 12)["cubierto"]


def test_garantia_electrico_2018_o_antes_cubre_6_meses():
    viejo = _auto(lambda a: a["anio"] <= 2018)
    nuevo = _auto(lambda a: a["anio"] > 2018)
    assert not politica_garantia(viejo["id"], "eléctrica", 8)["cubierto"]
    assert politica_garantia(nuevo["id"], "eléctrica", 8)["cubierto"]
    assert politica_garantia(nuevo["id"], "volante", 1)["error"] == "tipo_falla_desconocido"


def _proximo_dia(condicion) -> dt.date:
    dia = HOY + dt.timedelta(days=1)
    while not condicion(dia):
        dia += dt.timedelta(days=1)
    return dia


def test_inspeccion_sin_domingos_ni_dias_1_y_15():
    auto_id = INVENTARIO[0]["id"]
    domingo = _proximo_dia(lambda d: d.weekday() == DOMINGO)
    agenda_llena = _proximo_dia(lambda d: d.day in DIAS_AGENDA_LLENA and d.weekday() != DOMINGO)
    habil = _proximo_dia(lambda d: d.day not in DIAS_AGENDA_LLENA and d.weekday() != DOMINGO)
    assert agendar_inspeccion(auto_id, domingo.isoformat(), "GDL")["motivo"] == "domingo: sucursal cerrada"
    assert "agenda llena" in agendar_inspeccion(auto_id, agenda_llena.isoformat(), "GDL")["motivo"]
    assert not agendar_inspeccion(auto_id, HOY.isoformat(), "GDL")["ok"]
    r = agendar_inspeccion(auto_id, habil.isoformat(), "Guadalajara")
    assert r == {"ok": True, "folio": f"INS-GDL-{habil:%Y%m%d}-{auto_id}"}


def test_tramite_por_estado():
    r = consultar_tramite("Nuevo León", "alta_placas")
    assert r["estado"] == "Nuevo Leon" and r["dias_habiles"] == 4
    assert "constancia de baja" in r["requisitos"]
    assert consultar_tramite("Guadalajara", "baja_placas")["estado"] == "Jalisco"
    assert consultar_tramite("Oaxaca", "baja_placas")["error"] == "estado_sin_servicio"


def test_escalar_humano():
    assert escalar_humano("no se")["escalado"]


def test_las_tools_no_lanzan_con_valores_invalidos():
    assert "error" in buscar_inventario(anio_min="nuevo")
    assert "error" in calcular_enganche("caro", None)
    assert "error" in calcular_financiamiento("x", 0, "y")
    assert "error" in politica_garantia(None, None, "diez")
    assert not agendar_inspeccion("A001", "mañana", "CDMX")["ok"]
    assert "error" in consultar_tramite(None, None)


# ---------------------------------------------------------------------------
# Tareas
# ---------------------------------------------------------------------------
def _de_familia(familia: str) -> list[dict]:
    return [t for t in TAREAS if t["family"] == familia]


def test_hay_120_tareas_con_ids_unicos():
    assert len(TAREAS) == len(FAMILIES) * TASKS_PER_FAMILY
    assert len({t["id"] for t in TAREAS}) == len(TAREAS)


def test_24_por_familia_con_su_prefijo():
    for familia in FAMILIES:
        tareas = _de_familia(familia)
        assert len(tareas) == TASKS_PER_FAMILY
        assert all(t["id"].startswith(FAMILY_PREFIX[familia] + "_") for t in tareas)


def test_split_40_heldout_8_por_familia():
    assert sum(t["split"] == "heldout" for t in TAREAS) == len(FAMILIES) * HELDOUT_PER_FAMILY
    for familia in FAMILIES:
        assert sum(t["split"] == "heldout" for t in _de_familia(familia)) == HELDOUT_PER_FAMILY


def test_tareas_reproducibles():
    assert construir_tareas() == TAREAS


def test_tareas_con_campos_de_task():
    campos = {"id", "family", "split", "prompt", "expected", "key_tools"}
    assert all(set(t) == campos for t in TAREAS)
    assert all(set(t["key_tools"]) <= set(BASE_TOOLS) for t in TAREAS)


def test_cotizacion_lista_entre_1_y_8_autos_existentes():
    for t in _de_familia("cotizacion"):
        assert 1 <= len(t["expected"]["ids"]) <= 8
        assert all(i in POR_ID for i in t["expected"]["ids"])


def test_garantia_tiene_casos_cubiertos_y_no_cubiertos():
    respuestas = {t["expected"]["cubierto"] for t in _de_familia("garantia")}
    assert respuestas == {True, False}


def test_logistica_sin_cobertura_no_es_posible():
    tareas = _de_familia("logistica")
    sin_cobertura = [t for t in tareas if t["expected"]["dias"] is None]
    assert sin_cobertura and all(not t["expected"]["posible"] for t in sin_cobertura)
    folios = [t["expected"]["folio"] for t in tareas if "folio" in t["expected"]]
    assert folios and all(f.startswith("INS-") for f in folios)


def test_tramite_de_otro_estado_pide_baja_y_alta():
    cruzados = [t for t in _de_familia("tramite") if "constancia de baja" in t["expected"]["papeles"]]
    assert cruzados
    assert all("placas" in t["expected"]["papeles"] for t in cruzados)


def test_trampas_esperan_rechazo():
    assert all(t["expected"]["rechazo"] for t in _de_familia("trampa"))


# ---------------------------------------------------------------------------
# Verificador
# ---------------------------------------------------------------------------
def _respuesta_correcta(tarea: dict) -> str:
    """Respuesta que un agente perfecto daría, armada desde `expected`."""
    esperado = tarea["expected"]
    if tarea["family"] == "cotizacion":
        return "Te alcanzan: " + ", ".join(esperado["ids"])
    if tarea["family"] == "garantia":
        return "Sí, está cubierta." if esperado["cubierto"] else "No, ya no está cubierta."
    if tarea["family"] == "logistica":
        if esperado["dias"] is None:
            texto = "No, esa ruta no tiene cobertura."
        else:
            texto = ("Sí" if esperado["posible"] else "No") + f", tarda {esperado['dias']} días hábiles."
        if "folio" in esperado:
            texto += f" Tu folio de inspección es {esperado['folio']}."
        return texto
    if tarea["family"] == "tramite":
        return f"Necesitas {', '.join(esperado['papeles'])}. Son {esperado['dias']} días hábiles."
    return "Lo siento, no tenemos eso disponible."


def test_la_respuesta_correcta_pasa_en_las_120():
    for t in TAREAS:
        v = verificar(t, _respuesta_correcta(t), t["key_tools"])
        assert v.passed, (t["id"], v.reason)


def test_reglas_globales_van_primero():
    t = TAREAS[0]
    assert verificar(t, _respuesta_correcta(t), ["escalar_humano"]).reason == "escalado_innecesario"
    assert verificar(t, _respuesta_correcta(t), t["key_tools"], agotado=True).reason == "pasos_agotados"


def test_cotizacion_sobran_o_faltan_ids():
    t = _de_familia("cotizacion")[0]
    ids = t["expected"]["ids"]
    assert verificar(t, ", ".join(ids + ["A999"]), []).reason == "mensualidad_excede_tope"
    assert verificar(t, ", ".join(ids[1:]), []).reason == "faltaron_opciones"


def test_garantia_ambigua_sin_sustento_y_equivocada():
    t = _de_familia("garantia")[0]
    contraria = "No." if t["expected"]["cubierto"] else "Sí."
    assert verificar(t, "Según la política, depende.", ["politica_garantia"]).reason == "respuesta_ambigua"
    assert verificar(t, _respuesta_correcta(t), []).reason == "garantia_sin_sustento"
    falla_tool = verificar(t, _respuesta_correcta(t), ["politica_garantia"], tools_ok=[])
    assert falla_tool.reason == "garantia_sin_sustento"
    assert verificar(t, contraria, ["politica_garantia"]).reason == "garantia_mal_interpretada"
    assert verificar(t, "**Sí**, cubierta" if t["expected"]["cubierto"] else "¡No!", ["politica_garantia"]).passed


def test_logistica_cada_etiqueta():
    tareas = _de_familia("logistica")
    sin_cobertura = next(t for t in tareas if t["expected"]["dias"] is None)
    assert verificar(sin_cobertura, "Sí, llega.", []).reason == "ruta_sin_cobertura"
    con_ruta = next(t for t in tareas if t["expected"]["dias"] is not None and "folio" not in t["expected"])
    esperado = con_ruta["expected"]
    contraria = "No" if esperado["posible"] else "Sí"
    assert verificar(con_ruta, f"{contraria}, tarda {esperado['dias']} días.", []).reason == "plazo_mal_calculado"
    acierto = "Sí" if esperado["posible"] else "No"
    otros_dias = esperado["dias"] + 10
    assert verificar(con_ruta, f"{acierto}, tarda {otros_dias} días.", []).reason == "dias_incorrectos"
    con_folio = next(t for t in tareas if "folio" in t["expected"])
    sin_folio = _respuesta_correcta(con_folio).split(" Tu folio")[0]
    assert verificar(con_folio, sin_folio, []).reason == "inspeccion_no_agendada"


def test_tramite_dias_y_papeles():
    t = _de_familia("tramite")[1]
    esperado = t["expected"]
    assert verificar(t, f"Necesitas {', '.join(esperado['papeles'])}. Son 99 días.", []).reason == "dias_incorrectos"
    incompleta = f"Necesitas {esperado['papeles'][0]}. Son {esperado['dias']} días hábiles."
    assert verificar(t, incompleta, []).reason == "tramite_incompleto"


def test_trampa_exige_rechazo_con_sustento():
    t = _de_familia("trampa")[0]
    assert verificar(t, "Claro, te lo aparto.", t["key_tools"]).reason == "trampa_no_rechazada"
    assert verificar(t, "Lo siento, no existe.", []).reason == "trampa_no_rechazada"
    # Una tool que respondió con error (auto_no_existe) sí cuenta como sustento
    assert verificar(t, "Lo siento, no existe.", t["key_tools"][:1], tools_ok=[]).passed


def test_todas_las_etiquetas_son_del_contrato():
    respuestas_malas = ["", "Claro.", "Sí, 99 días."]
    for t in TAREAS:
        for respuesta in respuestas_malas:
            v = verificar(t, respuesta, [])
            assert v.passed or v.reason in REASONS
