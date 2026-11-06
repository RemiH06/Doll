"""Qué notas pertenecen a un corpus. Toda lectura de la bóveda pasa por aquí."""

import os
import re
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
    mcp_excluir: tuple[str, ...] | None = None  # None: sin configurar, el MCP no arranca
    alcances: tuple[tuple[str, str], ...] = ()  # (regex de la pregunta, carpeta a la que se limita)

    def es_terceros(self, relativa: str) -> bool:
        return any(PurePosixPath(relativa).full_match(p) for p in self.terceros)

    def alcance(self, consulta: str) -> tuple[str, tuple[str, ...]]:
        """La consulta sin la frase de alcance y las carpetas a las que se limita: esa frase no es el tema."""
        for regex, carpeta in self.alcances:
            resto, veces = re.subn(regex, " ", consulta, flags=re.IGNORECASE)
            if veces:
                return resto, (carpeta,)
        return consulta, ()

    def incluida(self, relativa: str) -> bool:
        ruta = PurePosixPath(relativa)
        if any(parte.startswith(".") for parte in ruta.parts):
            return False  # .obsidian, .git y similares no son notas
        return not any(ruta.full_match(p) for p in EXCLUIR_SIEMPRE + self.excluir)

    def _archivos(self) -> dict[str, Path]:
        archivos = {}
        for carpeta, subcarpetas, nombres in self.ruta.walk():
            subcarpetas[:] = [s for s in subcarpetas if not s.startswith(".")]  # .git pesa más que las notas
            for nombre in nombres:
                if nombre.endswith(".md"):
                    archivos[(carpeta / nombre).relative_to(self.ruta).as_posix()] = carpeta / nombre
        return archivos

    def notas(self) -> dict[str, str]:
        """Texto de cada nota incluida, por ruta relativa con diagonales."""
        rutas = self._archivos()
        return {
            relativa: rutas[relativa].read_text(encoding="utf-8", errors="replace")
            for relativa in sorted(rutas)
            if self.incluida(relativa)
        }

    def excluidas(self) -> list[str]:
        """Rutas que no se leen, solo para reconocer los enlaces que apuntan a ellas."""
        return sorted(r for r in self._archivos() if not self.incluida(r))


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
    mcp_excluir = datos.get("mcp_excluir")
    alcances = tuple(datos.get("alcances", {}).items())
    for regex, _ in alcances:
        try:
            re.compile(regex)
        except re.error as e:
            raise SystemExit(f"Regex inválida en alcances de {nombre!r}: {e}") from None
    return Corpus(nombre, ruta, tuple(datos.get("excluir", ())), tuple(datos.get("terceros", ())),
                  None if mcp_excluir is None else tuple(mcp_excluir), alcances)
