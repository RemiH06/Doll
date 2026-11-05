"""Línea base: lo que obtendría alguien usando grep con las palabras de la pregunta."""

import re

VACIAS = frozenset(
    """a al algo como con cual cuales cuanto cuantos cuánto cuántos cuántas cuál cuáles
    de del donde dónde e el ella en es esa ese eso esta este esto hay la las le lo los
    me mi mis mí muy o para pero por porque que qué se si sin sobre son su sus te tengo
    tu un una uno unos unas y ya yo""".split()
)


def terminos(consulta: str) -> list[str]:
    palabras = re.findall(r"\w[\w-]*", consulta.lower())
    return list(dict.fromkeys(p for p in palabras if p not in VACIAS and len(p) > 1))


def buscar(consulta: str, notas: dict[str, str], k: int) -> list[tuple[str, int]]:
    """Top k de notas por términos distintos y luego por coincidencias totales.

    Igual que `grep -i`: subcadena literal, sin ignorar acentos. Devuelve (ruta, chars
    de la nota), porque grep da la nota y lo que se lee es la nota completa.
    """
    buscados = terminos(consulta)
    puntajes = []
    for ruta, texto in notas.items():
        minusculas = texto.lower()
        cuentas = [minusculas.count(t) for t in buscados]
        distintos = sum(c > 0 for c in cuentas)
        if distintos:
            puntajes.append((-distintos, -sum(cuentas), ruta))
    return [(ruta, len(notas[ruta])) for _, _, ruta in sorted(puntajes)[:k]]
