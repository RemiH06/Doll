"""Qué notas pertenecen a un corpus. Toda lectura de la bóveda pasa por aquí.

Cada corpus es un floppy: `~/.doll/floppies/<nombre>/` con `floppy.toml`, `indice.db` y `eval/`. Uno está montado a la
vez (`~/.doll/montado`), y la CLI, el MCP y el panel usan ese salvo que se pida otro por nombre.
"""

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# Fijas en el código: un floppy.toml incompleto no debe exponer estas carpetas.
EXCLUIR_SIEMPRE = ("gente/**", "life/**")


def home() -> Path:
    return Path(os.environ.get("DOLL_HOME", Path.home() / ".doll"))


def floppies() -> Path:
    return home() / "floppies"


def montado() -> str:
    try:
        return (home() / "montado").read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise SystemExit("Ningún floppy montado: corre `doll montar <nombre>`") from None


def montar(nombre: str) -> None:
    cargar(nombre)  # un floppy roto no se monta
    (home() / "montado").write_text(nombre, encoding="utf-8")


def disponibles() -> list[str]:
    return sorted(f.parent.name for f in floppies().glob("*/floppy.toml"))


@dataclass(frozen=True)
class Corpus:
    nombre: str
    ruta: Path
    excluir: tuple[str, ...] = ()
    terceros: tuple[str, ...] = ()  # notas con texto ajeno: entrada no confiable
    mcp_excluir: tuple[str, ...] | None = None  # None: sin configurar, el MCP no arranca
    alcances: tuple[tuple[str, str], ...] = ()  # (regex de la pregunta, carpeta a la que se limita)

    @property
    def carpeta(self) -> Path:
        return floppies() / self.nombre

    @property
    def indice(self) -> Path:
        return self.carpeta / "indice.db"

    @property
    def eval(self) -> Path:
        return self.carpeta / "eval"

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


def cargar(nombre: str | None = None) -> Corpus:
    """El floppy con ese nombre; sin nombre, el montado."""
    nombre = nombre or montado()
    if not re.fullmatch(r"\w[\w.-]*", nombre):  # el nombre arma una ruta: nada de `..` ni diagonales
        raise SystemExit(f"Nombre de floppy inválido: {nombre!r}")
    archivo = floppies() / nombre / "floppy.toml"
    try:
        datos = tomllib.loads(archivo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        viejo = " (corpus.toml ya no se lee: cada tabla pasa a un floppy.toml)" if (home() / "corpus.toml").exists() else ""
        raise SystemExit(f"No existe el floppy {nombre!r}{viejo}") from None
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"floppy.toml de {nombre!r} inválido: {e}") from None
    if "fuente" not in datos:
        raise SystemExit(f"Falta `fuente` en el floppy {nombre!r}")
    ruta = Path(datos["fuente"])
    if not ruta.is_dir():
        raise SystemExit(f"La fuente del floppy {nombre!r} no existe")
    mcp_excluir = datos.get("mcp_excluir")
    alcances = tuple(datos.get("alcances", {}).items())
    for regex, _ in alcances:
        try:
            re.compile(regex)
        except re.error as e:
            raise SystemExit(f"Regex inválida en alcances de {nombre!r}: {e}") from None
    return Corpus(nombre, ruta, tuple(datos.get("excluir", ())), tuple(datos.get("terceros", ())),
                  None if mcp_excluir is None else tuple(mcp_excluir), alcances)
