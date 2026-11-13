"""Revisa un zip de `doll exportar` contra su floppy antes de compartirlo.

Uso, desde el clon de Doll: uv run python skills/doll-floppies/revisar_zip.py FLOPPY ZIP

Doll ya tapa enlaces y rutas con carpeta hacia lo que no sale. Esto busca lo que no puede tapar solo: el nombre
suelto de cada nota que no sale, en el texto y en los nombres de archivo del zip. Imprime nombres de archivo y
coincidencias, nunca el texto de las notas. Una coincidencia puede ser una palabra común: decide la persona.
"""

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
textos = {n: z.read(n).decode("utf-8", errors="replace") for n in z.namelist() if n.endswith((".md", ".toml", ".html", ".htm"))}
print(f"{len(fuera)} archivos no salen; el zip trae {len(z.namelist())}")

fuera_cf = {r.casefold() for r in fuera}
print("archivos que no debían salir:", [n for n in z.namelist() if n.removeprefix("notas/").casefold() in fuera_cf] or "ninguno")

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
