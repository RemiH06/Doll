"""Índice SQLite: fragmentos por encabezado y búsqueda FTS5."""

import hashlib
import json
import sqlite3
import sys
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import NamedTuple

from doll.corpus import Corpus
from doll.grep import terminos
from doll.parser import analizar

# El índice se rehace solo: las notas no cambiaron, pero lo que se guarda de ellas sí.
VERSION = 2
TABLAS = ("notas", "fragmentos", "fts", "enlaces", "categorias", "firma")
ESQUEMA = """
CREATE TABLE IF NOT EXISTS notas (ruta TEXT PRIMARY KEY, hash TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS fragmentos (
    id INTEGER PRIMARY KEY,
    ruta TEXT NOT NULL REFERENCES notas(ruta),
    encabezado TEXT NOT NULL,
    linea_ini INTEGER NOT NULL,
    linea_fin INTEGER NOT NULL,
    texto TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS fragmentos_ruta ON fragmentos(ruta);
CREATE TABLE IF NOT EXISTS enlaces (
    origen TEXT NOT NULL,
    destino TEXT NOT NULL,  -- siempre una nota indexada: nunca el nombre de una excluida
    PRIMARY KEY (origen, destino)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS enlaces_destino ON enlaces(destino);
CREATE TABLE IF NOT EXISTS categorias (
    ruta TEXT NOT NULL,
    clave TEXT NOT NULL,
    valor TEXT NOT NULL,
    PRIMARY KEY (ruta, clave, valor)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS categorias_valor ON categorias(clave, valor);
CREATE TABLE IF NOT EXISTS firma (valor TEXT NOT NULL);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    titulo, encabezado, texto, tokenize = 'unicode61 remove_diacritics 2'
);
"""
PESOS = (5.0, 3.0, 1.0)  # titulo, encabezado, texto
CAMPOS = ("tipo", "estado", "dominio")  # los valores salen de las notas, no del código
ENLACE_OCULTO = "[[…]]"  # sin letras: no debe ser un término buscable
TOPE_POR_NOTA = 2  # si no, varios fragmentos de una nota llenan el top k
VECINAS = 3


class Resultado(NamedTuple):
    ruta: str
    encabezado: str
    linea_ini: int
    linea_fin: int
    texto: str


@dataclass(frozen=True)
class Filtro:
    tipo: str | None = None
    dominio: str | None = None
    ocultar: tuple[str, ...] = ()  # patrones de ruta, para lo que no debe salir por el MCP


def abrir(archivo: Path) -> sqlite3.Connection:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(archivo)
    if con.execute("PRAGMA user_version").fetchone() != (VERSION,):
        con.executescript("".join(f"DROP TABLE IF EXISTS {t};" for t in TABLAS))
        con.execute(f"PRAGMA user_version = {VERSION}")
    con.executescript(ESQUEMA)
    return con


def _quitar(con: sqlite3.Connection, ruta: str) -> None:
    con.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM fragmentos WHERE ruta = ?)", (ruta,))
    con.execute("DELETE FROM fragmentos WHERE ruta = ?", (ruta,))
    con.execute("DELETE FROM categorias WHERE ruta = ?", (ruta,))
    con.execute("DELETE FROM notas WHERE ruta = ?", (ruta,))


def _tapar(cadena: str, crudos: set[str]) -> str:
    for crudo in crudos:
        cadena = cadena.replace(crudo, ENLACE_OCULTO)
    return cadena


def _nombres(rutas: Iterable[str]) -> dict[str, str]:
    """Cada forma de enlazar una nota: nombre, o ruta desde cualquier carpeta. Como en Obsidian, gana la ruta más corta."""
    nombres: dict[str, str] = {}
    for ruta in sorted(rutas, key=lambda r: (r.count("/"), r)):
        partes = ruta.removesuffix(".md").casefold().split("/")
        for i in range(len(partes)):
            nombres.setdefault("/".join(partes[i:]), ruta)
    return nombres


def _categorias(frontmatter: dict) -> list[tuple[str, str]]:
    pares = []
    for campo in CAMPOS:
        valor = frontmatter.get(campo)
        valores = valor if isinstance(valor, list) else [valor]
        pares += [(campo, str(v)) for v in valores if v is not None]
    return list(dict.fromkeys(pares))


def _firma(notas: dict[str, str], excluidas: list[str]) -> str:
    """Todo lo que cambia el índice: las notas y qué queda fuera, porque un enlace se tapa según eso."""
    return hashlib.sha256(json.dumps([notas, excluidas]).encode()).hexdigest()


