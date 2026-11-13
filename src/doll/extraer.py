"""HTML y PDF a fragmentos, con la misma forma que da `doll-parser` para Markdown.

HTML: un fragmento por encabezado (`h1` a `h6`), con las líneas del archivo fuente. PDF: un fragmento por página, con
el número de página en `linea_ini` y `linea_fin`, y `p. N` como encabezado.
"""

import json
import logging
from html.parser import HTMLParser
from pathlib import Path

from doll.parser import Fragmento, Nota

EXTRAIDO = ".json"  # `a.pdf` viaja en un floppy como `a.pdf.json`

MIN_PAGINA = 50  # caracteres: con menos, la página es un escaneo, una portada o una diapositiva de pura imagen
TITULOS = {f"h{n}" for n in range(1, 7)}
OMITIR = {"script", "style", "noscript", "template", "svg", "nav"}  # código, dibujo y menús: no es contenido
BLOQUES = {"p", "div", "li", "br", "tr", "td", "th", "dt", "dd", "pre", "blockquote", "section", "article",
           "table", "ul", "ol", "figcaption", "header", "footer", "main", "details", "summary"}


def _limpio(texto: str) -> str:
    return "\n".join(linea for linea in (" ".join(l.split()) for l in texto.splitlines()) if linea)


class _Partidor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.titulo = ""
        self.fragmentos: list[Fragmento] = []
        self._en_titulo = False
        self._omitir = 0
        self._ruta: list[tuple[int, str]] = []  # encabezados abiertos: (nivel, texto)
        self._inicio = 1
        self._partes: list[str] = []
        self._encabezado: tuple[int, list[str]] | None = None  # el `hN` que se está leyendo

    def cerrar(self, linea_fin: int) -> None:
        texto = _limpio("".join(self._partes))
        if texto:
            encabezado = " > ".join(t for _, t in self._ruta)
            self.fragmentos.append(Fragmento(encabezado, self._inicio, max(linea_fin, self._inicio), texto))
        self._partes = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in OMITIR:
            self._omitir += 1
        elif self._omitir:
            return  # un `<title>` dentro de un `<svg>` no es el del documento
        elif tag == "title":
            self._en_titulo = True
        elif tag in TITULOS:
            linea = self.getpos()[0]
            self.cerrar(linea - 1)
            self._inicio = linea
            self._encabezado = (int(tag[1]), [])
            self._partes.append("\n")
        elif tag in BLOQUES:
            self._partes.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in OMITIR:
            self._omitir = max(self._omitir - 1, 0)
        elif tag == "title":
            self._en_titulo = False
        elif tag in TITULOS and self._encabezado:
            nivel, partes = self._encabezado
            self._encabezado = None
            texto = " ".join("".join(partes).split())
            if texto:
                self._ruta = [r for r in self._ruta if r[0] < nivel] + [(nivel, texto)]
            self._partes.append("\n")
        elif tag in BLOQUES and not self._omitir:
            self._partes.append("\n")

    def handle_data(self, data: str) -> None:
        if self._en_titulo:
            self.titulo += data
        elif not self._omitir:
            self._partes.append(data)
            if self._encabezado:
                self._encabezado[1].append(data)


def html(texto: str) -> Nota:
    partidor = _Partidor()
    partidor.feed(texto)
    partidor.close()
    partidor.cerrar(texto.count("\n") + 1)
    return Nota(partidor.fragmentos, [], {}, False, " ".join(partidor.titulo.split()) or None)


def pdf(archivo: Path) -> Nota:
    """Las páginas sin capa de texto no entran: sin OCR, su texto no existe para Doll."""
    from pypdf import PdfReader  # aquí: indexar Markdown no debe cargarlo

    logging.getLogger("pypdf").setLevel(logging.ERROR)  # avisa de cada objeto mal referido: ruido para quien indexa
    fragmentos = []
    for numero, pagina in enumerate(PdfReader(archivo).pages, 1):
        texto = _limpio(pagina.extract_text() or "")
        if len(texto) >= MIN_PAGINA:
            fragmentos.append(Fragmento(f"p. {numero}", numero, numero, texto))
    return Nota(fragmentos, [], {}, False)


def a_json(titulo: str, fragmentos) -> bytes:
    """El texto ya extraído de un documento, como lo guarda el índice, para que viaje en un floppy sin el original."""
    return json.dumps({"titulo": titulo, "fragmentos": [
        {"encabezado": r.encabezado, "linea_ini": r.linea_ini, "linea_fin": r.linea_fin, "texto": r.texto}
        for r in fragmentos]}, ensure_ascii=False, indent=1).encode("utf-8")


def extraido(texto: str) -> Nota:
    """Lo que escribe `a_json`. Viene de un zip ajeno: cualquier otra forma es un error, no se adivina."""
    datos = json.loads(texto)
    titulo, fragmentos = datos.get("titulo"), datos.get("fragmentos")
    tipos = {"encabezado": str, "linea_ini": int, "linea_fin": int, "texto": str}
    if not (isinstance(titulo, str | None) and isinstance(fragmentos, list)
            and all(isinstance(f, dict) and f.keys() == tipos.keys()
                    and all(type(f[k]) is t for k, t in tipos.items()) for f in fragmentos)):
        raise ValueError("texto extraído con otra forma")
    return Nota([Fragmento(f["encabezado"], f["linea_ini"], f["linea_fin"], f["texto"]) for f in fragmentos],
                [], {}, False, titulo or None)
