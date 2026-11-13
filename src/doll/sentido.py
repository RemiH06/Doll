"""Búsqueda por sentido en las notas de terceros (la inspiración), con vectores de bge-m3 por el gateway de Bakery.

Es un modo aparte de `buscar`: la bóveda sigue con FTS, porque ahí los vectores no ganaron (iteración 2.7). En 16
búsquedas de inspiración (iteración 7), recall@5 de 0.71 contra 0.58 de FTS, con el mismo acierto@1 (11/16).
Los vectores viven en el índice, por hash del texto embebido: una nota que no cambia no se vuelve a embeber.
Sin gateway, responde con FTS limitada a las mismas notas y lo dice.
"""

import array
import hashlib
import math
import sqlite3
import sys
from collections import Counter
from dataclasses import replace
from pathlib import PurePosixPath

from bakers import core

from doll import indice
from doll.corpus import Corpus

# Debajo del lote de 8192 tokens del servidor de embeddings. En bge-m3 (SentencePiece) cada token tiene al menos un
# carácter: con 8000 no se pasa, en ningún idioma. Por promedio no alcanza: un PDF con 60 % de texto no ASCII dio
# 8649 tokens en 11 120 caracteres.
TOPE_CHARS = 8_000
ESQUEMA = "CREATE TABLE IF NOT EXISTS vectores (hash TEXT PRIMARY KEY, v BLOB NOT NULL)"
LOTE = 64  # fragmentos por commit: un corte a medias no pierde lo ya calculado
# Más que esto no se embebe dentro de una búsqueda: a ~0.4 s por fragmento son ~80 s, más ~40 s si el modelo está frío,
# debajo de los 300 s con que el panel corta el puente. Arriba, `doll indexar --sentido` aparte.
EN_LINEA = 200


class Faltan(Exception):
    """Demasiados fragmentos sin vector para embeberlos dentro de una búsqueda."""


def _texto(r: indice.Resultado) -> str:
    return f"{PurePosixPath(r.ruta).stem} | {r.encabezado}\n{r.texto}"[:TOPE_CHARS]


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode()).hexdigest()


def _unitario(v: list[float]) -> array.array:
    n = math.sqrt(math.sumprod(v, v)) or 1.0
    return array.array("f", (x / n for x in v))


def _fragmentos(con: sqlite3.Connection, corpus: Corpus) -> list[indice.Resultado]:
    filas = con.execute("SELECT ruta, encabezado, linea_ini, linea_fin, texto FROM fragmentos ORDER BY id")
    return [r for r in map(indice.Resultado._make, filas) if corpus.es_terceros(r.ruta)]


def llenar(con: sqlite3.Connection, corpus: Corpus, tope: int | None = None) -> int:
    """Embebe los fragmentos de terceros que no tienen vector y borra los vectores que ya no son de ninguno.
    Devuelve cuántos embebió. La primera vez tarda (~0.4 s por fragmento en CPU); después, solo lo nuevo.
    Con `tope`, si faltan más, no embebe nada y lanza `Faltan`."""
    con.execute(ESQUEMA)
    textos = {_hash(t): t for t in map(_texto, _fragmentos(con, corpus))}
    hay = {h for (h,) in con.execute("SELECT hash FROM vectores")}
    faltan = [h for h in textos if h not in hay]
    if tope is not None and len(faltan) > tope:
        raise Faltan(f"faltan {len(faltan)} vectores; llénalos con `doll --floppy {corpus.nombre} indexar --sentido`")
    for i in range(0, len(faltan), LOTE):
        lote = faltan[i:i + LOTE]
        vectores = core.embeber([textos[h] for h in lote])
        con.executemany("INSERT INTO vectores VALUES (?, ?)", [(h, _unitario(v).tobytes()) for h, v in zip(lote, vectores)])
        con.commit()
        if len(faltan) > EN_LINEA:  # solo fuera de una búsqueda: un trabajo largo dice por dónde va
            print(f"{i + len(lote)}/{len(faltan)} fragmentos embebidos", file=sys.stderr, flush=True)
    con.executemany("DELETE FROM vectores WHERE hash = ?", [(h,) for h in hay - textos.keys()])
    con.commit()
    return len(faltan)


def buscar(con: sqlite3.Connection, corpus: Corpus, consulta: str, k: int,
           filtro: indice.Filtro = indice.Filtro()) -> tuple[list[indice.Resultado], str | None]:
    """Hasta k fragmentos de notas de terceros, del más cercano en sentido, con el mismo tope por nota que FTS. El
    segundo valor es un aviso si la respuesta salió de FTS: sin gateway, o con más de EN_LINEA fragmentos sin vector."""
    try:
        llenar(con, corpus, EN_LINEA)
        [q] = core.embeber([consulta])
    except (core.BakerError, Faltan) as e:
        fts = indice.buscar(con, consulta, k, replace(filtro, solo=corpus.terceros))
        return fts, f"Sin búsqueda por sentido ({e}): resultados de FTS."
    q = _unitario(q)
    vectores = dict(con.execute("SELECT hash, v FROM vectores"))
    puntajes = []
    for r in _fragmentos(con, corpus):
        if filtro.admite(r.ruta):
            v = array.array("f")
            v.frombytes(vectores[_hash(_texto(r))])
            puntajes.append((math.sumprod(q, v), r))
    puntajes.sort(key=lambda p: -p[0])
    elegidos, por_nota = [], Counter()
    for _, r in puntajes:
        if por_nota[r.ruta] < indice.TOPE_POR_NOTA:
            elegidos.append(r)
            por_nota[r.ruta] += 1
            if len(elegidos) == k:
                break
    return elegidos, None
