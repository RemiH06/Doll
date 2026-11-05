from pathlib import Path

from doll import grep
from doll.corpus import Corpus
from doll.evaluar import evaluar

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
