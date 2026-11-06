"""Mide un motor de búsqueda contra el set privado de preguntas."""

import json
import time
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Motor = Callable[[str, int], list[tuple[str, int]]]


def _plano(texto: str) -> str:
    return " ".join(texto.split()).casefold()


def cargar_preguntas(archivo: Path) -> list[dict]:
    return tomllib.loads(archivo.read_text(encoding="utf-8"))["p"]


@dataclass
class Reporte:
    por_tipo: dict[str, tuple[int, int]]
    fallos: list[str]
    chars_promedio: float
    segundos_max: float

    @property
    def recall(self) -> float:
        aciertos = sum(a for a, _ in self.por_tipo.values())
        total = sum(t for _, t in self.por_tipo.values())
        return aciertos / total if total else 0.0


def evaluar(preguntas: list[dict], motor: Motor, k: int = 5) -> Reporte:
    """Recall@k por nota; una pregunta cruzada acierta solo si salen todas sus notas."""
    por_tipo: dict[str, tuple[int, int]] = {}
    fallos, chars, tiempos = [], [], []
    for p in preguntas:
        esperadas = set(p.get("notas", ()))
        inicio = time.perf_counter()
        resultado = motor(p["pregunta"], k)
        tiempos.append(time.perf_counter() - inicio)
        if not esperadas:  # no_respondible: mide generación, no recuperación
            continue
        chars.append(sum(c for _, c in resultado))
        acierto = esperadas <= {ruta for ruta, _ in resultado}
        a, t = por_tipo.get(p["tipo"], (0, 0))
        por_tipo[p["tipo"]] = (a + acierto, t + 1)
        if not acierto:
            fallos.append(p["id"])
    return Reporte(por_tipo, fallos, sum(chars) / max(len(chars), 1), max(tiempos, default=0.0))


@dataclass
class ReporteGeneracion:
    con_citas: int
    todas_las_notas: int  # el acierto: una cruzada que cita solo una de sus notas no contestó
    alguna_nota: int  # la métrica de la iteración 1, para comparar
    respondibles: int
    no_encontrado: int
    no_respondibles: int
    segundos_promedio: float
    fallos: list[str]
    traen_evidencia: int = 0  # citar la nota no prueba contestar: el dato etiquetado debe salir
    con_evidencia: int = 0
    sin_evidencia: list[str] = field(default_factory=list)


def _trae_evidencia(p: dict, r) -> bool:
    salida = _plano(" ".join([r.texto, *(c.texto for c in r.citas)]))
    return all(_plano(e) in salida for e in p["evidencia"])


def evaluar_generacion(preguntas: list[dict], responder: Callable, salida: Path) -> ReporteGeneracion:
    """Corre `responder(pregunta)` y guarda cada respuesta completa para leerla: acertar no prueba no inventar."""
    con_citas = todas_las_notas = alguna_nota = no_encontrado = respondibles = no_respondibles = 0
    traen = con_evidencia = 0
    fallos, tiempos, sin_evidencia = [], [], []
    with salida.open("w", encoding="utf-8") as f:
        for p in preguntas:
            inicio = time.perf_counter()
            r = responder(p["pregunta"])
            tiempos.append(time.perf_counter() - inicio)
            citadas = {c.ruta for c in r.citas}
            esperadas = set(p.get("notas", ()))
            if esperadas:
                respondibles += 1
                con_citas += bool(r.citas)
                acierto = esperadas <= citadas
                todas_las_notas += acierto
                alguna_nota += bool(citadas & esperadas)
            else:
                no_respondibles += 1
                acierto = r.no_encontrado
                no_encontrado += acierto
            if not acierto:
                fallos.append(p["id"])
            if p.get("evidencia"):
                con_evidencia += 1
                trae = _trae_evidencia(p, r)
                traen += trae
                if not trae:
                    sin_evidencia.append(p["id"])
            f.write(json.dumps({"id": p["id"], "acierto": acierto, "respuesta": r.texto, "fallo": r.fallo,
                                "descartadas": r.citas_descartadas, "intentos": r.intentos,
                                "citas": [(c.ruta, c.texto) for c in r.citas]}, ensure_ascii=False) + "\n")
            f.flush()
    return ReporteGeneracion(con_citas, todas_las_notas, alguna_nota, respondibles, no_encontrado, no_respondibles,
                             sum(tiempos) / max(len(tiempos), 1), fallos, traen, con_evidencia, sin_evidencia)
