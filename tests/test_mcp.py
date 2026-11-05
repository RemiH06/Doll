import asyncio
import shutil
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from doll import mcp_server  # noqa: E402

BOVEDA = Path(__file__).parent / "boveda"


def configurar(home: Path, boveda: Path, extra: str) -> None:
    (home / "corpus.toml").write_text(
        f'[t]\nruta = "{boveda.as_posix()}"\nterceros = ["recursos/reels/**"]\n{extra}\n', encoding="utf-8"
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
