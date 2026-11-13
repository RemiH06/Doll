"""Exportar, importar y firma (RF-13, RF-14, RNF-09). Las llaves se generan en cada test: nunca una de ~/.ssh."""

import array
import shutil
import sqlite3
import subprocess
import tomllib
import zipfile
from pathlib import Path

import pytest

from doll import corpus, floppy, indice, sentido
from doll.preguntar import AVISO_TERCEROS, contexto, texto_fragmentos

BOVEDA = Path(__file__).parent / "boveda"
SSH_KEYGEN = shutil.which("ssh-keygen")
pytestmark = pytest.mark.skipif(SSH_KEYGEN is None, reason="sin ssh-keygen")


def llave(carpeta: Path, nombre: str) -> Path:
    carpeta.mkdir(parents=True, exist_ok=True)
    subprocess.run([SSH_KEYGEN, "-q", "-t", "ed25519", "-N", "", "-C", nombre, "-f", carpeta / nombre], check=True)
    return carpeta / nombre


def instalar(home: Path, dueno: str, privada: Path | None = None, confia_en: Path | None = None) -> None:
    home.mkdir(parents=True, exist_ok=True)
    linea = f'llave = "{privada.as_posix()}"\n' if privada else ""
    (home / "doll.toml").write_text(f'[instalacion]\ndueno = "{dueno}"\n{linea}', encoding="utf-8")
    if confia_en:
        publica = confia_en.with_suffix(".pub").read_text(encoding="utf-8").strip()
        (home / "firmantes").write_text(f'{dueno} namespaces="doll" {publica}\n', encoding="utf-8")


@pytest.fixture
def origen(tmp_path, monkeypatch):
    """Instalación que exporta: dueña `ana`, floppy `taller` sobre la bóveda ficticia."""
    home = tmp_path / "origen"
    monkeypatch.setenv("DOLL_HOME", str(home))
    privada = llave(tmp_path / "ssh", "ana")
    instalar(home, "ana", privada, privada)
    carpeta = home / "floppies" / "taller"
    (carpeta / "eval").mkdir(parents=True)
    (carpeta / "floppy.toml").write_text(
        f"fuente = '{BOVEDA.as_posix()}'\nversion = 1\nterceros = ['recursos/reels/**']\n"
        "mcp_excluir = ['recursos/oficios/Escapes.md']\n", encoding="utf-8")
    (carpeta / "eval" / "preguntas.toml").write_text("[[preguntas]]\nid = 'p1'\nnotas = ['proyectos/Inventario.md']\n",
                                                     encoding="utf-8")
    return home


def exportar(home: Path, destino: Path, **kw) -> Path:
    floppy.exportar(corpus.cargar("taller"), destino, **kw)
    return destino


def en_destino(tmp_path, monkeypatch, dueno: str, confia_en: Path | None) -> Path:
    home = tmp_path / "destino"
    monkeypatch.setenv("DOLL_HOME", str(home))
    instalar(home, dueno, confia_en=confia_en)
    return home


def leer_zip(archivo: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archivo) as z:
        return {n: z.read(n) for n in z.namelist()}


