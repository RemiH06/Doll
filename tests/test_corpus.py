from pathlib import Path

import pytest

from doll import corpus
from doll.corpus import Corpus

BOVEDA = Path(__file__).parent / "boveda"


def test_excluye_carpetas_privadas_sin_configuracion():
    notas = Corpus("t", BOVEDA).notas()
    assert not any(r.startswith(("gente/", "life/")) for r in notas)
    assert not any("palabraexcluida" in texto for texto in notas.values())


def test_exclusion_propia_y_subcarpetas():
    notas = Corpus("t", BOVEDA, ("recursos/reels/**", "proyectos/Autómata.md")).notas()
    assert "proyectos/Autómata.md" not in notas
    assert not any(r.startswith("recursos/reels/") for r in notas)
    assert "recursos/oficios/Escapes.md" in notas


def test_ignora_carpetas_ocultas(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    (tmp_path / ".obsidian" / "x.md").write_text("oculta", encoding="utf-8")
    (tmp_path / "y.md").write_text("visible", encoding="utf-8")
    assert list(Corpus("t", tmp_path).notas()) == ["y.md"]


def test_alcance_quita_la_frase_y_da_la_carpeta():
    c = Corpus("t", BOVEDA, alcances=((r"notas? de oficios", "recursos/oficios/**"),))
    assert c.alcance("Hay NOTAS de oficios sobre campanas?") == ("Hay   sobre campanas?", ("recursos/oficios/**",))
    assert c.alcance("Qué oficios conozco?") == ("Qué oficios conozco?", ())


def floppy(home: Path, nombre: str, extra: str = "") -> None:
    (home / "floppies" / nombre).mkdir(parents=True)
    (home / "floppies" / nombre / "floppy.toml").write_text(f"fuente = '{BOVEDA.as_posix()}'\n{extra}", encoding="utf-8")


def test_regex_invalida_en_alcances_no_arranca(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLL_HOME", str(tmp_path))
    floppy(tmp_path, "b", "[alcances]\n'(' = 'x/**'\n")
    with pytest.raises(SystemExit, match="Regex inválida"):
        corpus.cargar("b")


def test_sin_nombre_usa_el_montado_y_sus_rutas(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLL_HOME", str(tmp_path))
    floppy(tmp_path, "a")
    floppy(tmp_path, "b", 'excluir = ["proyectos/**"]\n')
    with pytest.raises(SystemExit, match="montar"):
        corpus.cargar()
    corpus.montar("b")
    c = corpus.cargar()
    assert c.nombre == "b" and c.excluir == ("proyectos/**",)
    assert c.indice == tmp_path / "floppies" / "b" / "indice.db" and c.eval == tmp_path / "floppies" / "b" / "eval"
    assert corpus.cargar("a").nombre == "a" and corpus.disponibles() == ["a", "b"]


def test_no_monta_un_floppy_roto_ni_un_nombre_con_ruta(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLL_HOME", str(tmp_path))
    floppy(tmp_path, "a")
    corpus.montar("a")
    (tmp_path / "floppies" / "roto").mkdir()
    (tmp_path / "floppies" / "roto" / "floppy.toml").write_text("excluir = []\n", encoding="utf-8")
    for nombre, error in (("roto", "fuente"), ("nada", "No existe"), ("../a", "inválido"), ("a/../a", "inválido")):
        with pytest.raises(SystemExit, match=error):
            corpus.montar(nombre)
    assert corpus.montado() == "a"
