import shutil
from pathlib import Path

import pytest
from bakers import core

from doll import indice, sentido
from doll.corpus import Corpus

BOVEDA = Path(__file__).parent / "boveda"


def falso(llamadas):
    """Un eje por tema: el sentido sale de las palabras, sin modelo."""
    def embeber(textos):
        llamadas.append(len(textos))
        return [[t.lower().count("campana") + t.lower().count("bronce"), t.lower().count("engrane"), 0.01]
                for t in textos]
    return embeber


@pytest.fixture
def taller(tmp_path):
    raiz = tmp_path / "b"
    shutil.copytree(BOVEDA, raiz)
    (raiz / "recursos" / "reels" / "Fundir bronce.md").write_text(
        "# Fundir bronce\n\nVaciar bronce en un molde de arena.\n\n## Molde\n\nArena verde.\n", "utf-8")
    corpus = Corpus("t", raiz, terceros=("recursos/reels/**",))
    con = indice.abrir(tmp_path / "t.db")
    indice.indexar(con, corpus)
    return con, corpus


def test_llenar_solo_embebe_terceros_y_lo_nuevo(taller, monkeypatch):
    con, corpus = taller
    llamadas = []
    monkeypatch.setattr(core, "embeber", falso(llamadas))
    terceros = len(sentido._fragmentos(con, corpus))
    assert terceros and sentido.llenar(con, corpus) == terceros == sum(llamadas)
    assert sentido.llenar(con, corpus) == 0
    (corpus.ruta / "recursos" / "reels" / "Fundir bronce.md").write_text("# Fundir bronce\n\nOtro texto.\n", "utf-8")
    indice.indexar(con, corpus)
    assert sentido.llenar(con, corpus) == 1
    # Los vectores de la versión vieja se borran: uno por fragmento vigente.
    assert con.execute("SELECT count(*) FROM vectores").fetchone()[0] == len(sentido._fragmentos(con, corpus))


def test_buscar_ordena_por_sentido_y_no_sale_de_terceros(taller, monkeypatch):
    con, corpus = taller
    monkeypatch.setattr(core, "embeber", falso([]))
    res, aviso = sentido.buscar(con, corpus, "campana", 10)
    assert aviso is None and res
    assert all(corpus.es_terceros(r.ruta) for r in res)
    assert res[0].ruta.endswith("Afinar campanas.md")
    oculto, _ = sentido.buscar(con, corpus, "campana", 10, indice.Filtro(ocultar=("recursos/reels/Afinar*",)))
    assert oculto and not any(r.ruta.endswith("Afinar campanas.md") for r in oculto)


def test_sin_gateway_responde_con_fts_y_lo_dice(taller, monkeypatch):
    con, corpus = taller

    def caido(textos):
        raise core.BakerError("Sin conexión con llama-swap")

    monkeypatch.setattr(core, "embeber", caido)
    res, aviso = sentido.buscar(con, corpus, "bronce", 5)
    assert "FTS" in aviso and [r.ruta for r in res] == ["recursos/reels/Fundir bronce.md"] * len(res) and res


def test_con_muchos_vectores_faltantes_no_embebe_en_linea(taller, monkeypatch):
    con, corpus = taller
    llamadas = []
    monkeypatch.setattr(core, "embeber", falso(llamadas))
    monkeypatch.setattr(sentido, "EN_LINEA", 1)
    res, aviso = sentido.buscar(con, corpus, "bronce", 5)
    assert llamadas == [] and "indexar --sentido" in aviso and "FTS" in aviso and res
    assert sentido.llenar(con, corpus) > 1  # aparte, sin tope
    res, aviso = sentido.buscar(con, corpus, "bronce", 5)
    assert aviso is None and res
