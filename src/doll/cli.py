import argparse
import sys

from doll import corpus as corpus_mod
from doll import evaluar as evaluar_mod
from doll import grep, indice
from doll.preguntar import AVISO_TERCEROS, preguntar


def _indice(nombre: str):
    corpus = corpus_mod.cargar(nombre)
    con = indice.abrir(corpus_mod.home() / f"{nombre}.db")
    return con, indice.indexar(con, corpus)


def _indexar(args) -> None:
    _, (cambiadas, quitadas) = _indice(args.corpus)
    print(f"{cambiadas} notas reindexadas, {quitadas} quitadas")


def _buscar(args) -> None:
    con, _ = _indice(args.corpus)
    for r in indice.buscar(con, args.consulta, args.k):
        print(f"{r.ruta}:{r.linea_ini}-{r.linea_fin} [{r.encabezado}]\n{r.texto}\n")


def _preguntar(args) -> None:
    corpus = corpus_mod.cargar(args.corpus)
    con, _ = _indice(args.corpus)
    r = preguntar(con, corpus, args.consulta, args.k)
    if r.fallo:
        print(f"Sin respuesta generada: {r.fallo}\nFragmentos recuperados:\n")
        for f in r.fragmentos:
            print(f"{f.ruta}:{f.linea_ini}-{f.linea_fin} [{f.encabezado}]\n{f.texto}\n")
    elif r.no_encontrado:
        print("No encontrado.")
    else:
        print(f"{r.texto}\n")
        for c in r.citas:
            aviso = f" [{AVISO_TERCEROS}]" if c.terceros else ""
            print(f"- {c.ruta}:{c.linea_ini}-{c.linea_fin}{aviso}\n  {c.texto}")
        if r.citas_descartadas:
            print(f"({r.citas_descartadas} citas descartadas: no aparecen en las notas)")


def _generacion(args) -> None:
    corpus = corpus_mod.cargar(args.corpus)
    con, _ = _indice(args.corpus)
    eval_dir = corpus_mod.home() / "eval"
    g = evaluar_mod.evaluar_generacion(
        evaluar_mod.cargar_preguntas(eval_dir / "preguntas.toml"),
        lambda consulta: preguntar(con, corpus, consulta, args.k),
        eval_dir / "ultima.jsonl",
    )
    print(f"con citas reales: {g.con_citas}/{g.respondibles}")
    print(f"citan una nota esperada: {g.nota_correcta}/{g.respondibles}")
    print(f"no respondibles detectadas: {g.no_encontrado}/{g.no_respondibles}")
    print(f"segundos promedio: {g.segundos_promedio:.1f}")
    print(f"fallos: {' '.join(g.fallos) or 'ninguno'}")


def _evaluar(args) -> None:
    if args.generacion:
        return _generacion(args)
    corpus = corpus_mod.cargar(args.corpus)
    notas = corpus.notas()
    con, _ = _indice(args.corpus)

    def fts(consulta: str, k: int) -> list[tuple[str, int]]:
        return [(r.ruta, len(r.texto)) for r in indice.buscar(con, consulta, k)]

    motores = {"grep": lambda c, k: grep.buscar(c, notas, k), "fts": fts}
    archivo = corpus_mod.home() / "eval" / "preguntas.toml"
    reporte = evaluar_mod.evaluar(evaluar_mod.cargar_preguntas(archivo), motores[args.motor], args.k)
    print(f"motor {args.motor} | {len(notas)} notas | {sum(map(len, notas.values()))} chars")
    print(f"recall@{args.k}: {reporte.recall:.2f}")
    for tipo, (aciertos, total) in reporte.por_tipo.items():
        print(f"  {tipo}: {aciertos}/{total}")
    print(f"chars por consulta: {reporte.chars_promedio:.0f}")
    print(f"segundos máx: {reporte.segundos_max:.3f}")
    print(f"fallos: {' '.join(reporte.fallos) or 'ninguno'}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="doll")
    parser.add_argument("--corpus", default="boveda")
    subs = parser.add_subparsers(required=True)

    ix = subs.add_parser("indexar", help="sincroniza el índice con las notas")
    ix.set_defaults(func=_indexar)

    bu = subs.add_parser("buscar", help="fragmentos con ruta y líneas")
    bu.add_argument("consulta")
    bu.add_argument("-k", type=int, default=5)
    bu.set_defaults(func=_buscar)

    pr = subs.add_parser("preguntar", help="respuesta del Baker doll con citas verificadas")
    pr.add_argument("consulta")
    pr.add_argument("-k", type=int, default=5)
    pr.set_defaults(func=_preguntar)

    ev = subs.add_parser("evaluar", help="mide un motor contra ~/.doll/eval/preguntas.toml")
    ev.add_argument("--motor", default="fts", choices=["grep", "fts"])
    ev.add_argument("--generacion", action="store_true", help="mide respuestas y citas con el Baker")
    ev.add_argument("-k", type=int, default=5)
    ev.set_defaults(func=_evaluar)

    args = parser.parse_args()
    args.func(args)
