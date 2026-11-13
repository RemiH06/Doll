"""Exportar e importar floppies, con firma SSH.

El zip lleva `floppy.toml` (manifiesto con el sha256 de cada archivo), su firma `floppy.toml.sig`, `notas/`,
`vectores.db` y, con `--con-eval`, `eval/`. Nunca lleva la fuente, los patrones de exclusión ni `tapar`: dirían qué se
quitó. Lo que `mcp_excluir` oculta tampoco sale, y un enlace a una nota que no sale se tapa en el texto.

Un floppy importado es propio solo si su autor es el dueño de esta instalación (`~/.doll/doll.toml`) y la firma es de
una llave de `~/.doll/firmantes`. Si no, entra completo como de terceros: cada fragmento marcado, sin tope y sin acomodar.
"""

import hashlib
import json
import ntpath
import re
import shutil
import sqlite3
import subprocess
import tempfile
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from doll import corpus as corpus_mod
from doll import indice, sentido
from doll.corpus import FORMATOS, Corpus
from doll.parser import analizar

ESPACIO = "doll"  # namespace de ssh-keygen: una firma de Doll no sirve para git ni para otra cosa
MANIFIESTO = "floppy.toml"
FIRMA = "floppy.toml.sig"
VECTORES = "vectores.db"
TOPE_BYTES = 1 << 30  # descomprimido: un zip chico puede inflarse a mucho más
TOPE_ARCHIVOS = 50_000
TOPE_SSH = 30  # segundos; firmar o verificar tarda menos de uno
WIKILINK = re.compile(r"!?\[\[([^\[\]]*)\]\]")  # también en el frontmatter, que el parser no lee como enlace


@dataclass(frozen=True)
class Instalacion:
    dueno: str
    llave: Path | None  # la privada, en ~/.ssh: solo hace falta para exportar
    ssh_keygen: str | None = None  # otro binario; si no, el del PATH


@dataclass(frozen=True)
class Exportado:
    notas: int
    documentos: int
    vectores: int


@dataclass(frozen=True)
class Importado:
    nombre: str
    terceros: str | None  # por qué entró como de terceros; None si es propio
    vectores: int


def instalacion() -> Instalacion | None:
    archivo = corpus_mod.home() / "doll.toml"
    if not archivo.exists():
        return None
    try:
        datos = tomllib.loads(archivo.read_text(encoding="utf-8")).get("instalacion", {})
    except tomllib.TOMLDecodeError as e:
        raise SystemExit(f"doll.toml inválido: {e}") from None
    dueno, llave = datos.get("dueno"), datos.get("llave")
    if not isinstance(dueno, str) or not re.fullmatch(r"[\w.@-]+", dueno):  # va a allowed_signers: sin espacios
        raise SystemExit("`dueno` en [instalacion] de doll.toml: letras, números, `.`, `@` o `-`")
    return Instalacion(dueno, Path(llave).expanduser() if llave else None, datos.get("ssh_keygen"))


def _ssh_keygen(inst: Instalacion, *args: str | Path, entrada: bytes) -> subprocess.CompletedProcess:
    programa = inst.ssh_keygen or shutil.which("ssh-keygen")
    if programa is None:
        raise SystemExit("Falta ssh-keygen: viene con OpenSSH")
    try:
        return subprocess.run([programa, *map(str, args)], input=entrada, capture_output=True, timeout=TOPE_SSH)
    except subprocess.TimeoutExpired:
        # El OpenSSH de Windows se queda leyendo la entrada dentro de una sesión SSH; el de Git no.
        raise SystemExit(f"ssh-keygen no respondió en {TOPE_SSH} s. Si corres Doll por SSH en Windows, pon"
                         " `ssh_keygen` en [instalacion] de ~/.doll/doll.toml con otro, como el de Git") from None


def _sha(datos: bytes) -> str:
    return hashlib.sha256(datos).hexdigest()


def _toml(valor: str | list[str]) -> str:
    return json.dumps(valor)  # una cadena o lista de cadenas en JSON, con todo escapado, es TOML válido


def _hashes_vector(fragmentos) -> set[str]:
    return {sentido._hash(sentido._texto(r)) for r in fragmentos}


