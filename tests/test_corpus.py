from pathlib import Path

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
