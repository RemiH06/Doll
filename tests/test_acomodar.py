import pytest

from doll import acomodar as acomodar_mod
from doll.acomodar import Propuesta, acomodar
from doll.corpus import Corpus
from doll.evaluar import evaluar_acomodar

CLASES = """# Clases

| Clase | Identificador | Qué se guarda | Destino | Material |
|---|---|---|---|---|
| Cuerpo | `cuerpo` | Rutina | [[Rutinas\\|Rutinas]] | Se borra |
| Negocios | `negocios` | Modelo | [[Talleres\\|Talleres]] | Se borra |
"""

REEL = """---
tipo: inspiración
clase: {clase}
---
# {tema}

- Fuente: @cuenta, https://example.com/r/1
- Destino: [[Rutinas]]

## Idea central
{idea}
"""


@pytest.fixture
def boveda(tmp_path):
    raiz = tmp_path / "b"
    (raiz / "insp").mkdir(parents=True)
    (raiz / "Talleres").mkdir()
    (raiz / "insp" / "0. Clases de inspiración.md").write_text(CLASES, "utf-8")
    (raiz / "insp" / "2026-01-01-a.md").write_text(
        REEL.format(clase="cuerpo", tema="Estiramientos de muñeca", idea="Rutina corta para relojeros."), "utf-8")
    (raiz / "insp" / "2026-01-02-b.md").write_text(
        REEL.format(clase="cuerpo", tema="Cobrar por reparar relojes", idea="Precio por pieza en un taller."),
        "utf-8")
    (raiz / "Talleres" / "Herrería.md").write_text("# Herrería\n\nForja de rejas.\n", "utf-8")
    return Corpus("t", raiz)


def test_propone_sin_leer_la_clase_previa(boveda, monkeypatch):
    corpus = boveda
    vistos = []

    def asignar(renglones, tabla):
        vistos.extend(renglones)
        return ["cuerpo", "negocios"]

    monkeypatch.setattr(acomodar_mod.tabla_clases, "asignar", asignar)
    p = acomodar(corpus, ["insp/2026-01-01-a.md", "insp/2026-01-02-b.md"])
    assert p == [Propuesta("insp/2026-01-01-a.md", "cuerpo", ("Rutinas",)),
                 Propuesta("insp/2026-01-02-b.md", "negocios", ("Talleres",))]
    assert len(vistos) == 2 and not any("clase" in v or "Rutinas" in v for v in vistos)


def test_rechaza_notas_fuera_del_corpus_o_de_varias_carpetas(boveda):
    corpus = boveda
    with pytest.raises(ValueError, match="No están"):
        acomodar(corpus, ["insp/no-existe.md"])
    with pytest.raises(ValueError, match="misma carpeta"):
        acomodar(corpus, ["insp/2026-01-01-a.md", "Talleres/Herrería.md"])


def test_evaluar_acomodar_cuenta_clase_enlaces_y_previa(boveda, tmp_path):
    corpus = boveda
    etiquetas = [{"ruta": "insp/2026-01-01-a.md", "clase": "cuerpo", "enlaces": ["Rutinas"]},
                 {"ruta": "insp/2026-01-02-b.md", "clase": "negocios", "enlaces": ["Talleres"]}]
    propuestas = [Propuesta("insp/2026-01-01-a.md", "cuerpo", ("Rutinas",)),
                  Propuesta("insp/2026-01-02-b.md", "cuerpo", ("Rutinas",))]
    r = evaluar_acomodar(etiquetas, propuestas, corpus.notas(), tmp_path / "u.jsonl")
    assert (r.clase, r.enlaces, r.previa, r.total) == (1, 1, 1, 2)
    assert r.fallos == ["2:negocios->cuerpo"]
