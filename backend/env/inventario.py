"""Inventario sintético: 200 autos generados con semilla fija. Congelado.

Si cambia la semilla o el tamaño, cambian todas las respuestas esperadas de las tareas.
"""
from __future__ import annotations

import random
import unicodedata

from core.contracts import INVENTORY_SEED, INVENTORY_SIZE

CIUDADES = ["CDMX", "GDL", "MTY", "MID", "PUE"]
ESTADO_DE_CIUDAD = {"CDMX": "CDMX", "GDL": "Jalisco", "MTY": "Nuevo Leon", "MID": "Yucatan",
                    "PUE": "Puebla"}
# Nombres con los que un cliente escribe la ciudad; se comparan sin acentos ni mayúsculas
ALIAS_CIUDAD = {
    "cdmx": "CDMX", "ciudad de mexico": "CDMX", "df": "CDMX",
    "gdl": "GDL", "guadalajara": "GDL", "jalisco": "GDL",
    "mty": "MTY", "monterrey": "MTY", "nuevo leon": "MTY",
    "mid": "MID", "merida": "MID", "yucatan": "MID",
    "pue": "PUE", "puebla": "PUE",
}
MODELOS = {"Nissan": ["Versa", "Sentra", "Kicks"], "Toyota": ["Corolla", "RAV4"], "Mazda": ["3", "CX-5"],
           "Volkswagen": ["Jetta", "Vento"], "Honda": ["Civic", "CR-V"]}
ANIO_MIN, ANIO_MAX = 2015, 2024
KM_MIN, KM_MAX = 5_000, 160_000
PRECIO_MIN, PRECIO_MAX, PRECIO_PASO = 180_000, 520_000, 1_000


def sin_acentos(texto: str) -> str:
    """Minúsculas y sin acentos, para comparar lo que escribe el cliente o el modelo."""
    plano = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in plano if not unicodedata.combining(c)).lower().strip()


def normalizar_ciudad(ciudad: str | None) -> str | None:
    """'Guadalajara', 'gdl' o 'Jalisco' -> 'GDL'. None si no es una ciudad con sucursal."""
    return ALIAS_CIUDAD.get(sin_acentos(ciudad or ""))


def construir(semilla: int = INVENTORY_SEED) -> list[dict]:
    rng = random.Random(semilla)
    autos = []
    for i in range(INVENTORY_SIZE):
        marca = rng.choice(list(MODELOS))
        autos.append({"id": f"A{i:03d}", "marca": marca, "modelo": rng.choice(MODELOS[marca]),
                      "anio": rng.randint(ANIO_MIN, ANIO_MAX), "km": rng.randint(KM_MIN, KM_MAX),
                      "precio": rng.randrange(PRECIO_MIN, PRECIO_MAX, PRECIO_PASO),
                      "ciudad": rng.choice(CIUDADES)})
    return autos


INVENTARIO = construir()
POR_ID = {a["id"]: a for a in INVENTARIO}
