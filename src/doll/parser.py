"""Puente con `doll-parser`, el filtro en Rust que `uv sync` deja junto al intérprete."""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Fragmento:
    encabezado: str
    linea_ini: int  # 1-indexada, sobre el archivo original
    linea_fin: int
    texto: str


@dataclass(frozen=True)
class Enlace:
    destino: str
    crudo: str  # el `[[...]]` tal como está en la nota


@dataclass(frozen=True)
class Nota:
    fragmentos: list[Fragmento]
    enlaces: list[Enlace]
    frontmatter: dict
    frontmatter_invalido: bool


def analizar(textos: list[str]) -> list[Nota]:
    """Analiza las notas de una sola vez: lanzar un proceso por nota costaría más que parsearlas."""
    # Junto a sys.executable y no por PATH: el servidor MCP no corre dentro de `uv run`.
    binario = Path(sys.executable).with_name("doll-parser.exe" if os.name == "nt" else "doll-parser")
    try:
        salida = subprocess.run([binario], input=json.dumps(textos).encode(), capture_output=True)
    except FileNotFoundError:
        raise SystemExit("Falta doll-parser: corre `uv sync` (requiere cargo)") from None
    if salida.returncode:
        raise SystemExit(f"doll-parser falló: {salida.stderr.decode(errors='replace')}")
    return [
        Nota(
            [Fragmento(**f) for f in n["fragmentos"]],
            [Enlace(**e) for e in n["enlaces"]],
            n["frontmatter"] if isinstance(n["frontmatter"], dict) else {},
            n["frontmatter_invalido"],
        )
        for n in json.loads(salida.stdout)
    ]
