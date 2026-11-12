from pathlib import Path

from doll import grep
from doll.corpus import Corpus
from doll.evaluar import evaluar, evaluar_generacion
from doll.preguntar import Cita, Respuesta

NOTAS = Corpus("t", Path(__file__).parent / "boveda").notas()
ESCAPES = "recursos/oficios/Escapes.md"


def motor(consulta, k):
    return grep.buscar(consulta, NOTAS, k)


def test_terminos_quita_vacias_y_repetidos():
    assert grep.terminos("¿Qué es el escape, el ESCAPE de áncora?") == ["escape", "áncora"]


def test_grep_no_ignora_acentos():
    assert grep.buscar("ancora", NOTAS, 5) == []


def test_grep_ordena_por_terminos_distintos():
    assert grep.buscar("marcha temperatura volante", NOTAS, 1)[0][0].endswith("calibración.md")


def test_cruzada_exige_todas_las_notas():
    preguntas = [
        {"id": "a", "tipo": "directa", "pregunta": "escape áncora", "notas": [ESCAPES]},
        {"id": "b", "tipo": "cruzada", "pregunta": "escape áncora", "notas": [ESCAPES, "no/existe.md"]},
        {"id": "c", "tipo": "no_respondible", "pregunta": "escape"},
    ]
    r = evaluar(preguntas, motor)
    assert r.por_tipo == {"directa": (1, 1), "cruzada": (0, 1)}
    assert r.fallos == ["b"] and r.recall == 0.5


def test_notas_equivalentes_cuentan_con_una():
    preguntas = [{"id": "a", "tipo": "directa", "pregunta": "escape áncora", "notas": [["no/existe.md", ESCAPES]]},
                 {"id": "b", "tipo": "cruzada", "pregunta": "escape áncora", "notas": [["no/existe.md"], ESCAPES]}]
    r = evaluar(preguntas, motor)
    assert r.por_tipo == {"directa": (1, 1), "cruzada": (0, 1)} and r.fallos == ["b"]


def respuesta(*rutas):
    return Respuesta(texto="ok", citas=[Cita("x", r, 1, 1, False) for r in rutas])


def test_generacion_exige_citar_todas_las_notas(tmp_path):
    preguntas = [
        {"id": "a", "tipo": "cruzada", "pregunta": "dos", "notas": ["x.md", "y.md"]},
        {"id": "b", "tipo": "cruzada", "pregunta": "una", "notas": ["x.md", "y.md"]},
        {"id": "c", "tipo": "no_respondible", "pregunta": "nada"},
    ]
    salidas = {"dos": respuesta("x.md", "y.md"), "una": respuesta("x.md"), "nada": Respuesta(no_encontrado=True)}
    g = evaluar_generacion(preguntas, salidas.__getitem__, tmp_path / "s.jsonl")
    assert (g.todas_las_notas, g.alguna_nota, g.respondibles) == (1, 2, 2)
    assert g.no_encontrado == 1 and g.fallos == ["b"]


def test_generacion_acepta_notas_equivalentes(tmp_path):
    preguntas = [{"id": "a", "tipo": "cruzada", "pregunta": "dos", "notas": [["x.md", "z.md"], "y.md"]},
                 {"id": "b", "tipo": "cruzada", "pregunta": "una", "notas": [["x.md", "z.md"], "y.md"]}]
    salidas = {"dos": respuesta("z.md", "y.md"), "una": respuesta("y.md")}
    g = evaluar_generacion(preguntas, salidas.__getitem__, tmp_path / "s.jsonl")
    assert (g.todas_las_notas, g.alguna_nota) == (1, 2) and g.fallos == ["b"]


def test_citar_la_nota_sin_el_dato_no_trae_evidencia(tmp_path):
    preguntas = [{"id": "a", "tipo": "directa", "pregunta": "¿cuál?", "notas": [ESCAPES], "evidencia": ["áncora suiza"]},
                 {"id": "b", "tipo": "directa", "pregunta": "¿otra?", "notas": [ESCAPES], "evidencia": ["Áncora  suiza"]},
                 {"id": "c", "tipo": "directa", "pregunta": "¿sin?", "notas": [ESCAPES]}]
    respuestas = iter([Respuesta(texto="otra cosa", citas=[Cita("otra cosa", ESCAPES, 1, 2, False)]),
                       Respuesta(texto="la áncora suiza", citas=[Cita("texto", ESCAPES, 1, 2, False)]),
                       Respuesta(texto="x", citas=[Cita("x", ESCAPES, 1, 2, False)])])
    g = evaluar_generacion(preguntas, lambda _: next(respuestas), tmp_path / "s.jsonl")
    assert g.todas_las_notas == 3
    assert (g.traen_evidencia, g.con_evidencia, g.sin_evidencia) == (1, 2, ["a"])


def test_evaluar_busquedas_cuenta_por_nota_y_el_primer_lugar():
    from doll.evaluar import evaluar_busquedas

    busquedas = [{"id": "s1", "consulta": "a", "relevantes": ["x", "y"]},
                 {"id": "s2", "consulta": "b", "relevantes": ["z"]}]
    orden = {"a": ["q", "x", "w"], "b": ["z"]}
    assert evaluar_busquedas(busquedas, orden.__getitem__) == (0.75, 1, ["s1"])
