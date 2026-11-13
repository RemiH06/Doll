import argparse
import sys
from pathlib import Path

from doll import corpus as corpus_mod
from doll import evaluar as evaluar_mod
from doll import grep, indice
from doll.indice import Filtro
from doll.preguntar import preguntar, texto_fragmentos, texto_respuesta


def _indice(corpus):
    con = indice.abrir(corpus.indice)
    return con, indice.indexar(con, corpus)


def _filtro(args, corpus) -> Filtro:
    return Filtro(args.tipo, args.dominio, terceros=corpus.terceros)


def _indexar(args) -> None:
    corpus = corpus_mod.cargar(args.floppy)
    con, (cambiadas, quitadas) = _indice(corpus)
    print(f"{corpus.nombre}: {cambiadas} notas reindexadas, {quitadas} quitadas")
    if args.sentido:
        from doll import sentido

        print(f"{sentido.llenar(con, corpus)} fragmentos de terceros embebidos")


def _buscar(args) -> None:
    corpus = corpus_mod.cargar(args.floppy)
    con, _ = _indice(corpus)
    if not args.sentido:
        return print(texto_fragmentos(indice.buscar(con, args.consulta, args.k, _filtro(args, corpus)), corpus))
    if args.tipo or args.dominio:
        raise SystemExit("--sentido busca solo en notas de terceros: no filtra por --tipo ni --dominio")
    from doll import sentido

    fragmentos, aviso = sentido.buscar(con, corpus, args.consulta, args.k)
    if aviso:
        print(aviso, file=sys.stderr)
    print(texto_fragmentos(fragmentos, corpus))


def _preguntar(args) -> None:
    corpus = corpus_mod.cargar(args.floppy)
    con, _ = _indice(corpus)
    print(texto_respuesta(preguntar(con, corpus, args.consulta, args.k, filtro=_filtro(args, corpus)), corpus))


def _generacion(args) -> None:
    corpus = corpus_mod.cargar(args.floppy)
    con, _ = _indice(corpus)
    eval_dir = corpus.eval
    g = evaluar_mod.evaluar_generacion(
        evaluar_mod.cargar_preguntas(eval_dir / f"{args.set}.toml"),
        lambda consulta: preguntar(con, corpus, consulta, args.k, filtro=Filtro(terceros=corpus.terceros)),
        eval_dir / f"ultima-{args.set}.jsonl",
    )
    print(f"con citas reales: {g.con_citas}/{g.respondibles}")
    print(f"citan todas sus notas: {g.todas_las_notas}/{g.respondibles}")
    print(f"citan alguna nota esperada: {g.alguna_nota}/{g.respondibles}")
    print(f"traen la evidencia: {g.traen_evidencia}/{g.con_evidencia} (sin ella: {' '.join(g.sin_evidencia) or 'ninguna'})")
    print(f"citan la página o sección de la evidencia: {g.citan_el_lugar}/{g.con_evidencia}")
    print(f"no respondibles detectadas: {g.no_encontrado}/{g.no_respondibles}")
    print(f"segundos promedio: {g.segundos_promedio:.1f}")
    print(f"fallos: {' '.join(g.fallos) or 'ninguno'}")


def _acomodar(args) -> None:
    from bakers.core import BakerError

    from doll.acomodar import acomodar, acomodar_nota, texto_propuestas, texto_propuestas_nota

    corpus = corpus_mod.cargar(args.floppy)
    if corpus.importado:
        raise SystemExit(f"{corpus.nombre!r} es importado: una copia fija no se acomoda")
    terceros = {corpus.es_terceros(r) for r in args.rutas}
    if True in terceros and False in terceros:
        raise SystemExit("No mezcles notas de inspiración con otras: se acomodan distinto")
    try:
        if True in terceros:
            return print(texto_propuestas(acomodar(corpus, args.rutas)))
        con, _ = _indice(corpus)
        print(texto_propuestas_nota(acomodar_nota(con, corpus, args.rutas)))
    except BakerError as e:
        raise SystemExit(f"Sin propuesta, el modelo no respondió: {e}") from None


def _evaluar_acomodar_boveda(args) -> None:
    import tomllib

    from doll.acomodar import acomodar_nota

    corpus = corpus_mod.cargar(args.floppy)
    con, _ = _indice(corpus)
    eval_dir = corpus.eval
    etiquetas = tomllib.loads((eval_dir / "acomodar-boveda.toml").read_text(encoding="utf-8"))["notas"]
    # Dos mitades: cada una se acomoda sin estar en los ejemplos, y la otra mitad sí cuenta como bóveda.
    propuestas = {}
    for mitad in (etiquetas[0::2], etiquetas[1::2]):
        propuestas |= {p.ruta: p for p in acomodar_nota(con, corpus, [e["ruta"] for e in mitad])}
    r = evaluar_mod.evaluar_acomodar_nota(etiquetas, [propuestas[e["ruta"]] for e in etiquetas],
                                          eval_dir / "ultima-acomodar-boveda.jsonl")
    for faceta, (a, t) in r.aciertos.items():
        print(f"{faceta}: {a}/{t} ({a / t:.0%})")
    tp, propuestos, etiquetados = r.enlaces
    print(f"enlaces: precisión {tp / max(propuestos, 1):.2f}, recall {tp / max(etiquetados, 1):.2f}")
    print(f"fallos: {' '.join(r.fallos) or 'ninguno'}")


