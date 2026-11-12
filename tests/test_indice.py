import shutil
from pathlib import Path

import pytest

from doll import indice
from doll.corpus import Corpus
from doll.parser import Fragmento, analizar

BOVEDA = Path(__file__).parent / "boveda"


@pytest.fixture
def boveda(tmp_path):
    copia = tmp_path / "boveda"
    shutil.copytree(BOVEDA, copia)
    return copia


@pytest.fixture
def con(tmp_path):
    return indice.abrir(tmp_path / "t.db")


def partir(texto):
    return analizar([texto])[0].fragmentos


def volcado(con):
    return "\n".join(str(fila) for tabla in ("notas", "fragmentos", "enlaces", "categorias")
                     for fila in con.execute(f"SELECT * FROM {tabla}"))


def boveda_chica(carpeta, **notas):
    carpeta.mkdir(exist_ok=True)
    for nombre, texto in notas.items():
        (carpeta / f"{nombre}.md").write_text(texto, encoding="utf-8")
    return Corpus("t", carpeta)


def rutas(resultados):
    return [r.ruta for r in resultados]


def filas(con):
    return con.execute("SELECT id, ruta, linea_ini FROM fragmentos ORDER BY id").fetchall()


def test_partir_ignora_frontmatter_y_conserva_lineas():
    texto = "---\ntags: [a]\n---\n\n# Uno\n\ncuerpo\n\n## Dos\nmás\n"
    assert partir(texto) == [
        Fragmento("Uno", 5, 8, "# Uno\n\ncuerpo"),
        Fragmento("Uno > Dos", 9, 10, "## Dos\nmás"),
    ]


def test_partir_no_confunde_comentario_de_codigo_con_encabezado():
    nota = (BOVEDA / "proyectos" / "Reloj de torre.md").read_text(encoding="utf-8")
    nombres = [f.encabezado for f in partir(nota)]
    assert "Reloj de torre > Procedimiento" in nombres
    assert not any("no es un encabezado" in n for n in nombres)
    assert "Reloj de torre > Procedimiento > Lubricación" in nombres


def test_partir_nota_sin_encabezados():
    nota = (BOVEDA / "proyectos" / "Autómata.md").read_text(encoding="utf-8")
    assert [f.encabezado for f in partir(nota)] == [""]


def test_las_lineas_apuntan_al_texto_real():
    nota = (BOVEDA / "proyectos" / "Reloj de torre.md").read_text(encoding="utf-8")
    lineas = nota.splitlines()
    for f in partir(nota):
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
    # Las dos notas que enlazan a la carpeta se rehacen para tapar el enlace.
    assert indice.indexar(con, Corpus("t", boveda, ("recursos/oficios/**",))) == (2, 3)
    assert indice.buscar(con, "cilindro", 5) == []
    assert con.execute("SELECT count(*) FROM fts WHERE fts MATCH 'cilindro'").fetchone() == (0,)
    assert "Escapes" not in volcado(con) and "Marcha y calibración" not in volcado(con)


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


