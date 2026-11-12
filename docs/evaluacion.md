# Evaluación

Nada entra a Doll sin medirse: cada cambio a la búsqueda, al prompt o al modelo se compara contra sets de preguntas con la respuesta ya etiquetada. Los sets son privados (`~/.doll/eval/`), porque contienen preguntas sobre notas reales; aquí solo se publican los números agregados.

## Cómo se mide

```bash
uv run doll evaluar --set preguntas                # recall de la recuperación con FTS5
uv run doll evaluar --set preguntas --motor grep   # línea base con grep
uv run doll evaluar --set preguntas --generacion   # respuestas con citas
```

Cada corrida deja el detalle por pregunta en `~/.doll/eval/ultima-<set>.jsonl`.

### Preguntas

`<set>.toml` con una tabla `[[p]]` por pregunta. `tipo` es `directa`, `cruzada` (pide más de una nota) o `no_respondible`. Una lista dentro de `notas` son notas equivalentes: basta con una. `evidencia` es el dato exacto que debe salir en la respuesta. Con la bóveda ficticia de `tests/boveda/`:

```toml
[[p]]
id = "d01"
tipo = "directa"
pregunta = "¿Cuándo se inventó el escape de áncora?"
notas = ["recursos/oficios/Escapes.md"]
evidencia = ["1657"]

[[p]]
id = "n01"
tipo = "no_respondible"
pregunta = "¿Quién fundó la casa Ferrán?"
```

- **Recall:** la pregunta acierta si todas sus notas están entre los fragmentos recuperados.
- **Generación:** una respuesta acierta si cita todas sus notas; una no respondible acierta si responde "no encontrado". Aparte se cuenta cuántas traen la evidencia.

### Búsquedas por sentido

`inspo-busquedas.toml`, con `[[busquedas]]`: `id`, `consulta` y `relevantes` (rutas). Reporta recall@5 (relevantes entre las 5 primeras, sobre el mínimo entre 5 y las relevantes) y aciertos en la primera, para FTS5 y para la búsqueda por sentido.

### acomodar

`acomodar.toml` y `acomodar-boveda.toml`, con `[[notas]]`: la ruta y lo que se espera (clase y enlaces, o carpeta, `tipo`, `estado`, dominio, proyecto y enlaces). Cuenta aciertos por campo; los enlaces, como precisión y recall.

Las etiquetas las propone Claude y las confirma una persona antes de medir. Un set que se usó para ajustar ya no prueba nada: cada iteración se confirma con preguntas nuevas.

## Resultados

Medido con un modelo local sobre un corpus real de 521 notas, con preguntas privadas.

| Qué | Resultado |
|---|---|
| `preguntar`, set nuevo | Citó todas sus notas en 19 de 22 preguntas con respuesta; el dato exacto salió en 17 de 22. En los sets de ajuste baja a cerca del 75 %. |
| `preguntar`, sin respuesta | Rechazó las 11 del set nuevo (tras reclasificar 2 que sí se podían contestar); en otras pruebas limpias, 5 de 7. |
| Búsqueda por sentido, 16 búsquedas | 71 % de las notas relevantes entre las 5 primeras, contra 58 % de FTS5; las dos acertaron la primera en 11 de 16. |
| `acomodar`, inspiración (34 notas) | Clase 29/34 (85 %), enlaces 29/34. |
| `acomodar`, resto de la bóveda (30 notas) | Carpeta 26/30 (87 %), `tipo` 22/30, `estado` 22/30, dominio principal 29/30, proyecto 15/17 (88 %, sin contar fichas). Enlaces: precisión 0.31, recall 0.42. |

## Limitaciones

- Citar la nota no prueba contestar: una cita verificada prueba que el texto existe, no que responda la pregunta. Si el tema aparece en las notas, puede contestar algo cercano con citas reales.
- A veces dice "no encontrado" aunque el dato esté en lo recuperado.
- `buscar` y `preguntar` buscan por palabras: si la pregunta usa otro vocabulario que la nota, pueden no encontrarla. La búsqueda por sentido solo cubre notas de terceros, y cuando la consulta repite las palabras de la nota, FTS5 puede ganarle.
- El alcance solo actúa con las frases configuradas y por carpeta: "qué dice X sobre Y" puede contestar con otra nota.
- El chequeo de nombres solo reconoce palabras con mayúscula, y basta con que el nombre salga en cualquier fragmento recuperado.
- Agregar notas puede bajar el recall de las que ya estaban. Pasó al llegar a 521 notas: tres notas recortadas sobre un mismo tema llenaron los 5 lugares y una pregunta perdió la ficha de proyecto que también necesitaba. Ni el alcance por carpeta ni la fusión con vectores la recuperan.
- Ningún set es del todo ciego: las preguntas de recuperación y de generación se ajustaron sobre el mismo set, las etiquetas de inspiración partieron de la clase que ya había puesto el mismo clasificador, y las de la bóveda salen del frontmatter de las notas.
- `tipo` es una sugerencia que hay que revisar. El proyecto se ajustó sobre el mismo set: falta confirmarlo con notas nuevas.
- Cambiar una nota del lote de `acomodar` puede mover la propuesta de otra.

## Probado y descartado

Con las mismas preguntas y etiquetas:

- **Búsqueda híbrida con vectores en toda la bóveda** (bge-m3 y fusión RRF con FTS5): recupera paráfrasis que FTS5 pierde, pero hace perder otras preguntas, en 2 de 5 sets con RRF a partes iguales y en 1 de 5 al darle el doble de peso a FTS5. FTS5 sigue sola.
- **Lotes más chicos en `acomodar`:** con 10, 5 o 1 nota por llamada acertó 24 de 34, contra 29 de 34 en una sola llamada.
- **[Laya](https://huggingface.co/convaiinnovations/laya-multilingual) en lugar del clasificador:** sin especializar, 11 de 34 en su mejor variante. Es unas 5 veces más rápido, pero da confianzas altas cuando se equivoca, y especializarlo pide cientos de notas bien etiquetadas.
- **Proponer la sección Aplicación de un reel** (qué proyecto aprovecha la idea): 23 de 38 en la mejor variante, igual que tomar el primer destino de la clase sin modelo.