def _evaluar_acomodar(args) -> None:
    import tomllib

    from doll.acomodar import acomodar

    corpus = corpus_mod.cargar(args.floppy)
    eval_dir = corpus.eval
    etiquetas = tomllib.loads((eval_dir / "acomodar.toml").read_text(encoding="utf-8"))["notas"]
    propuestas = acomodar(corpus, [e["ruta"] for e in etiquetas])
    r = evaluar_mod.evaluar_acomodar(etiquetas, propuestas, corpus.notas(), eval_dir / "ultima-acomodar.jsonl")
    print(f"clase: {r.clase}/{r.total} ({r.clase / r.total:.0%})")
    print(f"enlaces exactos: {r.enlaces}/{r.total}")
    print(f"clase que ya traía la nota: {r.previa}/{r.total}")
    print(f"fallos: {' '.join(r.fallos) or 'ninguno'}")


def _evaluar_inspo(args) -> None:
    import tomllib

    from doll import sentido

    corpus = corpus_mod.cargar(args.floppy)
    con, _ = _indice(corpus)
    busquedas = tomllib.loads((corpus.eval / "inspo-busquedas.toml").read_text("utf-8"))["busquedas"]
    terceros = Filtro(solo=corpus.terceros)

    def notas(fragmentos) -> list[str]:
        return list(dict.fromkeys(r.ruta for r in fragmentos))

    def por_sentido(consulta: str) -> list[str]:
        fragmentos, aviso = sentido.buscar(con, corpus, consulta, 40)
        if aviso:
            raise SystemExit(aviso)  # medir FTS dos veces no dice nada
        return notas(fragmentos)

    for nombre, motor in (("fts", lambda c: notas(indice.buscar(con, c, 40, terceros))), ("sentido", por_sentido)):
        recall, aciertos, fallos = evaluar_mod.evaluar_busquedas(busquedas, motor)
        print(f"{nombre}: recall@5 {recall:.2f}, acierto@1 {aciertos}/{len(busquedas)}, incompletas: {' '.join(fallos) or 'ninguna'}")


def _mcp(args) -> None:
    from doll.mcp_server import crear  # import aquí: la CLI no carga el paquete mcp

    crear(args.floppy).run()


def _exportar(args) -> None:
    from doll import floppy

    corpus = corpus_mod.cargar(args.floppy)
    salida = args.salida or Path(f"{corpus.nombre}-v{corpus.version}.zip")
    e = floppy.exportar(corpus, salida, args.con_eval)
    print(f"{salida}: {e.notas} notas, {e.documentos} documentos, {e.vectores} vectores, versión {corpus.version}")
    if e.sin_texto:
        print(f"{e.sin_texto} documentos sin texto no van en el zip")
    if e.sin_vector:
        print(f"{e.sin_vector} fragmentos de terceros sin vector: quien importe los embebe. Para que viajen, corre"
              f" `doll --floppy {corpus.nombre} indexar --sentido` y exporta otra vez")


def _importar(args) -> None:
    from doll import floppy

    i = floppy.importar(args.zip, args.nombre)
    como = "propio" if i.terceros is None else f"de terceros ({i.terceros})"
    print(f"{i.nombre}: importado como {como}, {i.vectores} vectores reusados. Móntalo con `doll montar {i.nombre}`")


def _montar(args) -> None:
    if args.nombre:
        corpus_mod.montar(args.nombre)
    try:
        actual = corpus_mod.montado()
    except SystemExit:
        actual = None  # sin montar todavía: igual se listan
    disponibles = corpus_mod.disponibles()
    if not disponibles:
        print(f"Sin floppies en {corpus_mod.floppies()}")
    for nombre in disponibles:
        print(f"{'*' if nombre == actual else ' '} {nombre}")


