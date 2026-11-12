"""Propone dónde va una nota. Solo propone; nunca escribe en la bóveda.

Notas de inspiración (`acomodar`): la clase la pone el Baker `clasificador` con el mismo prompt que usa `analizar`
en Bakery (`bakers.clases`), sobre el tema, la idea central, la cuenta y los recursos de la nota. Ese renglón no
lleva el `clase:` ni el `Destino:` que la nota ya traiga: la propuesta no copia la etiqueta vieja. Los enlaces son
los del destino de la clase en la tabla de clases.

Las demás (`acomodar_nota`): carpeta, `tipo`, `estado`, dominio principal, proyecto y enlaces. El modelo lee de cada
nota su título y el inicio del cuerpo, sin frontmatter, ruta ni `[[...]]`. Las opciones salen del índice y se
describen con notas que ya las tienen; las notas que se acomodan no cuentan como ejemplo, porque una nota nueva
todavía no está en la bóveda. Iteración 5: carpeta 26/30; `tipo` 22/30 y proyecto 12/17 quedan bajo el 80 %.
"""

import re
import sqlite3
import tempfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from bakers import clases as tabla_clases
from bakers import core

from doll import indice
from doll.corpus import Corpus

ENLACE = re.compile(r"\[\[([^\]|#\\]+)")
CON_ALIAS = re.compile(r"!?\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
FRONTMATTER = re.compile(r"\A---\r?\n.*?\r?\n---\r?\n", re.DOTALL)
LARGO = 600  # chars de cada nota al modelo; 1500 no subió tipo ni proyecto
PURA = 0.6  # si esta fracción de la carpeta comparte tipo o estado, se toma de ahí: estado 22/30 contra 13 del modelo
EJEMPLOS = 6
ENLACES = 3  # por FTS: precisión 0.31, recall 0.42
NOTA_INDICE = "README.md"  # describe las carpetas de la bóveda
TIPO_PROYECTO, FICHA = "proyecto", "ficha"  # una nota con `ficha:` pertenece a otro proyecto: no es candidata
NINGUNO = "ninguno"
ENTRADA = "Each item is a note from the user's personal Obsidian vault (title, then the start of the body). "


@dataclass(frozen=True)
class Propuesta:
    ruta: str
    clase: str
    enlaces: tuple[str, ...]


@dataclass(frozen=True)
class PropuestaNota:
    ruta: str
    carpeta: str
    tipo: str | None
    estado: str | None
    dominio: str | None  # el principal
    proyecto: str | None
    enlaces: tuple[str, ...]


def acomodar(corpus: Corpus, rutas: list[str]) -> list[Propuesta]:
    """Una propuesta por nota, en el orden de `rutas` (relativas a la bóveda, todas en la carpeta de la tabla de
    clases). Una sola llamada al gateway por cada 40 notas."""
    notas = corpus.notas()
    _existen(rutas, notas)
    carpetas = {PurePosixPath(r).parent for r in rutas}
    if len(carpetas) != 1:
        raise ValueError("Todas las notas deben vivir en la misma carpeta que su tabla de clases")
    tabla = tabla_clases.cargar(corpus.ruta / carpetas.pop())
    bloques = [tabla_clases._de_nota(notas[r])[1] for r in rutas]
    asignadas = tabla_clases.asignar([tabla_clases.linea(b, None) for b in bloques], tabla)
    return [Propuesta(r, clase, tuple(sorted(set(ENLACE.findall(tabla.get(clase, {}).get("destino", ""))))))
            for r, clase in zip(rutas, asignadas)]


def _existen(rutas: list[str], notas: dict[str, str]) -> None:
    faltan = [r for r in rutas if r not in notas]
    if faltan:
        raise ValueError(f"No están en el corpus: {', '.join(faltan)}")


def _visible(texto: str) -> str:
    """El texto sin frontmatter y con cada `[[...]]` como se lee en Obsidian."""
    def leer(m: re.Match) -> str:
        destino, _, seccion = m[1].partition("#")
        return m[2] or PurePosixPath(destino).name or seccion
    return CON_ALIAS.sub(leer, FRONTMATTER.sub("", texto, count=1))


def renglon(texto: str, largo: int = LARGO) -> str:
    """Lo que el modelo lee de una nota, en una línea: una nota ya acomodada no debe traer su respuesta."""
    cuerpo = _visible(texto)
    m = re.search(r"(?m)^# (.+)$", cuerpo)
    titulo = m[1].strip() if m else ""
    if m:
        cuerpo = cuerpo[:m.start()] + cuerpo[m.end():]
    cuerpo = re.sub(r"[#*`|>_-]{2,}", " ", cuerpo)
    return f"{titulo}. {' '.join(cuerpo.split())}"[:largo]


def _carpeta(ruta: str) -> str:
    return f"{PurePosixPath(ruta).parent}/"


def _clasificar(tarea: str, categorias: list[str], renglones: list[str]) -> list[str | None]:
    if len(set(categorias)) < 2:  # el gateway pide al menos dos
        return [categorias[0] if categorias else None] * len(renglones)
    with tempfile.TemporaryDirectory() as d:
        ruta = Path(d) / "notas.txt"
        ruta.write_text("\n".join(renglones), "utf-8")
        res = core.bake("clasificador", tarea, [str(ruta)], categorias)
    salida: list[str | None] = [None] * len(renglones)
    for categoria, por_archivo in res["por_categoria"].items():
        for n in por_archivo[str(ruta)]:
            salida[n - 1] = categoria
    return salida


def _descripcion(indice_texto: str, carpeta: str, fuera: set[str]) -> str:
    """La línea de la nota índice que nombra la carpeta (`X/` o **X:**), o el párrafo bajo su encabezado, sin
    los enlaces a notas de `fuera`: el índice todavía no lista una nota nueva."""
    nombre = PurePosixPath(carpeta).name
    if not nombre:
        return ""
    lineas = FRONTMATTER.sub("", indice_texto, count=1).splitlines()
    texto = ""
    for i, linea in enumerate(lineas):
        if linea.strip() in (f"## {nombre}/", f"## {carpeta}"):
            siguiente = next((x for x in lineas[i + 1:] if x.strip()), "")
            texto = "" if siguiente.lstrip().startswith("-") else siguiente  # una lista es de las subcarpetas
            break
        if re.search(rf"`{re.escape(carpeta)}`|\b{re.escape(nombre)}/|\*\*{re.escape(nombre)}:\*\*", linea):
            texto = linea
            break
    nombres_fuera = {PurePosixPath(r).stem.casefold() for r in fuera}
    texto = CON_ALIAS.sub(lambda m: "" if PurePosixPath(m[1].partition("#")[0]).name.casefold() in nombres_fuera
                          else m[0], texto)
    texto = re.sub(r"(\s*·\s*){2,}", " · ", _visible(texto)).strip(" ·-")
    return " ".join(re.sub(r"[*`]", "", texto).split())[:200]


def _facetas(con: sqlite3.Connection, notas: dict[str, str]) -> dict[str, dict[str, list[str]]]:
    facetas: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for ruta, clave, valor in con.execute("SELECT ruta, clave, valor FROM categorias ORDER BY ruta"):
        if ruta in notas:
            facetas[ruta][clave].append(valor)
    return facetas


def acomodar_nota(con: sqlite3.Connection, corpus: Corpus, rutas: list[str]) -> list[PropuestaNota]:
    """Una propuesta por nota que no es de terceros, en el orden de `rutas`. `con`: el índice al día. Hasta cinco
    llamadas al gateway: carpeta, dominio, proyecto, y `tipo` y `estado` solo para notas de carpetas mezcladas."""
    notas = corpus.notas()
    _existen(rutas, notas)
    if any(corpus.es_terceros(r) for r in rutas):
        raise ValueError("Las notas de terceros se acomodan con su tabla de clases")
    fuera = set(rutas)
    facetas = {r: f for r, f in _facetas(con, notas).items() if r not in fuera}
    renglones = [renglon(notas[r]) for r in rutas]

    def ejemplos(predicado) -> str:
        # Los títulos de notas de terceros no entran al prompt: son texto no confiable.
        rs = [r for r in notas if r not in fuera and not corpus.es_terceros(r) and predicado(r)]
        return "; ".join(PurePosixPath(r).stem for r in rs[:EJEMPLOS])

    def valores(clave: str) -> list[str]:
        return [v for v, _ in Counter(v for f in facetas.values() for v in f.get(clave, [])).most_common()]

    def opciones(clave: str) -> str:
        return "\n".join(f"- {v}. Examples: {ejemplos(lambda r: v in facetas.get(r, {}).get(clave, []))}"
                         for v in valores(clave))

    def usual(carpeta: str, clave: str) -> str | None:
        cuenta = Counter(v for r, f in facetas.items() if _carpeta(r) == carpeta for v in f.get(clave, []))
        if not cuenta:
            return None
        valor, n = cuenta.most_common(1)[0]
        return valor if n / cuenta.total() >= PURA else None

    carpetas = sorted({_carpeta(r) for r in notas})
    indice_texto = notas.get(NOTA_INDICE, "")

    def describir(c: str) -> str:
        en = [f for r, f in facetas.items() if _carpeta(r) == c]
        tipos = [v for v, _ in Counter(v for f in en for v in f.get("tipo", [])).most_common(2)]
        dominios = [v for v, _ in Counter(v for f in en for v in f.get("dominio", [])).most_common(2)]
        texto = f"- {c} ({len(en)} notes; type {', '.join(tipos)}; domain {', '.join(dominios)})"
        if d := _descripcion(indice_texto, c, fuera):
            texto += f". Index says: {d}"
        return f"{texto}. Examples: {ejemplos(lambda r: _carpeta(r) == c)}"

    carpeta = _clasificar(ENTRADA + "Pick the folder where the note belongs.\nFolders:\n"
                          + "\n".join(map(describir, carpetas)), carpetas, renglones)

    def por_carpeta(clave: str, pregunta: str) -> list[str | None]:
        propuesta = [usual(c, clave) for c in carpeta]
        mezcladas = [i for i, v in enumerate(propuesta) if v is None]
        if mezcladas:
            tarea = f"{ENTRADA}{pregunta}\nOptions:\n{opciones(clave)}"
            for i, v in zip(mezcladas, _clasificar(tarea, valores(clave), [renglones[i] for i in mezcladas])):
                propuesta[i] = v
        return propuesta

    tipo = por_carpeta("tipo", "Pick the note type.")
    estado = por_carpeta("estado", "Pick the note status.")
    dominio = _clasificar(f"{ENTRADA}Pick the main domain of the note.\nDomains:\n{opciones('dominio')}",
                          valores("dominio"), renglones)

    proyectos = [r for r, f in facetas.items() if TIPO_PROYECTO in f.get("tipo", [])
                 and not re.search(rf"(?m)^{FICHA}:", (FRONTMATTER.match(notas[r]) or [""])[0])]
    lista = "\n".join(f"- {PurePosixPath(r).stem}: {renglon(notas[r], 140)}" for r in proyectos)
    proyecto = _clasificar(f"{ENTRADA}Pick the project the note belongs to, or {NINGUNO} when it is not about one "
                           f"project. A project's own page belongs to that project.\nProjects:\n{lista}",
                           [*(PurePosixPath(r).stem for r in proyectos), NINGUNO], renglones)

    return [PropuestaNota(r, c, t, e, d, None if p == NINGUNO else p, _enlaces(con, corpus, r, notas[r]))
            for r, c, t, e, d, p in zip(rutas, carpeta, tipo, estado, dominio, proyecto)]


def _enlaces(con: sqlite3.Connection, corpus: Corpus, ruta: str, texto: str) -> tuple[str, ...]:
    """Las notas que FTS encuentra con el inicio de la nota, sin ella ni notas de terceros."""
    vistas: list[str] = []
    for r in indice.buscar(con, renglon(texto, 300), 40):
        if r.ruta != ruta and not corpus.es_terceros(r.ruta) and r.ruta not in vistas:
            vistas.append(r.ruta)
    return tuple(PurePosixPath(r).stem for r in vistas[:ENLACES])


def texto_propuestas(propuestas: list[Propuesta]) -> str:
    return "\n".join(f"{p.ruta}\n  clase: {p.clase}\n  enlaces: {', '.join(f'[[{e}]]' for e in p.enlaces) or '(ninguno)'}"
                     for p in propuestas)


def texto_propuestas_nota(propuestas: list[PropuestaNota]) -> str:
    return "\n".join(
        f"{p.ruta}\n  carpeta: {p.carpeta}\n  tipo: {p.tipo}\n  estado: {p.estado}\n  dominio: {p.dominio}"
        f"\n  proyecto: {p.proyecto or '(ninguno)'}\n  enlaces: {', '.join(f'[[{e}]]' for e in p.enlaces) or '(ninguno)'}"
        f"\n  (tipo y proyecto: baja precisión, revisar)" for p in propuestas)