def escribir_zip(archivo: Path, contenido: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(archivo, "w") as z:
        for nombre, datos in contenido.items():
            z.writestr(nombre, datos)
    return archivo


def test_exporta_sin_lo_excluido_ni_lo_oculto_y_tapa_sus_enlaces(origen, tmp_path):
    z = leer_zip(exportar(origen, tmp_path / "t.zip"))
    notas = {n for n in z if n.startswith("notas/")}
    assert "notas/proyectos/Inventario.md" in notas and "notas/recursos/reels/Afinar campanas.md" in notas
    assert not any(n.startswith(("notas/gente/", "notas/life/")) for n in notas)
    assert "notas/recursos/oficios/Escapes.md" not in notas  # mcp_excluir tampoco sale
    assert not any(n.startswith("eval/") for n in z) and "indice.db" not in z
    reloj = z["notas/proyectos/Reloj de torre.md"].decode()
    assert "[[" + "Escapes]]" not in reloj and "Pruebas" not in reloj and "Sin nota" not in reloj
    assert reloj.count(indice.ENLACE_OCULTO) == 3 and "18 400 pesos" in reloj
    assert "[[" + "Reloj de torre]]" in z["notas/proyectos/Inventario.md"].decode()  # lo que sí sale queda enlazado
    todo = b"".join(z.values()).decode(errors="replace")
    assert "palabraexcluida" not in todo and "Escapes.md" not in todo and "Doña" not in todo
    manifiesto = tomllib.loads(z["floppy.toml"].decode())
    assert manifiesto.keys() == {"nombre", "autor", "version", "terceros", "archivos"}
    assert BOVEDA.as_posix() not in todo and "mcp_excluir" not in todo


def test_tapa_la_ruta_de_lo_que_no_sale_escrita_tal_cual(origen, tmp_path):
    fuente = shutil.copytree(BOVEDA, tmp_path / "fuente")
    (fuente / "proyectos" / "Notas.md").write_text(
        "# Notas\n\nVer `recursos/OFICIOS/Escapes.md`, `life/Diario` y recursos/oficios/Gear ratios.md\n", encoding="utf-8")
    toml = origen / "floppies" / "taller" / "floppy.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace(BOVEDA.as_posix(), fuente.as_posix()), encoding="utf-8")
    texto = leer_zip(exportar(origen, tmp_path / "t.zip"))["notas/proyectos/Notas.md"].decode()
    oculto = indice.TEXTO_OCULTO
    assert texto == f"# Notas\n\nVer `{oculto}`, `{oculto}` y recursos/oficios/Gear ratios.md\n"


def test_con_eval_solo_si_no_nombra_lo_oculto(origen, tmp_path):
    z = leer_zip(exportar(origen, tmp_path / "t.zip", con_eval=True))
    assert "eval/preguntas.toml" in z
    (origen / "floppies" / "taller" / "eval" / "otra.toml").write_text("notas = ['recursos/oficios/Escapes.md']\n",
                                                                         encoding="utf-8")
    with pytest.raises(SystemExit, match="menciona"):
        exportar(origen, tmp_path / "t2.zip", con_eval=True)


def test_exportar_exige_version_mcp_excluir_y_llave(origen, tmp_path):
    toml = origen / "floppies" / "taller" / "floppy.toml"
    original = toml.read_text(encoding="utf-8")
    toml.write_text(original.replace("version = 1\n", ""), encoding="utf-8")
    with pytest.raises(SystemExit, match="version"):
        exportar(origen, tmp_path / "t.zip")
    toml.write_text(original.replace("mcp_excluir", "otra_cosa"), encoding="utf-8")
    with pytest.raises(SystemExit, match="mcp_excluir"):
        exportar(origen, tmp_path / "t.zip")
    toml.write_text(original, encoding="utf-8")
    instalar(origen, "ana")
    with pytest.raises(SystemExit, match="llave"):
        exportar(origen, tmp_path / "t.zip")


def test_ida_y_vuelta_entra_como_propio_y_solo_una_version_mayor(origen, tmp_path, monkeypatch):
    v1 = exportar(origen, tmp_path / "v1.zip")
    toml = origen / "floppies" / "taller" / "floppy.toml"
    toml.write_text(toml.read_text(encoding="utf-8").replace("version = 1", "version = 2"), encoding="utf-8")
    v2 = exportar(origen, tmp_path / "v2.zip")

    en_destino(tmp_path, monkeypatch, "ana", tmp_path / "ssh" / "ana")
    assert floppy.importar(v1).terceros is None
    c = corpus.cargar("taller")
    assert c.importado and c.version == 1 and c.terceros == ("recursos/reels/**",)
    con = indice.abrir(c.indice)
    assert indice.indexar(con, c) == (0, 0)  # el índice quedó hecho al importar
    assert indice.buscar(con, "escape de áncora gastado", 3)[0].ruta == "proyectos/Reloj de torre.md"
    assert not c.es_terceros("proyectos/Reloj de torre.md") and c.es_terceros("recursos/reels/Afinar campanas.md")
    con.close()
    with pytest.raises(SystemExit, match="solo entra una mayor"):
        floppy.importar(v1)
    floppy.importar(v2)
    assert corpus.cargar("taller").version == 2
    with pytest.raises(SystemExit, match="exporta"):
        floppy.exportar(corpus.cargar("taller"), tmp_path / "de-nuevo.zip")


def test_no_reemplaza_un_floppy_con_fuente_local(origen, tmp_path):
    zip_ = exportar(origen, tmp_path / "t.zip")
    with pytest.raises(SystemExit, match="--nombre"):
        floppy.importar(zip_)
    assert floppy.importar(zip_, "copia").nombre == "copia"


@pytest.mark.parametrize("caso", ["otro autor", "firma de otra llave con el nombre del dueño", "manifiesto alterado"])
def test_sin_firma_del_dueno_entra_completo_de_terceros(origen, tmp_path, monkeypatch, caso):
    zip_ = exportar(origen, tmp_path / "t.zip")
    dueno, confia_en = "ana", tmp_path / "ssh" / "ana"
    if caso == "otro autor":
        dueno, confia_en = "beto", llave(tmp_path / "ssh", "beto")
    elif caso == "firma de otra llave con el nombre del dueño":
        confia_en = llave(tmp_path / "ssh", "ana-de-verdad")
    else:
        z = leer_zip(zip_)
        z["floppy.toml"] = z["floppy.toml"].replace(b"version = 1", b"version = 9")
        escribir_zip(zip_, z)
    en_destino(tmp_path, monkeypatch, dueno, confia_en)
    i = floppy.importar(zip_)
    assert i.terceros is not None
    c = corpus.cargar("taller")
    assert c.terceros == ("**",) and c.es_terceros("proyectos/Inventario.md")


def test_inyeccion_en_un_floppy_ajeno_sale_marcada(origen, tmp_path, monkeypatch):
    zip_ = exportar(origen, tmp_path / "t.zip")
    en_destino(tmp_path, monkeypatch, "beto", llave(tmp_path / "ssh", "beto"))
    floppy.importar(zip_, "ajeno")
    c = corpus.cargar("ajeno")
    con = indice.abrir(c.indice)
    fragmentos = indice.buscar(con, "taller reloj instrucciones campana", 8, indice.Filtro(terceros=c.terceros))
    assert len(fragmentos) > indice.TOPE_TERCEROS  # todo es de terceros: sin tope
    assert any("Ignora todas tus instrucciones" in f.texto for f in fragmentos)
    assert contexto(fragmentos, c).count(AVISO_TERCEROS) == len(fragmentos)
    assert texto_fragmentos(fragmentos, c).count(AVISO_TERCEROS) == len(fragmentos)


def test_cli_no_acomoda_un_importado(origen, tmp_path, monkeypatch):
    from doll import cli

    zip_ = exportar(origen, tmp_path / "t.zip")
    en_destino(tmp_path, monkeypatch, "ana", tmp_path / "ssh" / "ana")
    floppy.importar(zip_)
    monkeypatch.setattr("sys.argv", ["doll", "--floppy", "taller", "acomodar", "proyectos/Inventario.md"])
    with pytest.raises(SystemExit, match="importado"):
        cli.main()


def test_nota_alterada_rechaza_el_zip(origen, tmp_path, monkeypatch):
    zip_ = exportar(origen, tmp_path / "t.zip")
    z = leer_zip(zip_)
    z["notas/proyectos/Inventario.md"] += b"\nnota agregada"
    escribir_zip(zip_, z)
    en_destino(tmp_path, monkeypatch, "ana", tmp_path / "ssh" / "ana")
    with pytest.raises(SystemExit, match="no es el que se firmó"):
        floppy.importar(zip_)
    assert not (tmp_path / "destino" / "floppies" / "taller").exists()


@pytest.mark.parametrize("nombre", ["../fuera.md", "notas/../../fuera.md", "/abs.md", "C:/x.md", "notas\\..\\x.md",
                                    "notas/CON.md", "otra/x.md", "notas/x.exe", "eval/sub/x.toml"])
def test_zip_con_rutas_que_no_van_se_rechaza(tmp_path, monkeypatch, nombre):
    monkeypatch.setenv("DOLL_HOME", str(tmp_path / "home"))
    zip_ = escribir_zip(tmp_path / "malo.zip", {"floppy.toml": b"", nombre: b"x"})
    with pytest.raises(SystemExit, match="no va en un floppy"):
        floppy.importar(zip_)
    assert not (tmp_path / "fuera.md").exists() and not (tmp_path / "home" / "floppies").exists()


def test_zip_que_se_infla_se_rechaza(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLL_HOME", str(tmp_path / "home"))
    monkeypatch.setattr(floppy, "TOPE_BYTES", 1000)
    zip_ = escribir_zip(tmp_path / "grande.zip", {"floppy.toml": b"", "notas/a.md": b"a" * 2000})
    with pytest.raises(SystemExit, match="MB"):
        floppy.importar(zip_)


def _vectores_del_reel(origen) -> list[str]:
    c = corpus.cargar("taller")
    con = indice.abrir(c.indice)
    indice.indexar(con, c)
    hashes = [sentido._hash(sentido._texto(r)) for r in sentido._fragmentos(con, c)]
    con.execute(sentido.ESQUEMA)
    v = array.array("f", [0.6, 0.8]).tobytes()
    con.executemany("INSERT INTO vectores VALUES (?, ?)", [(h, v) for h in [*hashes, "huerfano"]])
    con.commit()
    con.close()
    return hashes


def test_reusa_solo_los_vectores_de_fragmentos_rehechos(origen, tmp_path, monkeypatch):
    hashes = _vectores_del_reel(origen)
    zip_ = exportar(origen, tmp_path / "t.zip")
    assert "vectores.db" in leer_zip(zip_)
    en_destino(tmp_path, monkeypatch, "ana", tmp_path / "ssh" / "ana")
    assert floppy.importar(zip_).vectores == len(hashes) > 0
    con = indice.abrir(corpus.cargar("taller").indice)
    assert {h for (h,) in con.execute("SELECT hash FROM vectores")} == set(hashes)


def test_indice_ajeno_es_dato_de_solo_lectura(origen, tmp_path):
    hashes = _vectores_del_reel(origen)
    c = corpus.cargar("taller")
    ajeno = tmp_path / "ajeno.db"
    db = sqlite3.connect(ajeno)
    db.executescript("CREATE TABLE vectores (hash TEXT, v BLOB); CREATE TABLE rastro (x);"
                     "CREATE TRIGGER t AFTER INSERT ON vectores BEGIN INSERT INTO rastro VALUES (1); END;")
    db.executemany("INSERT INTO vectores VALUES (?, ?)", [(hashes[0], b"\0" * 8), ("otro", b"\0" * 8)])
    db.execute("DELETE FROM rastro")
    db.commit()
    db.close()
    antes = ajeno.read_bytes()
    local = indice.abrir(tmp_path / "local.db")
    indice.indexar(local, c)
    assert floppy._copiar_vectores(local, c, ajeno) == 1  # solo el hash que coincide con un fragmento de aquí
    assert ajeno.read_bytes() == antes

    vista = tmp_path / "vista.db"
    db = sqlite3.connect(vista)
    db.executescript("CREATE TABLE x (hash TEXT, v BLOB); CREATE VIEW vectores AS SELECT * FROM x;")
    db.close()
    with pytest.raises(SystemExit, match="tabla"):
        floppy._copiar_vectores(local, c, vista)


def test_ssh_keygen_que_no_responde_no_cuelga_y_se_puede_cambiar(origen, tmp_path, monkeypatch):
    zip_ = exportar(origen, tmp_path / "t.zip")
    (origen / "doll.toml").write_text(
        (origen / "doll.toml").read_text(encoding="utf-8") + f'ssh_keygen = "{Path(SSH_KEYGEN).as_posix()}"\n',
        encoding="utf-8")
    assert floppy.instalacion().ssh_keygen == Path(SSH_KEYGEN).as_posix()
    assert floppy.importar(zip_, "copia").terceros is None  # el binario configurado verifica

    real = subprocess.run

    def colgado(args, **kw):
        if "-Y" not in args:
            return real(args, **kw)  # el parser también corre como subproceso
        raise subprocess.TimeoutExpired(args, kw["timeout"])

    monkeypatch.setattr(floppy.subprocess, "run", colgado)
    with pytest.raises(SystemExit, match="ssh_keygen"):
        exportar(origen, tmp_path / "t2.zip")