def _evaluar(args) -> None:
    if args.set == "acomodar":
        return _evaluar_acomodar(args)
    if args.set == "acomodar-boveda":
        return _evaluar_acomodar_boveda(args)
    if args.set == "inspo-busquedas":
        return _evaluar_inspo(args)
    if args.generacion:
        return _generacion(args)
    corpus = corpus_mod.cargar(args.floppy)
    notas, documentos, _ = corpus.leer()
    if args.motor == "grep" and documentos:
        raise SystemExit("grep solo lee Markdown: no sirve de línea base en un floppy con HTML o PDF")
    con, _ = _indice(corpus)

    def fts(consulta: str, k: int) -> list[tuple[str, int]]:
        return [(r.ruta, len(r.texto)) for r in indice.buscar(con, consulta, k, Filtro(terceros=corpus.terceros))]

    motores = {"grep": lambda c, k: grep.buscar(c, notas, k), "fts": fts}
    archivo = corpus.eval / f"{args.set}.toml"
    reporte = evaluar_mod.evaluar(evaluar_mod.cargar_preguntas(archivo), motores[args.motor], args.k)
    # Del índice, no de la fuente: un PDF sin texto no cuenta, y un documento solo existe ya extraído.
    archivos, chars = con.execute("SELECT count(DISTINCT ruta), coalesce(sum(length(texto)), 0) FROM fragmentos").fetchone()
    print(f"motor {args.motor} | {archivos} archivos con texto | {chars} chars")
    print(f"recall@{args.k}: {reporte.recall:.2f}")
    for tipo, (aciertos, total) in reporte.por_tipo.items():
        print(f"  {tipo}: {aciertos}/{total}")
    print(f"chars por consulta: {reporte.chars_promedio:.0f}")
    print(f"segundos máx: {reporte.segundos_max:.3f}")
    print(f"fallos: {' '.join(reporte.fallos) or 'ninguno'}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="doll")
    parser.add_argument("--floppy", help="usa este floppy y no el montado, solo en este comando")
    subs = parser.add_subparsers(required=True)

    ix = subs.add_parser("indexar", help="sincroniza el índice con las notas")
    ix.add_argument("--sentido", action="store_true", help="también embebe las notas de terceros. Tarda la primera vez: en un floppy grande,"
                    " hazlo aparte o antes de exportar, porque `buscar --sentido` no embebe tanto en línea")
    ix.set_defaults(func=_indexar)

    bu = subs.add_parser("buscar", help="fragmentos con ruta y líneas")
    bu.add_argument("consulta")
    bu.add_argument("-k", type=int, default=5)
    bu.add_argument("--tipo", help="solo notas con este tipo")
    bu.add_argument("--dominio", help="solo notas con este dominio")
    bu.add_argument("--sentido", action="store_true", help="por sentido, solo en notas de terceros (la inspiración)")
    bu.set_defaults(func=_buscar)

    pr = subs.add_parser("preguntar", help="respuesta del Baker doll con citas verificadas")
    pr.add_argument("consulta")
    pr.add_argument("-k", type=int, default=5)
    pr.add_argument("--tipo", help="solo notas con este tipo")
    pr.add_argument("--dominio", help="solo notas con este dominio")
    pr.set_defaults(func=_preguntar)

    ev = subs.add_parser("evaluar", help="mide un motor contra eval/<set>.toml del floppy")
    ev.add_argument("--motor", default="fts", choices=["grep", "fts"])
    ev.add_argument("--set", default="preguntas", choices=["preguntas", "control", "nuevas", "confirmacion", "docs", "acomodar",
                                                 "acomodar-boveda", "inspo-busquedas"])
    ev.add_argument("--generacion", action="store_true", help="mide respuestas y citas con el Baker")
    ev.add_argument("-k", type=int, default=5)
    ev.set_defaults(func=_evaluar)

    ac = subs.add_parser("acomodar", help="propone dónde va cada nota (clase si es de inspiración); no escribe")
    ac.add_argument("rutas", nargs="+", help="relativas a la bóveda; las de inspiración, en la carpeta de su tabla de clases")
    ac.set_defaults(func=_acomodar)

    mo = subs.add_parser("montar", help="monta un floppy para la CLI, el MCP y el panel; sin nombre, lista los floppies")
    mo.add_argument("nombre", nargs="?")
    mo.set_defaults(func=_montar)

    ex = subs.add_parser("exportar", help="zip firmado del floppy, sin lo excluido ni lo que oculta mcp_excluir")
    ex.add_argument("-o", "--salida", type=Path, help="por defecto <floppy>-v<version>.zip aquí")
    ex.add_argument("--con-eval", action="store_true", help="también las preguntas de eval/")
    ex.set_defaults(func=_exportar)

    im = subs.add_parser("importar", help="instala un floppy desde un zip; si no lo firmaste tú, entra como de terceros")
    im.add_argument("zip", type=Path)
    im.add_argument("--nombre", help="otro nombre para el floppy; por defecto, el del zip")
    im.set_defaults(func=_importar)

    mc = subs.add_parser("mcp", help="servidor MCP por stdio; sin --floppy, sigue al montado en cada llamada")
    mc.set_defaults(func=_mcp)

    args = parser.parse_args()
    args.func(args)
