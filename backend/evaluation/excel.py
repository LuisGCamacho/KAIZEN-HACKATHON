"""Excel de Evolución: las mismas filas que el CSV de la web, con tabla con formato, resumen y gráficas.

Lo genera exportar_excel.py para la ruta /api/excel. Los datos salen de export.filas_de_rama(), así que
el Excel y la vista Evolución siempre muestran los mismos números. Nada se rellena: un valor ausente
queda como celda vacía.
"""
from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.chart import BarChart, LineChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

FUENTE = "Arial"
TINTA, GRIS, LINEA = "1E1E20", "5E5D58", "D9D7D0"
VERDE, MORADO, NARANJA, GRIS_TRAIN = "2E8B66", "5B4FC4", "B5532F", "8C8B85"
FILA_ENCABEZADOS = 4
ALTO_GRAFICA_CM, ANCHO_LINEA_CM, ANCHO_BARRAS_CM = 8.5, 16, 14
GROSOR_HELDOUT, GROSOR_TRAIN = 32000, 19050  # EMU: ~2.5 pt y 1.5 pt

# (clave de la fila, encabezado, formato de número, ancho de columna). Mismo orden que web/lib/csv.ts
COLUMNAS: list[tuple[str, str, str, int]] = [
    ("branch", "Rama", "@", 10),
    ("generation", "Generación", "0", 12),
    ("seeds", "Semillas", "0", 10),
    ("heldout_mean", "Éxito held-out", "0.0%", 15),
    ("heldout_std", "Desv. held-out", "0.0%;-0.0%;-", 15),
    ("train_mean", "Éxito train", "0.0%", 13),
    ("train_std", "Desv. train", "0.0%;-0.0%;-", 13),
    ("delta", "Delta vs. padre", "+0.0%;-0.0%;-", 15),
    ("avg_steps", "Pasos promedio", "0.00", 15),
    ("tool_precision", "Precisión de tools", "0.0%", 17),
    ("judge_correlation", "Correlación del juez", "0.00", 19),
    ("escalations", "Escalados", "0", 11),
    ("cost_usd", "Costo (USD)", "$#,##0.00;($#,##0.00);-", 13),
    ("cost_per_solved", "Costo por resuelta (USD)", "$#,##0.0000;($#,##0.0000);-", 22),
    ("topology", "Topología", "@", 14),
]
COL_GENERACION, COL_HELDOUT, COL_TRAIN, COL_PASOS, COL_ESCALADOS = 2, 4, 6, 9, 12
ANCHO_ETIQUETAS = 34


def _letra(columna: int) -> str:
    return get_column_letter(columna)


def _escribir_tabla(ws: Worksheet, filas: list[dict[str, Any]]) -> int:
    """Encabezados, datos y estilo de tabla. Devuelve la última fila con datos."""
    for i, (_, titulo, _, ancho) in enumerate(COLUMNAS, start=1):
        celda = ws.cell(row=FILA_ENCABEZADOS, column=i, value=titulo)
        celda.font = Font(name=FUENTE, size=10, bold=True, color="FFFFFF")
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[_letra(i)].width = ancho
    ws.row_dimensions[FILA_ENCABEZADOS].height = 30

    for r, fila in enumerate(filas, start=FILA_ENCABEZADOS + 1):
        for i, (clave, _, formato, _) in enumerate(COLUMNAS, start=1):
            celda = ws.cell(row=r, column=i, value=fila.get(clave))
            celda.font = Font(name=FUENTE, size=10, color=TINTA)
            celda.number_format = formato
            celda.alignment = Alignment(horizontal="left" if formato == "@" else "center", vertical="center")
        # El éxito held-out es la métrica oficial: se resalta
        ws.cell(row=r, column=COL_HELDOUT).font = Font(name=FUENTE, size=10, bold=True, color=VERDE)
        ws.row_dimensions[r].height = 20

    ultima = FILA_ENCABEZADOS + len(filas)
    tabla = Table(displayName="Generaciones", ref=f"A{FILA_ENCABEZADOS}:{_letra(len(COLUMNAS))}{ultima}")
    tabla.tableStyleInfo = TableStyleInfo(name="TableStyleMedium2", showRowStripes=True)
    ws.add_table(tabla)
    ws.freeze_panes = ws.cell(row=FILA_ENCABEZADOS + 1, column=COL_GENERACION + 1)
    return ultima


