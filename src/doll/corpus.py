"""Qué notas pertenecen a un corpus. Toda lectura de la bóveda pasa por aquí.

Cada corpus es un floppy: `~/.doll/floppies/<nombre>/` con `floppy.toml`, `indice.db` y `eval/`. Uno está montado a la
vez (`~/.doll/montado`), y la CLI, el MCP y el panel usan ese salvo que se pida otro por nombre. Uno propio lee su
`fuente`; uno importado (`doll importar`) no tiene `fuente` y lee su carpeta `notas/`.
"""

import os
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# Fijas en el código: un floppy.toml incompleto no debe exponer estas carpetas.
EXCLUIR_SIEMPRE = ("gente/**", "life/**")
FORMATOS = (".md", ".html", ".htm", ".pdf")  # Markdown va a doll-parser; los demás, a `extraer`
# En un importado, el texto ya extraído de un documento (`a.pdf.json` es `a.pdf`): el PDF original no viaja.
EXTRAIDOS = tuple(f"{f}.json" for f in FORMATOS if f != ".md")


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
    incluir: tuple[str, ...] = ("**/*.md",)  # qué archivos de la fuente entran, antes de `excluir`
    tapar: tuple[str, ...] = ()  # frases que no se guardan en el índice (datos personales dentro de un documento)
    version: int | None = None  # sube en cada exportación; un importado solo se reemplaza por una mayor
    importado: bool = False  # copia fija de `notas/`: no se acomoda ni se vuelve a exportar

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

    @property
    def _formatos(self) -> tuple[str, ...]:
        return FORMATOS + EXTRAIDOS if self.importado else FORMATOS

    def _recorrer(self):
        for carpeta, subcarpetas, nombres in self.ruta.walk():
            subcarpetas[:] = [s for s in subcarpetas if not s.startswith(".")]  # .git pesa más que las notas
            for nombre in nombres:
                if nombre.lower().endswith(self._formatos):  # antes de armar rutas: una fuente puede traer miles de archivos
                    yield carpeta / nombre

    def _archivos(self) -> dict[str, Path]:
        archivos = {}
        for patron in self.incluir:
            # Con `**` se recorre todo, podando carpetas ocultas que glob sí recorrería. Sin `**`, glob solo abre
            # las carpetas del patrón: una fuente grande (todo iroFactory) no se recorre en cada `buscar`.
            for archivo in self._recorrer() if "**" in patron else self.ruta.glob(patron):
                if not archivo.name.lower().endswith(self._formatos):
                    continue
                relativa = archivo.relative_to(self.ruta).as_posix()
                if PurePosixPath(relativa).full_match(patron, case_sensitive=False) and archivo.is_file():
                    if relativa.lower().endswith(EXTRAIDOS):
                        relativa = relativa[:-len(".json")]
                    archivos[relativa] = archivo
        return archivos

    def leer(self) -> tuple[dict[str, str], dict[str, Path], list[str]]:
        """De una sola pasada por la fuente: texto de cada nota Markdown, HTML y PDF por extraer, y excluidas."""
        archivos = self._archivos()
        notas, documentos, excluidas = {}, {}, []
        for relativa in sorted(archivos):
            if not self.incluida(relativa):
                excluidas.append(relativa)  # no se leen: solo sirven para reconocer enlaces que apuntan a ellas
            elif relativa.lower().endswith(".md"):
                notas[relativa] = archivos[relativa].read_text(encoding="utf-8", errors="replace")
            else:
                documentos[relativa] = archivos[relativa]  # se extraen solo si cambiaron: extraer un PDF tarda
        return notas, documentos, excluidas

    def notas(self) -> dict[str, str]:
        """Texto de cada nota Markdown incluida, por ruta relativa con diagonales."""
        return self.leer()[0]


def nombre_valido(nombre: str) -> str:
    if not re.fullmatch(r"\w[\w.-]*", nombre):  # el nombre arma una ruta: nada de `..` ni diagonales
        raise SystemExit(f"Nombre de floppy inválido: {nombre!r}")
    return nombre


def cargar(nombre: str | None = None) -> Corpus:
    """El floppy con ese nombre; sin nombre, el montado."""
    nombre = nombre_valido(nombre or montado())
    archivo = floppies() / nombre / "floppy.toml"
    try:
        datos = tomllib.loads(archivo.read_text(encoding="utf-8"))
    except FileNotFoundError:
        viejo = " (corpus.toml ya no se lee: cada tabla pasa a un floppy.toml)" if (home() / "corpus.toml").exists() else ""
        raise SystemExit(f"No existe el floppy {nombre!r}{viejo}") from None
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"floppy.toml de {nombre!r} inválido: {e}") from None
    importado = "fuente" not in datos and (archivo.parent / "notas").is_dir()
    if "fuente" not in datos and not importado:
        raise SystemExit(f"Falta `fuente` en el floppy {nombre!r}")
    ruta = archivo.parent / "notas" if importado else Path(datos["fuente"])
    if not ruta.is_dir():
        raise SystemExit(f"La fuente del floppy {nombre!r} no existe")
    version = datos.get("version")
    if version is not None and (type(version) is not int or version < 1):
        raise SystemExit(f"`version` en el floppy {nombre!r}: un entero desde 1")
    mcp_excluir = datos.get("mcp_excluir")
    alcances = tuple(datos.get("alcances", {}).items())
    for regex, _ in alcances:
        try:
            re.compile(regex)
        except re.error as e:
            raise SystemExit(f"Regex inválida en alcances de {nombre!r}: {e}") from None
    incluir = tuple(datos.get("incluir", ("**/*.md",)))
    if not incluir:
        raise SystemExit(f"`incluir` vacío en el floppy {nombre!r}: no entraría ningún archivo")
    for patron in incluir:
        if PurePosixPath(patron).is_absolute() or ".." in PurePosixPath(patron).parts or ":" in patron:
            raise SystemExit(f"`incluir` sale de la fuente en el floppy {nombre!r}: {patron!r}")
    tapar = tuple(datos.get("tapar", ()))
    if any(not isinstance(t, str) or len(t.strip()) < 3 for t in tapar):
        raise SystemExit(f"`tapar` en el floppy {nombre!r}: cada frase, de 3 caracteres o más")
    return Corpus(nombre, ruta, tuple(datos.get("excluir", ())), tuple(datos.get("terceros", ())),
                  None if mcp_excluir is None else tuple(mcp_excluir), alcances, incluir, tapar, version, importado)
