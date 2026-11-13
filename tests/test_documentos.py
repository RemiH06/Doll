from pathlib import Path

import pytest

from doll import extraer, indice
from doll.corpus import Corpus
from doll.evaluar import evaluar_generacion
from doll.indice import Resultado
from doll.preguntar import Cita, Respuesta, texto_fragmentos

PENDULO = "El escape de ancora tolera un pendulo largo y por eso domina en los relojes de torre."
VOLANTE = "La marcha se calibra moviendo la raqueta del volante hasta que el atraso diario desaparece."
HTML = """<!doctype html>
<html><head><title>Manual del relojero</title><style>h1 { color: red }</style></head>
<body><nav><a href="#escapes">Menu de prueba</a></nav>
<p>Antes de todo.</p>
<h1>Escapes</h1>
<p>El escape de ancora tolera un pendulo largo.</p>
<script>var secreto = "no indexar";</script>
<h2>Cilindro</h2>
<p>Para relojes de bolsillo.</p>
<svg><title>dibujo</title><text>engrane</text></svg>
<h1>Marcha</h1><p>Se calibra con el volante.</p>
</body></html>
"""


def pdf_minimo(paginas: list[str]) -> bytes:
    """Un PDF de texto, sin librerías ni archivos binarios en el repo. Página vacía: '' (como un escaneo)."""
    objetos: list[bytes] = [b"<< /Type /Catalog /Pages 2 0 R >>", b"",
                            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    hojas = []
    for texto in paginas:
        contenido = f"BT /F1 10 Tf 40 700 Td ({texto}) Tj ET".encode("latin-1") if texto else b""
        objetos.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(contenido), contenido))
        objetos.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                       b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % len(objetos))
        hojas.append(len(objetos))
    objetos[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % h for h in hojas), len(hojas))
    salida, posiciones = b"%PDF-1.4\n", []
    for numero, objeto in enumerate(objetos, 1):
        posiciones.append(len(salida))
        salida += b"%d 0 obj\n%s\nendobj\n" % (numero, objeto)
    inicio_xref = len(salida)
    salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
    salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
    return salida + b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, inicio_xref)


def test_pdf_un_fragmento_por_pagina_sin_las_vacias(tmp_path):
    archivo = tmp_path / "m.pdf"
    archivo.write_bytes(pdf_minimo([PENDULO, "", VOLANTE]))
    nota = extraer.pdf(archivo)
    assert [(f.encabezado, f.linea_ini, f.linea_fin) for f in nota.fragmentos] == [("p. 1", 1, 1), ("p. 3", 3, 3)]
    assert "pendulo largo" in nota.fragmentos[0].texto


def test_html_parte_por_encabezado_con_lineas_del_fuente():
    nota = extraer.html(HTML)
    assert nota.titulo == "Manual del relojero"
    assert [f.encabezado for f in nota.fragmentos] == ["", "Escapes", "Escapes > Cilindro", "Marcha"]
    lineas = HTML.splitlines()
    for f in nota.fragmentos[1:]:
        assert f.encabezado.split(" > ")[-1] in lineas[f.linea_ini - 1]
        assert f.linea_ini <= f.linea_fin
    todo = " ".join(f.texto for f in nota.fragmentos)
    assert "Antes de todo." in todo and "volante" in todo
    for fuera in ("secreto", "Menu", "engrane", "dibujo", "color"):
        assert fuera not in todo


@pytest.fixture
def fuente(tmp_path):
    raiz = tmp_path / "f"
    (raiz / "docs" / "sub").mkdir(parents=True)
    (raiz / "a.pdf").write_bytes(pdf_minimo([PENDULO, VOLANTE]))
    (raiz / "docs" / "index.html").write_text(HTML, encoding="utf-8")
    (raiz / "docs" / "sub" / "otra.html").write_text(HTML, encoding="utf-8")
    (raiz / "nota.md").write_text("# Nota\n\nNo entra: incluir no la pide.\n", encoding="utf-8")
    return raiz


def test_indexa_solo_lo_que_incluir_pide_y_extrae_solo_lo_que_cambio(fuente, tmp_path, monkeypatch):
    corpus = Corpus("t", fuente, incluir=("*.pdf", "docs/*.html"))
    con = indice.abrir(tmp_path / "t.db")
    assert indice.indexar(con, corpus) == (2, 0)
    assert {r for (r,) in con.execute("SELECT ruta FROM notas")} == {"a.pdf", "docs/index.html"}

    llamadas = []
    original = extraer.pdf
    monkeypatch.setattr(extraer, "pdf", lambda archivo: llamadas.append(archivo) or original(archivo))
    (fuente / "nota.md").write_text("# Nota\n\nCambia, pero sigue fuera.\n", encoding="utf-8")
    assert indice.indexar(con, corpus) == (0, 0) and llamadas == []
    (fuente / "a.pdf").write_bytes(pdf_minimo([PENDULO]))
    assert indice.indexar(con, corpus) == (1, 0) and len(llamadas) == 1
    (fuente / "docs" / "index.html").unlink()
    assert indice.indexar(con, corpus) == (0, 1)