def _escribir_resumen(ws: Worksheet, ultima: int) -> int:
    """Resumen con fórmulas, para que se recalcule si alguien edita la tabla. Devuelve su última fila."""
    inicio = ultima + 2
    primera = FILA_ENCABEZADOS + 1
    heldout = f"${_letra(COL_HELDOUT)}${primera}:${_letra(COL_HELDOUT)}${ultima}"
    generacion = f"${_letra(COL_GENERACION)}${primera}:${_letra(COL_GENERACION)}${ultima}"
    renglones = [
        ("Éxito held-out en la primera generación", f"=INDEX({heldout},1)", "0.0%"),
        ("Mejor éxito held-out", f"=MAX({heldout})", "0.0%"),
        ("Generación con el mejor held-out", f"=INDEX({generacion},MATCH(MAX({heldout}),{heldout},0))", "0"),
        ("Mejora desde la primera generación", f"=B{inicio + 2}-B{inicio + 1}", "+0.0%;-0.0%;-"),
        ("Generaciones evaluadas", f"=COUNT({generacion})", "0"),
    ]
    titulo = ws.cell(row=inicio, column=1, value="Resumen (se recalcula si cambian los datos)")
    titulo.font = Font(name=FUENTE, size=11, bold=True, color=TINTA)
    borde = Border(bottom=Side(style="thin", color=LINEA))
    for k, (etiqueta, formula, formato) in enumerate(renglones, start=1):
        a = ws.cell(row=inicio + k, column=1, value=etiqueta)
        b = ws.cell(row=inicio + k, column=2, value=formula)
        a.font = Font(name=FUENTE, size=10, color=TINTA)
        b.font = Font(name=FUENTE, size=11, bold=True, color=TINTA)
        b.number_format = formato
        b.alignment = Alignment(horizontal="right")
        a.border = b.border = borde
    ws.column_dimensions["A"].width = ANCHO_ETIQUETAS
    return inicio + len(renglones)


def notas_para(filas: list[dict[str, Any]]) -> list[str]:
    """Notas que explican lo que la tabla no dice. Solo aparecen las que aplican a estos datos."""
    notas = []
    if all(f.get("seeds") == 1 for f in filas):
        notas.append("Una sola semilla por generación: la desviación es 0 y no hay barras de error. "
                     "Con KAIZEN_SEEDS=1,2,3 aparecen.")
    if all(f.get("judge_correlation") is None for f in filas):
        notas.append("Correlación del juez vacía: no hubo notas del juez en esta corrida "
                     "(por ejemplo, con KAIZEN_JUDGE apagado). No se rellena.")
    if all(not f.get("cost_usd") for f in filas):
        notas.append("Costo 0 USD: con el proveedor Codex el gasto se mide en tokens, no en dólares.")
    notas.append("La métrica oficial es el éxito held-out: 40 tareas que el destilador nunca ve, "
                 "calificadas por el verificador sin IA.")
    return notas


def _escribir_notas(ws: Worksheet, desde: int, filas: list[dict[str, Any]]) -> int:
    ws.cell(row=desde, column=1, value="Notas").font = Font(name=FUENTE, size=11, bold=True, color=TINTA)
    notas = notas_para(filas)
    for k, texto in enumerate(notas, start=1):
        ws.cell(row=desde + k, column=1, value=f"• {texto}").font = Font(name=FUENTE, size=9, color=GRIS)
    return desde + len(notas)