def test_enlace_a_nota_excluida_no_deja_rastro(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    todo = volcado(con)
    assert "Pruebas" not in todo and "señora del encargo" not in todo and "Sin nota" not in todo
    assert indice.buscar(con, "señora", 5) == []
    assert con.execute("SELECT count(*) FROM fts WHERE fts MATCH 'doña'").fetchone() == (0,)
    assert indice.ENLACE_OCULTO in indice.buscar(con, "atrasa cuatro minutos", 1)[0].texto


def test_taparlo_no_mueve_las_lineas(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    r = indice.buscar(con, "atrasa cuatro minutos", 1)[0]
    lineas = (boveda / r.ruta).read_text(encoding="utf-8").splitlines()
    assert lineas[r.linea_ini - 1] == r.texto.splitlines()[0]


def test_guarda_enlaces_resueltos(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    enlaces = set(con.execute("SELECT origen, destino FROM enlaces"))
    assert ("proyectos/Reloj de torre.md", "recursos/oficios/Escapes.md") in enlaces
    assert all(d.endswith(".md") for _, d in enlaces)


def test_enlaces_se_actualizan_al_crear_la_nota_destino(tmp_path, con):
    corpus = boveda_chica(tmp_path / "b", a="# A\n[[B]]\n")
    indice.indexar(con, corpus)
    assert con.execute("SELECT count(*) FROM enlaces").fetchone() == (0,)
    (tmp_path / "b" / "b.md").write_text("# B\n", encoding="utf-8")
    indice.indexar(con, corpus)
    assert con.execute("SELECT * FROM enlaces").fetchall() == [("a.md", "b.md")]


def test_nombre_repetido_resuelve_a_la_ruta_mas_corta_y_con_carpeta_a_la_exacta(tmp_path, con):
    corpus = boveda_chica(tmp_path / "b", a="# A\n[[X]] [[sub/x]]\n", x="# X\n")
    (tmp_path / "b" / "sub").mkdir()
    (tmp_path / "b" / "sub" / "x.md").write_text("# X\n", encoding="utf-8")
    indice.indexar(con, corpus)
    assert sorted(con.execute("SELECT destino FROM enlaces")) == [("sub/x.md",), ("x.md",)]


def test_tope_por_nota_deja_entrar_otras_notas(tmp_path, con):
    secciones = "".join(f"## {n}\nrueda rueda rueda\n" for n in ("Uno", "Dos", "Tres", "Cuatro"))
    indice.indexar(con, boveda_chica(tmp_path / "b", a=f"# A\n{secciones}", b="# B\nrueda en un texto bastante más largo\n"))
    encontradas = rutas(indice.buscar(con, "rueda", 3))
    assert encontradas.count("a.md") == indice.TOPE_POR_NOTA and "b.md" in encontradas


def test_trae_vecina_en_ambas_direcciones_y_solo_si_coincide(tmp_path, con):
    corpus = boveda_chica(tmp_path / "b", a="# A\nrueda rueda rueda\n[[B]]\n", b="# B\nrueda de otra cosa\n",
                          c="# C\nmucho texto y una rueda\n[[A]]\n", d="# D\nrueda aislada de todo lo demás, sin enlaces\n",
                          e="# E\nsin el término\n[[A]]\n")
    indice.indexar(con, corpus)
    encontradas = rutas(indice.buscar(con, "rueda", 1))
    assert encontradas[0] == "a.md" and sorted(encontradas[1:]) == ["b.md", "c.md"]


def test_vecinas_tienen_tope(tmp_path, con):
    enlaces = " ".join(f"[[n{i}]]" for i in range(6))
    otras = {f"n{i}": f"# N\nuna rueda entre muchas otras palabras {i}\n" for i in range(6)}
    indice.indexar(con, boveda_chica(tmp_path / "b", a=f"# A\nrueda rueda\n{enlaces}\n", **otras))
    assert len(indice.buscar(con, "rueda", 1)) == 1 + indice.VECINAS


def test_vecinas_salen_solo_de_la_mejor_nota(tmp_path, con):
    relleno = "palabras sin relación con la consulta " * 8
    corpus = boveda_chica(tmp_path / "v", mejor="rueda rueda rueda rueda [[cerca]]", otra="rueda rueda [[lejos]]",
                          cerca=f"rueda {relleno}", lejos=f"rueda {relleno}")
    indice.indexar(con, corpus)
    rutas = [r.ruta for r in indice.buscar(con, "rueda", 2)]
    assert rutas == ["mejor.md", "otra.md", "cerca.md"]


def test_solo_limita_la_carpeta_tambien_en_vecinas(boveda, con):
    corpus = Corpus("t", boveda)
    indice.indexar(con, corpus)
    filtro = indice.Filtro(solo=("recursos/oficios/**",))
    assert {r.ruta.split("/")[0] for r in indice.buscar(con, "escape marcha reloj", 5, filtro)} == {"recursos"}
    assert indice.buscar(con, "Valdeluna", 5, filtro) == []


def test_filtra_por_tipo_y_dominio_en_lista(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    assert set(rutas(indice.buscar(con, "escape", 8, indice.Filtro(tipo="referencia")))) == {"recursos/oficios/Escapes.md"}
    assert set(rutas(indice.buscar(con, "escape", 8, indice.Filtro(dominio="restauración")))) == {"proyectos/Reloj de torre.md"}
    assert indice.buscar(con, "escape", 8, indice.Filtro(tipo="referencia", dominio="restauración")) == []
    assert indice.buscar(con, "escape", 8, indice.Filtro(tipo="no existe")) == []


def test_ocultar_no_deja_entrar_ni_como_vecina(boveda, con):
    indice.indexar(con, Corpus("t", boveda))
    filtro = indice.Filtro(ocultar=("recursos/oficios/**",))
    assert not any("oficios" in r for r in rutas(indice.buscar(con, "escape áncora marcha", 8, filtro)))


def test_indice_de_otra_version_se_rehace(tmp_path):
    archivo = tmp_path / "v.db"
    con = indice.abrir(archivo)
    indice.indexar(con, boveda_chica(tmp_path / "b", a="# A\nrueda\n"))
    con.execute("PRAGMA user_version = 1")
    con.close()
    con = indice.abrir(archivo)
    assert con.execute("SELECT count(*) FROM notas").fetchone() == (0,)
    assert con.execute("SELECT count(*) FROM fts").fetchone() == (0,)


def test_frontmatter_invalido_avisa_y_la_nota_entra(tmp_path, con, capsys):
    indice.indexar(con, boveda_chica(tmp_path / "b", a="---\ndominio: [roto\n---\n# A\nrueda\n"))
    assert "a.md" in capsys.readouterr().err
    assert rutas(indice.buscar(con, "rueda", 1)) == ["a.md"]


def test_ampliar_suma_secciones_de_la_mejor_nota_sin_duplicar(tmp_path, con):
    boveda_chica(tmp_path, a="# Tema\n\nescape escape\n\n## Otra\n\nsin relación\n", b="# B\n\nescape\n\n## Fuera\n\nnada\n")
    indice.indexar(con, Corpus("t", tmp_path))
    base = indice.buscar(con, "escape", 5)
    ampliados = indice.ampliar(con, base)
    assert any("sin relación" in f.texto for f in ampliados)
    assert not any("nada" in f.texto for f in ampliados)  # solo la mejor nota
    assert len({(f.ruta, f.linea_ini) for f in ampliados}) == len(ampliados)


def test_ampliar_respeta_el_tope(tmp_path, con):
    relleno = "x " * (indice.TOPE_AMPLIAR // 2 + 1)
    boveda_chica(tmp_path, a=f"# Tema\n\nescape\n\n## Larga\n\n{relleno}\n\n## Corta\n\nbreve\n")
    indice.indexar(con, Corpus("t", tmp_path))
    ampliados = indice.ampliar(con, indice.buscar(con, "escape", 5))
    assert any("breve" in f.texto for f in ampliados)
    assert not any("x x x" in f.texto for f in ampliados)


def test_ampliar_sin_fragmentos(con):
    assert indice.ampliar(con, []) == []


def test_terceros_ocupan_a_lo_mas_dos_lugares_salvo_que_se_pidan(tmp_path):
    raiz = tmp_path / "b"
    (raiz / "reels").mkdir(parents=True)
    for i in range(4):
        (raiz / "reels" / f"r{i}.md").write_text(f"# Campana {i}\n\nAfinar la campana con torno.\n", "utf-8")
    (raiz / "Campanario.md").write_text("# Campanario\n\nLa campana mayor se afina cada año.\n", "utf-8")
    corpus = Corpus("t", raiz, terceros=("reels/**",))
    con = indice.abrir(tmp_path / "t.db")
    indice.indexar(con, corpus)
    con_tope = indice.buscar(con, "campana", 5, indice.Filtro(terceros=corpus.terceros))
    assert sum(r.ruta.startswith("reels/") for r in con_tope) == 2
    assert "Campanario.md" in {r.ruta for r in con_tope}
    pedidas = indice.buscar(con, "campana", 5, indice.Filtro(solo=corpus.terceros, terceros=corpus.terceros))
    assert len(pedidas) == 4