def test_pdf_se_cita_por_pagina_y_html_por_titulo(fuente, tmp_path):
    corpus = Corpus("t", fuente, incluir=("*.pdf", "docs/*.html"))
    con = indice.abrir(tmp_path / "t.db")
    indice.indexar(con, corpus)
    salida = texto_fragmentos(indice.buscar(con, "raqueta volante", 1), corpus)
    assert salida.startswith("a.pdf, p. 2 [p. 2]")
    # Todos los HTML de docs/ se llaman index.html: el título del documento es lo que se busca.
    assert indice.buscar(con, "relojero", 5)[0].ruta == "docs/index.html"


def test_pdf_sin_texto_o_danado_avisa_y_no_detiene_el_indice(fuente, tmp_path, capsys):
    (fuente / "escaneo.pdf").write_bytes(pdf_minimo(["", ""]))
    (fuente / "roto.pdf").write_bytes(b"esto no es un pdf")
    con = indice.abrir(tmp_path / "t.db")
    assert indice.indexar(con, Corpus("t", fuente, incluir=("*.pdf",))) == (3, 0)
    avisos = capsys.readouterr().err
    assert "sin texto en escaneo.pdf" in avisos and "no se pudo leer roto.pdf" in avisos
    assert indice.buscar(con, "pendulo", 5)[0].ruta == "a.pdf"


def test_floppy_todo_de_terceros_no_lleva_tope(tmp_path):
    raiz = tmp_path / "b"
    raiz.mkdir()
    for i in range(4):
        (raiz / f"r{i}.md").write_text(f"# Campana {i}\n\nAfinar la campana con torno.\n", "utf-8")
    con = indice.abrir(tmp_path / "t.db")
    indice.indexar(con, Corpus("t", raiz, terceros=("**",)))
    assert len(indice.buscar(con, "campana", 4, indice.Filtro(terceros=("**",)))) == 4


def test_cita_en_otra_pagina_del_pdf_correcto_no_cuenta(tmp_path):
    p1 = Resultado("a.pdf", "p. 1", 1, 1, PENDULO)
    p2 = Resultado("a.pdf", "p. 2", 2, 2, VOLANTE)
    preguntas = [{"id": x, "tipo": "directa", "pregunta": x, "notas": ["a.pdf"], "evidencia": ["raqueta del volante"]}
                 for x in ("bien", "mal")]
    salidas = {"bien": Respuesta(texto="raqueta del volante", fragmentos=[p1, p2],
                                 citas=[Cita("raqueta del volante", "a.pdf", 2, 2, False)]),
               "mal": Respuesta(texto="raqueta del volante", fragmentos=[p1, p2],
                                citas=[Cita("pendulo largo", "a.pdf", 1, 1, False)])}
    g = evaluar_generacion(preguntas, salidas.__getitem__, tmp_path / "s.jsonl")
    assert (g.todas_las_notas, g.traen_evidencia, g.citan_el_lugar) == (2, 2, 1)


def test_incluir_no_sale_de_la_fuente(tmp_path, monkeypatch):
    from doll import corpus

    monkeypatch.setenv("DOLL_HOME", str(tmp_path))
    (tmp_path / "floppies" / "x").mkdir(parents=True)
    for patron in ("../*.pdf", "/etc/*.html", "C:/x/*.pdf"):
        (tmp_path / "floppies" / "x" / "floppy.toml").write_text(
            f"fuente = '{Path(__file__).parent.as_posix()}'\nincluir = ['{patron}']\n", encoding="utf-8")
        with pytest.raises(SystemExit, match="sale de la fuente"):
            corpus.cargar("x")


def test_tapar_quita_frases_sin_importar_mayusculas_acentos_ni_separadores(tmp_path):
    raiz = tmp_path / "t"
    raiz.mkdir()
    (raiz / "tarea_zacarias_nunez_9911.pdf").write_bytes(pdf_minimo(
        ["Entrega de ZACARIAS NUNEZ, expediente 9911. " + PENDULO, "Firma: Zacarias_Nunez. " + VOLANTE]))
    (raiz / "nota.md").write_text("# Zacarías Núñez\n\nLo escribió Zacarías  Núñez sobre el péndulo.\n", "utf-8")
    con = indice.abrir(tmp_path / "t.db")
    corpus = Corpus("t", raiz, incluir=("*.pdf", "*.md"), tapar=("Zacarías Núñez", "9911"))
    indice.indexar(con, corpus)
    guardado = " ".join(" ".join(f) for f in con.execute("SELECT encabezado, texto FROM fragmentos"))
    assert "[…]" in guardado
    for dato in ("zacar", "nunez", "núñez", "9911"):
        assert dato not in guardado.casefold()
    for consulta in ("Zacarias", "Nunez", "9911"):  # tampoco por el nombre del archivo
        assert indice.buscar(con, consulta, 5) == []
    assert indice.buscar(con, "pendulo", 5)  # el resto del documento sigue buscable
    # Quitar la frase de `tapar` rehace lo que la tenía, aunque los archivos no cambien.
    assert indice.indexar(con, Corpus("t", raiz, incluir=("*.pdf", "*.md"), tapar=("9911",)))[0] == 2
