"""Qué notas pertenecen a un corpus. Toda lectura de la bóveda pasa por aquí."""

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# Fijas en el código: un corpus.toml incompleto no debe exponer estas carpetas.
EXCLUIR_SIEMPRE = ("gente/**", "life/**")


def home() -> Path:
    return Path(os.environ.get("DOLL_HOME", Path.home() / ".doll"))


@dataclass(frozen=True)
class Corpus:
    nombre: str
    ruta: Path
    excluir: tuple[str, ...] = ()
    terceros: tuple[str, ...] = ()  # notas con texto ajeno: entrada no confiable

    def es_terceros(self, relativa: str) -> bool:
        return any(PurePosixPath(relativa).full_match(p) for p in self.terceros)

    def incluida(self, relativa: str) -> bool:
        ruta = PurePosixPath(relativa)
        if any(parte.startswith(".") for parte in ruta.parts):
            return False  # .obsidian, .git y similares no son notas
        return not any(ruta.full_match(p) for p in EXCLUIR_SIEMPRE + self.excluir)

    def notas(self) -> dict[str, str]:
        """Texto de cada nota incluida, por ruta relativa con diagonales."""
        rutas = {p.relative_to(self.ruta).as_posix(): p for p in self.ruta.rglob("*.md")}
        return {
            relativa: rutas[relativa].read_text(encoding="utf-8", errors="replace")
            for relativa in sorted(rutas)
            if self.incluida(relativa)
        }


def cargar(nombre: str) -> Corpus:
    archivo = home() / "corpus.toml"
    try:
        datos = tomllib.loads(archivo.read_text(encoding="utf-8"))[nombre]
    except FileNotFoundError:
        raise SystemExit(f"No existe {archivo}") from None
    except KeyError:
        raise SystemExit(f"El corpus {nombre!r} no está en {archivo}") from None
    ruta = Path(datos["ruta"])
    if not ruta.is_dir():
        raise SystemExit(f"La ruta del corpus {nombre!r} no existe")
    return Corpus(nombre, ruta, tuple(datos.get("excluir", ())), tuple(datos.get("terceros", ())))
