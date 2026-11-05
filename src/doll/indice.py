"""Índice SQLite: fragmentos por encabezado y búsqueda FTS5."""

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from doll.corpus import Corpus
from doll.grep import terminos

ENCABEZADO = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$")
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
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    titulo, encabezado, texto, tokenize = 'unicode61 remove_diacritics 2'
);
"""
PESOS = (5.0, 3.0, 1.0)  # titulo, encabezado, texto


@dataclass(frozen=True)
class Fragmento:
    encabezado: str
    linea_ini: int  # 1-indexada, sobre el archivo original
    linea_fin: int
    texto: str


@dataclass(frozen=True)
class Resultado:
    ruta: str
    encabezado: str
    linea_ini: int
    linea_fin: int
    texto: str


def partir(texto: str) -> list[Fragmento]:
    """Parte una nota por encabezados, sin frontmatter y sin leer `#` en bloques de código."""
    lineas = texto.splitlines()
    inicio = 0
    if lineas and lineas[0].strip() == "---":
        cierre = next((i for i, l in enumerate(lineas[1:], 1) if l.strip() == "---"), None)
        if cierre is not None:
            inicio = cierre + 1

    fragmentos: list[Fragmento] = []
    ruta_titulos: list[tuple[int, str]] = []
    actual: list[str] = []
    primera = inicio
    en_codigo = False

    def cerrar(fin: int) -> None:
        contenido = "\n".join(actual).strip()
        if contenido:
            nombre = " > ".join(t for _, t in ruta_titulos)
            fragmentos.append(Fragmento(nombre, primera + 1, fin, contenido))
        actual.clear()

    for i, linea in enumerate(lineas[inicio:], inicio):
        if linea.lstrip().startswith(("```", "~~~")):
            en_codigo = not en_codigo
        marca = None if en_codigo else ENCABEZADO.match(linea)
        if marca:
            cerrar(i)
            primera = i
            nivel = len(marca[1])
            ruta_titulos = [(n, t) for n, t in ruta_titulos if n < nivel] + [(nivel, marca[2])]
        actual.append(linea)
    cerrar(len(lineas))
    return fragmentos


def abrir(archivo: Path) -> sqlite3.Connection:
    archivo.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(archivo)
    con.executescript(ESQUEMA)
    return con


def _quitar(con: sqlite3.Connection, ruta: str) -> None:
    con.execute("DELETE FROM fts WHERE rowid IN (SELECT id FROM fragmentos WHERE ruta = ?)", (ruta,))
    con.execute("DELETE FROM fragmentos WHERE ruta = ?", (ruta,))
    con.execute("DELETE FROM notas WHERE ruta = ?", (ruta,))


def indexar(con: sqlite3.Connection, corpus: Corpus) -> tuple[int, int]:
    """Sincroniza el índice con el corpus. Devuelve (notas reindexadas, notas quitadas)."""
    notas = corpus.notas()
    previas = dict(con.execute("SELECT ruta, hash FROM notas"))
    # Una nota borrada o recién excluida no puede quedarse en el índice.
    sobrantes = previas.keys() - notas.keys()
    cambiadas = 0
    with con:
        for ruta in sobrantes:
            _quitar(con, ruta)
        for ruta, texto in notas.items():
            huella = hashlib.sha256(texto.encode()).hexdigest()
            if previas.get(ruta) == huella:
                continue
            cambiadas += 1
            _quitar(con, ruta)
            con.execute("INSERT INTO notas VALUES (?, ?)", (ruta, huella))
            titulo = PurePosixPath(ruta).stem
            for f in partir(texto):
                fila = con.execute(
                    "INSERT INTO fragmentos (ruta, encabezado, linea_ini, linea_fin, texto)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (ruta, f.encabezado, f.linea_ini, f.linea_fin, f.texto),
                )
                con.execute(
                    "INSERT INTO fts (rowid, titulo, encabezado, texto) VALUES (?, ?, ?, ?)",
                    (fila.lastrowid, titulo, f.encabezado, f.texto),
                )
    return cambiadas, len(sobrantes)


def buscar(con: sqlite3.Connection, consulta: str, k: int) -> list[Resultado]:
    # Entre comillas, cada término es texto: la consulta no puede inyectar sintaxis FTS5.
    expresion = " OR ".join(f'"{t}"' for t in terminos(consulta))
    if not expresion:
        return []
    filas = con.execute(
        "SELECT f.ruta, f.encabezado, f.linea_ini, f.linea_fin, f.texto"
        " FROM fts JOIN fragmentos f ON f.id = fts.rowid"
        f" WHERE fts MATCH ? ORDER BY bm25(fts, {', '.join(map(str, PESOS))}) LIMIT ?",
        (expresion, k),
    )
    return [Resultado(*fila) for fila in filas]
