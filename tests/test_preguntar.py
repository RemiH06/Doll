import json
import shutil
from pathlib import Path

import pytest

from doll import indice
from doll.corpus import Corpus
from doll.preguntar import AVISO_TERCEROS, BakerCaido, contexto, preguntar, verificar

BOVEDA = Path(__file__).parent / "boveda"
PREGUNTA_SECRETA = "pregunta secreta sobre el escape de áncora"


@pytest.fixture
def doll_home(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLL_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def corpus():
    return Corpus("t", BOVEDA, terceros=("recursos/reels/**",))


@pytest.fixture
def con(doll_home, corpus):
    conexion = indice.abrir(doll_home / "t.db")
    indice.indexar(conexion, corpus)
    return conexion


def guion(*salidas):
    """Baker falso que responde en orden y guarda lo que recibió."""
    pendientes = list(salidas)
    llamadas = []

    def baker(tarea, archivo):
        llamadas.append((tarea, Path(archivo).read_text(encoding="utf-8")))
        return pendientes.pop(0)

    baker.llamadas = llamadas
    return baker


def salida(citas=(), no_encontrado=False, respuesta="ok"):
    return {"citas": list(citas), "no_encontrado": no_encontrado, "respuesta": respuesta}


CITA_REAL = "Inventado hacia 1657"


def test_cita_real_trae_ruta_y_lineas(con, corpus):
    r = preguntar(con, corpus, "escape de áncora inventado", baker=guion(salida([CITA_REAL])))
    assert not r.no_encontrado and r.intentos == 1
    assert r.citas[0].ruta == "recursos/oficios/Escapes.md" and r.citas[0].linea_ini > 1


def test_cita_falsa_se_reintenta_y_la_correccion_la_rescata(con, corpus):
    baker = guion(salida(["Inventado en 1999"]), salida([CITA_REAL]))
    r = preguntar(con, corpus, "escape de áncora inventado", baker=baker)
    assert r.intentos == 2 and r.citas_descartadas == 0 and len(r.citas) == 1
    assert "Inventado en 1999" in baker.llamadas[1][0]


def test_sin_citas_validas_termina_en_no_encontrado(con, corpus):
    baker = guion(salida(["falsa uno"], respuesta="inventada"), salida(["falsa dos"], respuesta="inventada"))
    r = preguntar(con, corpus, "escape de áncora", baker=baker)
    assert r.no_encontrado and r.texto == "" and r.citas == []


def test_sin_citas_no_cuenta_como_respuesta(con, corpus):
    r = preguntar(con, corpus, "escape", baker=guion(salida(), salida()))
    assert r.no_encontrado


def test_el_modelo_puede_decir_no_encontrado(con, corpus):
    baker = guion(salida(no_encontrado=True, respuesta=""))
    assert preguntar(con, corpus, "escape", baker=baker).no_encontrado and len(baker.llamadas) == 1


def test_sin_fragmentos_no_llama_al_baker(con, corpus):
    baker = guion()
    assert preguntar(con, corpus, "xilofón", baker=baker).no_encontrado and baker.llamadas == []


def test_baker_caido_deja_fallo_y_fragmentos(con, corpus):
    def caido(tarea, archivo):
        raise BakerCaido("marcha ninguna")

    r = preguntar(con, corpus, "escape de áncora", baker=caido)
    assert r.fallo == "marcha ninguna" and r.fragmentos and not r.no_encontrado


def test_verificar_tolera_espacios_pero_no_otras_palabras(con, corpus):
    fragmentos = indice.buscar(con, "escape áncora", 5)
    buenas, malas = verificar(["Inventado   hacia\n1657", "inventado hacia 1657", "de"], fragmentos, corpus)
    assert [c.texto for c in buenas] == ["Inventado   hacia\n1657"]
    assert malas == ["inventado hacia 1657", "de"]


def test_texto_de_terceros_va_marcado_en_prompt_y_cita(con, corpus):
    fragmentos = indice.buscar(con, "afinar campana metal", 5)
    assert AVISO_TERCEROS in contexto(fragmentos, corpus)
    cita = "se afina quitando metal por dentro"
    r = preguntar(con, corpus, "afinar campana metal", baker=guion(salida([cita])))
    assert r.citas[0].terceros


def test_el_log_no_guarda_pregunta_ni_fragmentos(con, corpus, doll_home):
    preguntar(con, corpus, PREGUNTA_SECRETA, baker=guion(salida([CITA_REAL])))
    crudo = (doll_home / "log.jsonl").read_text(encoding="utf-8")
    assert "secreta" not in crudo and "1657" not in crudo
    linea = json.loads(crudo)
    assert linea["citas"] == 1
    assert not any(isinstance(v, str) for k, v in linea.items() if k not in ("fecha", "op"))


def test_buscar_funciona_sin_gateway(monkeypatch, con):
    monkeypatch.delenv("BAKERS_URL", raising=False)
    monkeypatch.delenv("BAKERS_API_KEY", raising=False)
    assert indice.buscar(con, "escape", 1)


def test_sin_variables_del_gateway_preguntar_reporta_fallo(monkeypatch, con, corpus):
    pytest.importorskip("bakers")
    monkeypatch.delenv("BAKERS_URL", raising=False)
    monkeypatch.delenv("BAKERS_API_KEY", raising=False)
    r = preguntar(con, corpus, "escape de áncora")
    assert "BAKERS_URL" in r.fallo and r.fragmentos


def test_el_indice_copia_no_toca_la_boveda(tmp_path):
    copia = tmp_path / "b"
    shutil.copytree(BOVEDA, copia)
    antes = sorted(p.read_bytes() for p in copia.rglob("*.md"))
    con = indice.abrir(tmp_path / "x.db")
    indice.indexar(con, Corpus("t", copia))
    assert sorted(p.read_bytes() for p in copia.rglob("*.md")) == antes