def _grafica_exito(ws: Worksheet, ultima: int) -> LineChart:
    """Held-out (verde, con su % sobre cada punto) contra train (gris punteada). Eje de 0 a 100 %."""
    grafica = LineChart()
    grafica.title = "Éxito por generación"
    grafica.y_axis.title, grafica.x_axis.title = "Tareas resueltas", "Generación"
    grafica.y_axis.scaling.min, grafica.y_axis.scaling.max = 0, 1
    grafica.y_axis.number_format, grafica.y_axis.majorUnit = "0%", 0.2
    for columna in (COL_HELDOUT, COL_TRAIN):
        grafica.add_data(Reference(ws, min_col=columna, min_row=FILA_ENCABEZADOS, max_row=ultima), titles_from_data=True)
    grafica.set_categories(Reference(ws, min_col=COL_GENERACION, min_row=FILA_ENCABEZADOS + 1, max_row=ultima))
    heldout, train = grafica.series
    for serie, color, grosor, tamano in ((heldout, VERDE, GROSOR_HELDOUT, 8), (train, GRIS_TRAIN, GROSOR_TRAIN, 6)):
        serie.graphicalProperties.line.solidFill = color
        serie.graphicalProperties.line.width = grosor
        serie.marker.symbol, serie.marker.size = "circle", tamano
        serie.marker.graphicalProperties.solidFill = serie.marker.graphicalProperties.line.solidFill = color
    train.graphicalProperties.line.dashStyle = "dash"
    heldout.dLbls = DataLabelList()
    heldout.dLbls.showVal, heldout.dLbls.position, heldout.dLbls.numFmt = True, "t", "0%"
    grafica.x_axis.delete = grafica.y_axis.delete = False
    grafica.legend.position = "b"
    grafica.height, grafica.width = ALTO_GRAFICA_CM, ANCHO_LINEA_CM
    return grafica


def _grafica_eficiencia(ws: Worksheet, ultima: int) -> BarChart:
    """Pasos promedio y escalados por generación: si el agente resuelve con menos vueltas y sin escalar."""
    grafica = BarChart()
    grafica.type = "col"
    grafica.title = "Eficiencia del agente"
    grafica.y_axis.title, grafica.x_axis.title = "Cantidad", "Generación"
    grafica.y_axis.scaling.min = 0
    for columna in (COL_PASOS, COL_ESCALADOS):
        grafica.add_data(Reference(ws, min_col=columna, min_row=FILA_ENCABEZADOS, max_row=ultima), titles_from_data=True)
    grafica.set_categories(Reference(ws, min_col=COL_GENERACION, min_row=FILA_ENCABEZADOS + 1, max_row=ultima))
    for serie, color in zip(grafica.series, (MORADO, NARANJA)):
        serie.graphicalProperties.solidFill = color
        serie.dLbls = DataLabelList()
        serie.dLbls.showVal = True
    grafica.x_axis.delete = grafica.y_axis.delete = False
    grafica.legend.position = "b"
    grafica.height, grafica.width = ALTO_GRAFICA_CM, ANCHO_BARRAS_CM
    return grafica


def construir(filas: list[dict[str, Any]], branch: str) -> bytes:
    """El .xlsx completo de una rama. Exige al menos una fila: sin datos la web no ofrece la descarga."""
    if not filas:
        raise ValueError(f"La rama {branch} no tiene generaciones evaluadas")
    wb = Workbook()
    ws = wb.active
    ws.title = "Generaciones"
    ws.sheet_view.showGridLines = False
    ws["A1"] = f"KAIZEN · evolución por generación · rama {branch}"
    ws["A1"].font = Font(name=FUENTE, size=16, bold=True, color=TINTA)
    ws["A2"] = ("Fuente: reports.json de la corrida (los mismos datos de la vista Evolución). "
                "Valores tal como los escribió el sistema; ninguno se capturó a mano.")
    ws["A2"].font = Font(name=FUENTE, size=9, italic=True, color=GRIS)

    ultima = _escribir_tabla(ws, filas)
    fin_resumen = _escribir_resumen(ws, ultima)
    fin_notas = _escribir_notas(ws, fin_resumen + 2, filas)
    # Las gráficas van debajo de las notas: el texto de las notas se desborda hacia la derecha
    fila_graficas = fin_notas + 2
    ws.add_chart(_grafica_exito(ws, ultima), f"A{fila_graficas}")
    ws.add_chart(_grafica_eficiencia(ws, ultima), f"G{fila_graficas}")

    wb.calculation.fullCalcOnLoad = True  # openpyxl no calcula fórmulas: Excel las calcula al abrir
    salida = BytesIO()
    wb.save(salida)
    return salida.getvalue()
