import shutil
from pathlib import Path

import pytest

from doll import indice
from doll.corpus import Corpus

BOVEDA = Path(__file__).parent / "boveda"


@pytest.fixture
def boveda(tmp_path):
    copia = tmp_path / "boveda"
    shutil.copytree(BOVEDA, copia)
    return copia


@pytest.fixture
def con(tmp_path):
    return indice.abrir(tmp_path / "t.db")


def filas(con):
    return con.execute("SELECT id, ruta, linea_ini FROM fragmentos ORDER BY id").fetchall()


def test_partir_ignora_frontmatter_y_conserva_lineas():
    texto = "---\ntags: [a]\n---\n\n# Uno\n\ncuerpo\n\n## Dos\nmás\n"
    assert indice.partir(texto) == [
        indice.Fragmento("Uno", 5, 8, "# Uno\n\ncuerpo"),
        indice.Fragmento("Uno > Dos", 9, 10, "## Dos\nmás"),
    ]


def test_partir_no_confunde_comentario_de_codigo_con_encabezado():
    nota = (BOVEDA / "proyectos" / "Reloj de torre.md").read_text(encoding="utf-8")
    nombres = [f.encabezado for f in indice.partir(nota)]
    assert "Reloj de torre > Procedimiento" in nombres
    assert not any("no es un encabezado" in n for n in nombres)
    assert "Reloj de torre > Procedimiento > Lubricación" in nombres


def test_partir_nota_sin_encabezados():
    nota = (BOVEDA / "proyectos" / "Autómata.md").read_text(encoding="utf-8")
    assert [f.encabezado for f in indice.partir(nota)] == [""]


def test_las_lineas_apuntan_al_texto_real():
    nota = (BOVEDA / "proyectos" / "Reloj de torre.md").read_text(encoding="utf-8")
    lineas = nota.splitlines()
    for f in indice.partir(nota):
        assert lineas[f.linea_ini - 1] == f.texto.splitlines()[0]


def test_reindexar_sin_cambios_no_toca_filas(boveda, con):
    corpus = Corpus("t", boveda)
    indice.indexar(con, corpus)
    antes = filas(con)
    assert indice.indexar(con, corpus) == (0, 0)
    assert filas(con) == antes


def test_editar_una_nota_solo_reindexa_esa(boveda, con):
    corpus = Corpus("t", boveda)
    indice.indexar(con, corpus)
    otras = [f for f in filas(con) if f[1] != "recursos/oficios/Escapes.md"]
    (boveda / "recursos/oficios/Escapes.md").write_text("# Escapes\n\ntourbillon\n", encoding="utf-8")
    assert indice.indexar(con, corpus) == (1, 0)
    assert [f for f in filas(con) if f[1] != "recursos/oficios/Escapes.md"] == otras
    assert indice.buscar(con, "tourbillon", 5)[0].ruta == "recursos/oficios/Escapes.md"
    assert indice.buscar(con, "cilindro", 5) == []


def test_nota_recien_excluida_sale_del_indice(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    assert indice.buscar(con, "escape cilindro", 5)
    assert indice.indexar(con, Corpus("t", boveda, ("recursos/oficios/**",))) == (0, 3)
    assert indice.buscar(con, "cilindro", 5) == []
    assert con.execute("SELECT count(*) FROM fts WHERE fts MATCH 'cilindro'").fetchone() == (0,)


def test_ninguna_ruta_excluida_entra_al_indice(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    rutas = [r for (r,) in con.execute("SELECT DISTINCT ruta FROM fragmentos")]
    assert rutas and not any(r.startswith(("gente/", "life/")) for r in rutas)
    assert indice.buscar(con, "palabraexcluidagente palabraexcluidalife", 5) == []


def test_buscar_ignora_acentos_y_da_lineas(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    r = indice.buscar(con, "ancora gastado", 1)[0]
    assert r.ruta == "proyectos/Reloj de torre.md"
    assert r.encabezado == "Reloj de torre > Diagnóstico"
    assert r.linea_ini > 1


def test_buscar_no_interpreta_sintaxis_fts(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    assert indice.buscar(con, 'escape" OR titulo:* NEAR(', 5) is not None
    assert indice.buscar(con, "¿?", 5) == []