def exportar(corpus: Corpus, destino: Path, con_eval: bool = False) -> Exportado:
    if corpus.importado:
        raise SystemExit("Un floppy importado no se exporta: lo firmarías sin haberlo escrito")
    inst = instalacion()
    if inst is None or inst.llave is None:
        raise SystemExit("Para firmar hacen falta `dueno` y `llave` en [instalacion] de ~/.doll/doll.toml")
    if corpus.mcp_excluir is None:
        raise SystemExit(f"Define mcp_excluir en el floppy {corpus.nombre!r}: lo que no sale por el MCP tampoco sale en el zip")
    if corpus.version is None:
        raise SystemExit(f"Falta `version` en el floppy {corpus.nombre!r}: un entero que subes en cada exportación")

    notas, documentos, excluidas = corpus.leer()
    visible = indice.Filtro(ocultar=corpus.mcp_excluir).admite
    fuera = excluidas + [r for r in [*notas, *documentos] if not visible(r)]
    notas = {r: t for r, t in notas.items() if visible(r)}
    documentos = {r: a for r, a in documentos.items() if visible(r)}
    if documentos and corpus.tapar:
        raise SystemExit("`tapar` no se aplica dentro de un PDF o HTML: este floppy no se exporta")
    frases = indice._patron_tapar(corpus.tapar)
    if frases and (ruta := next((r for r in [*notas, *documentos] if frases.search(r)), None)):
        raise SystemExit(f"El nombre de {ruta} trae una frase de `tapar`: pásala a mcp_excluir")

    nombres = indice._nombres([*notas, *documentos, *fuera])

    def enlace(m: re.Match) -> str:
        destino_ = m[1].split("|")[0].split("#")[0].strip().rstrip("\\").removesuffix(".md")
        ruta = nombres.get(destino_.casefold())
        if not destino_ or ruta in notas or ruta in documentos:
            return m[0]
        # Sin nota destino también: un enlace roto hacia una carpeta que no sale trae el nombre.
        if ruta is None and corpus.incluida(f"{destino_}.md") and visible(f"{destino_}.md"):
            return m[0]
        return indice.ENLACE_OCULTO

    # La ruta de algo que no sale, escrita tal cual (en código, un enlace Markdown, una etiqueta del set). Solo rutas
    # con carpeta: el nombre suelto de una nota es una palabra común; ese lo revisa quien exporta.
    rastros = sorted({r.removesuffix(".md") for r in fuera if "/" in r}, key=len, reverse=True)
    rutas_fuera = re.compile("|".join(re.escape(r) + r"(?:\.md)?" for r in rastros), re.IGNORECASE) if rastros else None

    textos = {}
    for ruta, texto in notas.items():
        texto = WIKILINK.sub(enlace, texto)
        texto = rutas_fuera.sub(indice.TEXTO_OCULTO, texto) if rutas_fuera else texto
        textos[ruta] = frases.sub(indice.TEXTO_OCULTO, texto) if frases else texto
    evals = {f"eval/{a.name}": a.read_text(encoding="utf-8") for a in sorted(corpus.eval.glob("*.toml"))} if con_eval else {}
    for ruta, texto in evals.items():
        if rutas_fuera and (m := rutas_fuera.search(texto)):  # tapada, la etiqueta dejaría el set roto
            raise SystemExit(f"{ruta} menciona {m[0]!r}, que no sale en el zip: quítala del set o exporta sin --con-eval")

    # Solo los vectores del texto que sale, con el hash que calculará quien importe: nada embebido de un enlace tapado.
    con = indice.abrir(corpus.indice)
    indice.indexar(con, corpus)
    queridos = set()
    for (ruta, _), nota in zip(textos.items(), analizar(list(textos.values()))):
        if corpus.es_terceros(ruta):
            queridos |= _hashes_vector(indice.Resultado(ruta, f.encabezado, f.linea_ini, f.linea_fin, f.texto)
                                       for f in nota.fragmentos)
    filas = con.execute("SELECT ruta, encabezado, linea_ini, linea_fin, texto FROM fragmentos")
    queridos |= _hashes_vector(r for r in map(indice.Resultado._make, filas)
                               if r.ruta in documentos and corpus.es_terceros(r.ruta))
    con.execute(sentido.ESQUEMA)
    vectores = [(h, v) for h, v in con.execute("SELECT hash, v FROM vectores") if h in queridos]
    con.close()

    contenido = {f"notas/{r}": t.encode("utf-8") for r, t in textos.items()}
    contenido |= {f"notas/{r}": a.read_bytes() for r, a in documentos.items()}
    contenido |= {r: t.encode("utf-8") for r, t in evals.items()}
    if vectores:
        with tempfile.TemporaryDirectory() as tmp:
            db = sqlite3.connect(Path(tmp) / VECTORES)
            db.execute(sentido.ESQUEMA)
            db.executemany("INSERT INTO vectores VALUES (?, ?)", vectores)
            db.commit()
            db.close()
            contenido[VECTORES] = (Path(tmp) / VECTORES).read_bytes()

    lineas = [f"nombre = {_toml(corpus.nombre)}", f"autor = {_toml(inst.dueno)}", f"version = {corpus.version}",
              f"terceros = {_toml(list(corpus.terceros))}"]
    for ruta, datos in contenido.items():
        lineas += ["", "[[archivos]]", f"ruta = {_toml(ruta)}", f"sha256 = {_toml(_sha(datos))}"]
    manifiesto = ("\n".join(lineas) + "\n").encode("utf-8")
    firma = _ssh_keygen(inst, "-Y", "sign", "-f", inst.llave, "-n", ESPACIO, entrada=manifiesto)
    if firma.returncode:
        raise SystemExit(f"ssh-keygen no firmó: {firma.stderr.decode(errors='replace').strip()}")

    with zipfile.ZipFile(destino, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(MANIFIESTO, manifiesto)
        z.writestr(FIRMA, firma.stdout)
        for ruta, datos in contenido.items():
            z.writestr(ruta, datos)
    return Exportado(len(textos), len(documentos), len(vectores))


def _permitida(nombre: str) -> bool:
    """Solo lo que un zip de Doll lleva, y nada que salga de la carpeta al escribirlo (`..`, `C:`, `CON`)."""
    partes = nombre.split("/")
    segura = (not nombre.startswith("/") and "\\" not in nombre and ":" not in nombre
              and all(p not in ("", ".", "..") and not ntpath.isreserved(p) for p in partes))
    if not segura:
        return False
    if partes[0] == "notas":
        return len(partes) > 1 and nombre.lower().endswith(FORMATOS)
    if partes[0] == "eval":
        return len(partes) == 2 and nombre.endswith(".toml")
    return nombre in (MANIFIESTO, FIRMA, VECTORES)


def _manifiesto(datos: bytes) -> dict:
    try:
        m = tomllib.loads(datos.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        raise SystemExit("Zip rechazado: floppy.toml inválido") from None
    cadenas = lambda xs: isinstance(xs, list) and all(isinstance(x, str) for x in xs)  # noqa: E731
    archivos = m.get("archivos", [])
    if not (isinstance(m.get("nombre"), str) and isinstance(m.get("autor"), str)
            and type(m.get("version")) is int and m["version"] >= 1 and cadenas(m.get("terceros", []))
            and isinstance(archivos, list)
            and all(isinstance(a, dict) and isinstance(a.get("ruta"), str) and isinstance(a.get("sha256"), str)
                    for a in archivos)):
        raise SystemExit("Zip rechazado: al manifiesto le falta nombre, autor, version (entero) o archivos")
    return m


def _por_que_terceros(manifiesto: bytes, firma: bytes | None, autor: str) -> str | None:
    inst = instalacion()
    if inst is None:
        return "esta instalación no tiene dueño en ~/.doll/doll.toml"
    if autor != inst.dueno:
        return f"el autor no es {inst.dueno}"
    if firma is None:
        return "sin firma"
    firmantes = corpus_mod.home() / "firmantes"
    if not firmantes.exists():
        return "falta ~/.doll/firmantes"
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / FIRMA).write_bytes(firma)
        r = _ssh_keygen(inst, "-Y", "verify", "-f", firmantes, "-I", inst.dueno, "-n", ESPACIO, "-s", Path(tmp) / FIRMA,
                        entrada=manifiesto)
    return None if r.returncode == 0 else "firma inválida o de una llave que no está en ~/.doll/firmantes"


def _previo(destino: Path, version: int, propio: bool) -> None:
    """Un importado solo se reemplaza por una versión mayor, y nunca uno propio por uno ajeno."""
    if not destino.exists():
        return
    try:
        datos = tomllib.loads((destino / MANIFIESTO).read_text(encoding="utf-8"))
    except (FileNotFoundError, tomllib.TOMLDecodeError):
        raise SystemExit(f"Ya existe {destino}: importa con --nombre") from None
    if "fuente" in datos:
        raise SystemExit(f"Ya tienes un floppy {destino.name!r} con fuente local: importa con --nombre")
    if datos.get("version", 0) >= version:
        raise SystemExit(f"Ya está la versión {datos.get('version')} de {destino.name!r}: solo entra una mayor")
    if datos.get("propio") and not propio:
        raise SystemExit(f"{destino.name!r} es tuyo y este zip no lo firmaste tú: importa con --nombre")


def _copiar_vectores(con: sqlite3.Connection, corpus: Corpus, archivo: Path) -> int:
    """Solo los vectores cuyo hash coincide con un fragmento de terceros rehecho aquí. El índice ajeno es dato: solo
    lectura, sin funciones en su esquema, y solo se lee una tabla de verdad llamada `vectores`."""
    ajeno = sqlite3.connect(f"{archivo.as_uri()}?mode=ro", uri=True)
    try:
        ajeno.execute("PRAGMA trusted_schema = OFF")
        if ajeno.execute("SELECT type FROM sqlite_schema WHERE name = 'vectores'").fetchone() != ("table",):
            raise SystemExit("Zip rechazado: vectores.db sin tabla `vectores`")
        locales = _hashes_vector(sentido._fragmentos(con, corpus))
        con.execute(sentido.ESQUEMA)
        filas = [(h, v) for h, v in ajeno.execute("SELECT hash, v FROM vectores")
                 if h in locales and isinstance(v, bytes) and v and len(v) % 4 == 0]
    finally:
        ajeno.close()
    if len({len(v) for _, v in filas}) > 1:
        raise SystemExit("Zip rechazado: vectores de tamaños distintos")
    con.executemany("INSERT OR IGNORE INTO vectores VALUES (?, ?)", filas)
    con.commit()
    return len(filas)


def importar(archivo: Path, nombre: str | None = None) -> Importado:
    with zipfile.ZipFile(archivo) as z:
        infos = [i for i in z.infolist() if not i.is_dir()]
        if len(infos) > TOPE_ARCHIVOS or sum(i.file_size for i in infos) > TOPE_BYTES:
            raise SystemExit(f"Zip rechazado: más de {TOPE_ARCHIVOS} archivos o de {TOPE_BYTES >> 20} MB")
        vistos = set()
        for i in infos:
            # Dos nombres que solo difieren en mayúsculas serían el mismo archivo en Windows.
            if not _permitida(i.filename) or i.filename.casefold() in vistos:
                raise SystemExit(f"Zip rechazado: {i.filename!r} no va en un floppy")
            vistos.add(i.filename.casefold())
        presentes = {i.filename for i in infos}
        if MANIFIESTO not in presentes:
            raise SystemExit("Zip rechazado: sin floppy.toml")
        manifiesto = z.read(MANIFIESTO)
        m = _manifiesto(manifiesto)
        archivos = {a["ruta"]: a["sha256"] for a in m["archivos"]}
        if archivos.keys() != presentes - {MANIFIESTO, FIRMA}:
            raise SystemExit("Zip rechazado: sus archivos no son los del manifiesto")

        nombre = corpus_mod.nombre_valido(nombre or m["nombre"])
        terceros = _por_que_terceros(manifiesto, z.read(FIRMA) if FIRMA in presentes else None, m["autor"])
        destino = corpus_mod.floppies() / nombre
        _previo(destino, m["version"], terceros is None)

        corpus_mod.floppies().mkdir(parents=True, exist_ok=True)
        tmp = Path(tempfile.mkdtemp(prefix=".importando-", dir=corpus_mod.home()))  # fuera de floppies/: no se lista
        try:
            for ruta, sha in archivos.items():
                datos = z.read(ruta)
                if _sha(datos) != sha:
                    raise SystemExit(f"Zip rechazado: {ruta} no es el que se firmó")
                (tmp / ruta).parent.mkdir(parents=True, exist_ok=True)
                (tmp / ruta).write_bytes(datos)
            (tmp / "notas").mkdir(exist_ok=True)
            patrones = list(m.get("terceros", [])) if terceros is None else ["**"]
            (tmp / MANIFIESTO).write_text("\n".join([
                "# Importado con `doll importar`: no se edita, se reemplaza al importar una versión mayor.",
                f"autor = {_toml(m['autor'])}", f"version = {m['version']}",
                f"propio = {'false' if terceros else 'true'}", f"terceros = {_toml(patrones)}",
                'incluir = ["**/*"]', "mcp_excluir = []", ""]), encoding="utf-8")
            # El índice de palabras se rehace desde las notas: del ajeno solo se reusan vectores.
            local = Corpus(nombre, tmp / "notas", terceros=tuple(patrones), mcp_excluir=(), incluir=("**/*",))
            con = indice.abrir(tmp / "indice.db")
            indice.indexar(con, local)
            copiados = _copiar_vectores(con, local, tmp / VECTORES) if VECTORES in archivos else 0
            con.close()
            (tmp / VECTORES).unlink(missing_ok=True)
            if destino.exists():
                viejo = Path(tempfile.mkdtemp(prefix=".reemplazado-", dir=corpus_mod.home()))
                try:
                    destino.rename(viejo / nombre)
                except PermissionError:  # Windows no mueve una carpeta con el índice abierto
                    shutil.rmtree(viejo, ignore_errors=True)
                    raise SystemExit(f"{nombre!r} está en uso: cierra las sesiones que lo usan e importa de nuevo") from None
                tmp.rename(destino)
                shutil.rmtree(viejo, ignore_errors=True)
            else:
                tmp.rename(destino)
        except BaseException:
            shutil.rmtree(tmp, ignore_errors=True)
            raise
    return Importado(nombre, terceros, copiados)
