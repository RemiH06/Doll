import asyncio
import shutil
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from doll import mcp_server  # noqa: E402

BOVEDA = Path(__file__).parent / "boveda"


def configurar(home: Path, boveda: Path, extra: str, nombre: str = "t") -> None:
    (home / "floppies" / nombre).mkdir(parents=True, exist_ok=True)
    (home / "floppies" / nombre / "floppy.toml").write_text(
        f'fuente = "{boveda.as_posix()}"\nterceros = ["recursos/reels/**"]\n{extra}\n', encoding="utf-8"
    )


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("DOLL_HOME", str(tmp_path))
    monkeypatch.delenv("BAKERS_URL", raising=False)
    monkeypatch.delenv("BAKERS_API_KEY", raising=False)
    copia = tmp_path / "boveda"
    shutil.copytree(BOVEDA, copia)
    return tmp_path


def llamar(servidor, herramienta: str, **argumentos) -> str:
    resultado = asyncio.run(servidor.call_tool(herramienta, argumentos))
    return resultado.content[0].text


def test_no_arranca_sin_mcp_excluir(home):
    configurar(home, home / "boveda", "")
    with pytest.raises(SystemExit, match="mcp_excluir"):
        mcp_server.crear("t")


def test_buscar_da_ruta_lineas_y_marca_terceros(home):
    configurar(home, home / "boveda", "mcp_excluir = []")
    salida = llamar(mcp_server.crear("t"), "buscar", consulta="afinar campana metal")
    assert "recursos/reels/Afinar campanas.md:" in salida and "NO CONFIABLE" in salida


def test_mcp_excluir_oculta_lo_que_la_cli_si_encuentra(home):
    configurar(home, home / "boveda", 'mcp_excluir = ["recursos/oficios/**"]')
    servidor = mcp_server.crear("t")
    assert "oficios" not in llamar(servidor, "buscar", consulta="escape cilindro áncora")


def test_preguntar_no_ve_lo_excluido_y_sin_gateway_lo_dice(home):
    configurar(home, home / "boveda", 'mcp_excluir = ["recursos/oficios/**"]')
    salida = llamar(mcp_server.crear("t"), "preguntar_notas", consulta="escape de áncora inventado")
    assert "BAKERS_URL" in salida and "oficios" not in salida


def test_k_fuera_de_rango_no_rompe(home):
    configurar(home, home / "boveda", "mcp_excluir = []")
    assert "Escapes" in llamar(mcp_server.crear("t"), "buscar", consulta="escape cilindro", k=-3)


def test_buscar_inspiracion_sin_gateway_usa_fts_solo_en_terceros(home):
    configurar(home, home / "boveda", "mcp_excluir = []")
    salida = llamar(mcp_server.crear("t"), "buscar_inspiracion", consulta="campana torre escape")
    assert salida.startswith("Sin búsqueda por sentido") and "Afinar campanas" in salida
    assert "Reloj de torre" not in salida and "Escapes" not in salida


def test_sigue_al_montado_sin_reiniciar(home):
    configurar(home, home / "boveda", "mcp_excluir = []")
    configurar(home, home / "boveda", 'mcp_excluir = ["recursos/oficios/**"]', nombre="u")
    (home / "montado").write_text("t", encoding="utf-8")
    servidor = mcp_server.crear()
    assert "Escapes" in llamar(servidor, "buscar", consulta="escape cilindro")
    (home / "montado").write_text("u", encoding="utf-8")
    assert "oficios" not in llamar(servidor, "buscar", consulta="escape cilindro")


def test_montar_uno_sin_mcp_excluir_no_tumba_el_servidor(home):
    configurar(home, home / "boveda", "mcp_excluir = []")
    configurar(home, home / "boveda", "", nombre="u")
    (home / "montado").write_text("t", encoding="utf-8")
    servidor = mcp_server.crear()
    (home / "montado").write_text("u", encoding="utf-8")
    with pytest.raises(Exception, match="mcp_excluir"):
        llamar(servidor, "buscar", consulta="escape cilindro")
    (home / "montado").write_text("t", encoding="utf-8")
    assert "Escapes" in llamar(servidor, "buscar", consulta="escape cilindro")
