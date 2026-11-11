"""Propone dónde va una nota de inspiración: su clase y sus enlaces. Solo propone; nunca escribe en la bóveda.

La clase la pone el Baker `clasificador` con el mismo prompt que usa `analizar` en Bakery (`bakers.clases`), sobre
el tema, la idea central, la cuenta y los recursos de la nota. Ese renglón no lleva el `clase:` ni el `Destino:`
que la nota ya traiga: la propuesta no copia la etiqueta vieja. Los enlaces salen del destino de la clase en la
tabla de clases; si el destino es una carpeta, FTS elige la nota de esa carpeta que más se parece.
"""

import re
import sqlite3
from dataclasses import dataclass
from pathlib import PurePosixPath

from bakers import clases as tabla_clases

from doll.corpus import Corpus
from doll.indice import Filtro, buscar

ENLACE = re.compile(r"\[\[([^\]|#\\]+)")
CARPETA = re.compile(r"`([^`]+)/`")


@dataclass(frozen=True)
class Propuesta:
    ruta: str
    clase: str
    enlaces: tuple[str, ...]


def _enlaces(destino: str, consulta: str, con: sqlite3.Connection) -> tuple[str, ...]:
    enlaces = set(ENLACE.findall(destino))
    for carpeta in CARPETA.findall(destino):
        mejor = buscar(con, consulta, 1, Filtro(solo=(f"**/{carpeta}/*.md",)))
        if mejor:
            enlaces.add(PurePosixPath(mejor[0].ruta).stem)
    return tuple(sorted(enlaces))


def acomodar(corpus: Corpus, rutas: list[str], con: sqlite3.Connection) -> list[Propuesta]:
    """Una propuesta por nota, en el orden de `rutas` (relativas a la bóveda, todas en la carpeta de la tabla de
    clases). Una sola llamada al gateway por cada 40 notas."""
    notas = corpus.notas()
    faltan = [r for r in rutas if r not in notas]
    if faltan:
        raise ValueError(f"No están en el corpus: {', '.join(faltan)}")
    carpetas = {PurePosixPath(r).parent for r in rutas}
    if len(carpetas) != 1:
        raise ValueError("Todas las notas deben vivir en la misma carpeta que su tabla de clases")
    tabla = tabla_clases.cargar(corpus.ruta / carpetas.pop())
    bloques = [tabla_clases._de_nota(notas[r])[1] for r in rutas]
    asignadas = tabla_clases.asignar([tabla_clases.linea(b, None) for b in bloques], tabla)
    return [Propuesta(r, clase, _enlaces(tabla.get(clase, {}).get("destino", ""),
                                         f"{b['tema']} {b.get('idea_central') or ''}", con))
            for r, b, clase in zip(rutas, bloques, asignadas)]


def texto_propuestas(propuestas: list[Propuesta]) -> str:
    return "\n".join(f"{p.ruta}\n  clase: {p.clase}\n  enlaces: {', '.join(f'[[{e}]]' for e in p.enlaces) or '(ninguno)'}"
                     for p in propuestas)