def indexar(con: sqlite3.Connection, corpus: Corpus) -> tuple[int, int]:
    """Sincroniza el índice con el corpus. Devuelve (notas reindexadas, notas quitadas)."""
    notas = corpus.notas()
    excluidas = corpus.excluidas()
    firma = _firma(notas, excluidas)
    if con.execute("SELECT 1 FROM firma WHERE valor = ?", (firma,)).fetchone():
        return 0, 0  # el camino de cada `buscar`: sin lanzar el parser

    previas = dict(con.execute("SELECT ruta, hash FROM notas"))
    # Una nota borrada o recién excluida no puede quedarse en el índice.
    sobrantes = previas.keys() - notas.keys()
    nombres = _nombres([*notas, *excluidas])
    analizadas = analizar(list(notas.values()))
    cambiadas = 0
    with con:
        for ruta in sobrantes:
            _quitar(con, ruta)
        # Se rehace completa: un enlace depende de qué notas existan, no solo de su origen.
        con.execute("DELETE FROM enlaces")
        for (ruta, texto), nota in zip(notas.items(), analizadas):
            if nota.frontmatter_invalido:
                print(f"Aviso: frontmatter inválido en {ruta}", file=sys.stderr)
            tapar: set[str] = set()
            for enlace in nota.enlaces:
                sin_md = enlace.destino.removesuffix(".md")
                destino = nombres.get(sin_md.casefold())
                if destino in notas:
                    if destino != ruta:
                        con.execute("INSERT OR IGNORE INTO enlaces VALUES (?, ?)", (ruta, destino))
                # Sin nota destino también: un enlace roto hacia una carpeta excluida trae el nombre.
                elif destino or not corpus.incluida(f"{sin_md}.md"):
                    tapar.add(enlace.crudo)

            # El hash incluye lo tapado: si una nota enlazada sale del corpus, esta debe rehacerse.
            huella = hashlib.sha256("\0".join([texto, *sorted(tapar)]).encode()).hexdigest()
            if previas.get(ruta) == huella:
                continue
            cambiadas += 1
            _quitar(con, ruta)
            con.execute("INSERT INTO notas VALUES (?, ?)", (ruta, huella))
            con.executemany("INSERT INTO categorias VALUES (?, ?, ?)",
                            [(ruta, *par) for par in _categorias(nota.frontmatter)])
            titulo = PurePosixPath(ruta).stem
            for f in nota.fragmentos:
                encabezado, cuerpo = _tapar(f.encabezado, tapar), _tapar(f.texto, tapar)
                fila = con.execute(
                    "INSERT INTO fragmentos (ruta, encabezado, linea_ini, linea_fin, texto)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (ruta, encabezado, f.linea_ini, f.linea_fin, cuerpo),
                )
                con.execute(
                    "INSERT INTO fts (rowid, titulo, encabezado, texto) VALUES (?, ?, ?, ?)",
                    (fila.lastrowid, titulo, encabezado, cuerpo),
                )
        con.execute("DELETE FROM firma")
        con.execute("INSERT INTO firma VALUES (?)", (firma,))
    return cambiadas, len(sobrantes)


def _vecinas(con: sqlite3.Connection, rutas: Collection[str]) -> set[str]:
    """Notas a un salto, en las dos direcciones: quien enlaza a una nota también habla de ella."""
    marcas = ", ".join("?" * len(rutas))
    filas = con.execute(
        f"SELECT destino FROM enlaces WHERE origen IN ({marcas})"
        f" UNION SELECT origen FROM enlaces WHERE destino IN ({marcas})",
        [*rutas, *rutas],
    )
    return {ruta for (ruta,) in filas} - set(rutas)


def buscar(con: sqlite3.Connection, consulta: str, k: int, filtro: Filtro = Filtro()) -> list[Resultado]:
    """Hasta k fragmentos, con tope por nota, más un fragmento de hasta VECINAS notas enlazadas."""
    # Entre comillas, cada término es texto: la consulta no puede inyectar sintaxis FTS5.
    expresion = " OR ".join(f'"{t}"' for t in terminos(consulta))
    if not expresion:
        return []
    condiciones, valores = "", [expresion]
    for clave, valor in (("tipo", filtro.tipo), ("dominio", filtro.dominio)):
        if valor is not None:
            condiciones += " AND f.ruta IN (SELECT ruta FROM categorias WHERE clave = ? AND valor = ?)"
            valores += [clave, valor]
    filas = con.execute(
        "SELECT f.ruta, f.encabezado, f.linea_ini, f.linea_fin, f.texto"
        " FROM fts JOIN fragmentos f ON f.id = fts.rowid"
        f" WHERE fts MATCH ?{condiciones} ORDER BY bm25(fts, {', '.join(map(str, PESOS))})",
        valores,
    )
    # Sin LIMIT: el orden de bm25 decide tanto el tope como qué fragmento de cada vecina entra.
    candidatos = [r for r in map(Resultado._make, filas)
                  if not any(PurePosixPath(r.ruta).full_match(p) for p in filtro.ocultar)]
    elegidos: list[Resultado] = []
    por_nota: Counter[str] = Counter()
    resto = []
    for r in candidatos:
        if len(elegidos) < k and por_nota[r.ruta] < TOPE_POR_NOTA:
            elegidos.append(r)
            por_nota[r.ruta] += 1
        else:
            resto.append(r)
    if not elegidos:
        return []
    vecinas = _vecinas(con, list(por_nota))
    for r in resto:
        if r.ruta in vecinas and len(elegidos) < k + VECINAS:
            elegidos.append(r)
            vecinas.discard(r.ruta)
    return elegidos
