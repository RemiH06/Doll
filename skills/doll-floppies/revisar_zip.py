"""Revisa un zip de `doll exportar` contra su floppy antes de compartirlo.

Uso, desde el clon de Doll: uv run python skills/doll-floppies/revisar_zip.py FLOPPY ZIP

Doll ya tapa enlaces y rutas con carpeta hacia lo que no sale, y las frases de `tapar`. Esto comprueba que ninguna
frase de `tapar` sobrevive (en notas, texto extraído de documentos y nombres de archivo) y busca lo que Doll no puede
tapar solo: el nombre suelto de cada nota que no sale. Imprime nombres de archivo y coincidencias, nunca el texto de
las notas. Una coincidencia de nombre puede ser una palabra común: decide la persona.
"""

import json
import re
import sqlite3
import sys
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath

from doll import corpus, indice

sys.stdout.reconfigure(encoding="utf-8")
c = corpus.cargar(sys.argv[1])
notas, documentos, excluidas = c.leer()
visible = indice.Filtro(ocultar=c.mcp_excluir or ()).admite
fuera = excluidas + [r for r in [*notas, *documentos] if not visible(r)]
z = zipfile.ZipFile(sys.argv[2])


def texto(nombre: str) -> str:
    crudo = z.read(nombre).decode("utf-8", errors="replace")
    if not nombre.endswith(corpus.EXTRAIDOS):
        return crudo
    # Decodificado: en el JSON un salto de línea entre dos palabras de una frase es `\n` y no se reconocería.
    datos = json.loads(crudo)
    return "\n".join([datos["titulo"] or "", *(f"{f['encabezado']}\n{f['texto']}" for f in datos["fragmentos"])])


textos = {n: texto(n) for n in z.namelist() if n.endswith((".md", ".toml", ".html", ".htm", *corpus.EXTRAIDOS))}
print(f"{len(fuera)} archivos no salen; el zip trae {len(z.namelist())}")

fuera_cf = {r.casefold() for r in fuera}
de_fuera = [n for n in z.namelist() if n.removeprefix("notas/").removesuffix(".json").casefold() in fuera_cf]
print("archivos que no debían salir:", de_fuera or "ninguno")
print("documentos originales en el zip:", [n for n in z.namelist() if n.endswith(corpus.FORMATOS[1:])] or "ninguno")

frases = indice._patron_tapar(c.tapar)
tapadas = [n for n, t in textos.items() if frases and frases.search(f"{n}\n{t}")]
tapadas += [n for n in z.namelist() if n not in textos and frases and frases.search(n)]
print(f"frases de `tapar` ({len(c.tapar)}) que sobreviven:", tapadas or "ninguna")

nombres = indice._nombres([*notas, *documentos, *fuera])
vivos = [n for n, t in textos.items() for d in re.findall(r"\[\[([^\[\]]*)\]\]", t)
         if nombres.get(d.split("|")[0].split("#")[0].strip().rstrip("\\").removesuffix(".md").casefold()) in fuera]
print("enlaces vivos hacia lo que no sale:", vivos or "ninguno")

coincide = defaultdict(list)
for stem in {PurePosixPath(r).stem.casefold() for r in fuera if len(PurePosixPath(r).stem) >= 4}:
    for n, t in textos.items():
        if re.search(rf"(?<!\w){re.escape(stem)}(?!\w)", f"{n}\n{t}".casefold()):
            coincide[stem].append(n)
print(f"nombres de lo que no sale que aparecen: {len(coincide)}")
for stem, archivos in sorted(coincide.items(), key=lambda x: -len(x[1])):
    print(f"  {stem!r}: {len(archivos)} archivos, p. ej. {archivos[0]}")

if "vectores.db" in z.namelist():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "v.db").write_bytes(z.read("vectores.db"))
        con = sqlite3.connect(Path(tmp) / "v.db")
        print("vectores.db:", [n for (n,) in con.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")])
        con.close()
