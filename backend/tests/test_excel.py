"""Tests del Excel de Evolución: estructura, formatos, fórmulas y gráficas. Sin LLM."""
from __future__ import annotations

from io import BytesIO

import pytest
from openpyxl import load_workbook

import exportar_excel
from evaluation import excel


def _fila(generacion: int, heldout: float, **extra) -> dict:
    fila = {"branch": "main", "generation": generacion, "seeds": 1, "heldout_mean": heldout, "heldout_std": 0,
            "train_mean": heldout, "train_std": 0, "delta": 0, "avg_steps": 2.5, "tool_precision": 0.97,
            "judge_correlation": None, "escalations": 3, "cost_usd": 0, "cost_per_solved": 0,
            "topology": "single_react"}
    return {**fila, **extra}


FILAS = [_fila(0, 0.68), _fila(1, 0.84, delta=0.16)]


def _hoja(filas=FILAS):
    return load_workbook(BytesIO(excel.construir(filas, "main")))["Generaciones"]


def test_tabla_con_encabezados_y_valores_del_reporte():
    ws = _hoja()
    assert [c.value for c in ws[excel.FILA_ENCABEZADOS]][:4] == ["Rama", "Generación", "Semillas", "Éxito held-out"]
    assert ws.cell(row=5, column=excel.COL_HELDOUT).value == 0.68
    assert ws.cell(row=6, column=excel.COL_HELDOUT).number_format == "0.0%"
    assert ws.cell(row=5, column=11).value is None  # correlación del juez ausente: no se inventa
    assert list(ws.tables) == ["Generaciones"] and ws.tables["Generaciones"].ref == "A4:O6"


def test_resumen_con_formulas_sobre_la_tabla():
    ws = _hoja()
    formulas = [ws.cell(row=r, column=2).value for r in range(9, 14)]
    assert formulas[0] == "=INDEX($D$5:$D$6,1)"
    assert formulas[1] == "=MAX($D$5:$D$6)"
    assert formulas[3] == "=B10-B9"  # mejor menos la primera


def test_dos_graficas():
    assert len(_hoja()._charts) == 2


def test_notas_solo_las_que_aplican():
    con_juez = [_fila(0, 0.5, seeds=3, judge_correlation=0.4, cost_usd=1.2)]
    notas = excel.notas_para(con_juez)
    assert len(notas) == 1 and "métrica oficial" in notas[0]
    assert len(excel.notas_para(FILAS)) == 4


def test_sin_generaciones_no_hay_excel():
    with pytest.raises(ValueError):
        excel.construir([], "main")


def test_el_script_escribe_el_xlsx_por_stdout(monkeypatch, capsysbinary):
    monkeypatch.setattr(exportar_excel.export, "filas_de_rama", lambda branch: FILAS)
    assert exportar_excel.main(["--branch", "main"]) == 0
    assert capsysbinary.readouterr().out[:2] == b"PK"  # un .xlsx es un zip


def test_el_script_rechaza_ramas_fuera_de_la_allowlist():
    with pytest.raises(SystemExit):
        exportar_excel.main(["--branch", "otra"])
