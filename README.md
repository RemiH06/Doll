![Made with Python](https://forthebadge.com/images/badges/made-with-python.svg)
![SQLite](https://img.shields.io/badge/-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)
![Rust](https://img.shields.io/badge/-Rust-000000?style=for-the-badge&logo=rust&logoColor=white)

```ascii
██████╗  ██████╗ ██╗     ██╗
██╔══██╗██╔═══██╗██║     ██║
██║  ██║██║   ██║██║     ██║
██║  ██║██║   ██║██║     ██║
██████╔╝╚██████╔╝███████╗███████╗
╚═════╝  ╚═════╝ ╚══════╝╚══════╝

       by RemLam (@RemiH06)          version 0.3.0
```

![AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue.svg?style=for-the-badge)

### Descripción general

**Doll** es un RAG local sobre notas Markdown: busca en tus notas sin leerlas completas, responde con un modelo propio y verifica por código que cada cita exista en el texto recuperado. El nombre viene de RAG doll, muñeca de trapo.

El código es público y los datos no: los índices, la configuración de cada corpus y las preguntas de evaluación viven en `~/.doll/`. Los ejemplos y las pruebas usan solo la bóveda ficticia de `tests/boveda/`.

```diff
- En desarrollo: funciona en la CLI; la interfaz puede cambiar.
```

## Instalación

1. Instala [uv](https://docs.astral.sh/uv/) y [Rust](https://rustup.rs/): `uv sync` compila `doll-parser` con `cargo` y lo deja en el entorno.
2. Clona el repo y sincroniza el entorno:

```bash
git clone https://github.com/RemiH06/Doll.git
cd Doll
uv sync
uv run pytest
```

En una máquina sin Rust, compila `doll-parser` donde sí lo haya y lleva el wheel:

```bash
uv build --wheel parser -o dist                       # en la máquina con Rust
uv venv                                               # en la otra, dentro del clon
uv pip install dist/doll_parser-*.whl
uv pip install -e /ruta/a/Bakery/bakers               # o el paquete bakers desde git
uv pip install -e . --no-sources
```

Ahí no corras `uv sync` ni `uv pip install` sin `--no-sources`: los dos leen `[tool.uv.sources]`, compilan `doll-parser` y cambian `bakers` por el de git. Para actualizar, `git pull` basta mientras no cambie `parser/`, porque `doll` queda editable; `uv pip install -e . --no-sources` refresca la versión instalada. Si cambia `parser/`, vuelve a compilar y a instalar el wheel con `--reinstall`.

Crea `~/.doll/corpus.toml`, con rutas relativas a `ruta`:

```toml
[boveda]
ruta = "/ruta/a/tus/notas"
excluir = ["privado/**"]
terceros = ["recortes/**"]
mcp_excluir = ["borradores/**"]

[boveda.alcances]
'notas? de recortes' = "recortes/**"
```

`gente/**` y `life/**` quedan fuera siempre. `mcp_excluir` deja notas fuera del MCP, pero no de la CLI; el servidor no arranca sin esa clave (`[]` si no quieres ocultar nada). `alcances` es opcional: si la pregunta coincide con una regex, `preguntar` busca solo en esa carpeta y la frase no cuenta como tema. `preguntar` usa el paquete [`bakers`](https://github.com/RemiH06/Bakery) y necesita `BAKERS_URL` y `BAKERS_API_KEY`; `buscar` funciona sin ellas.

## Launch arguments

- `doll indexar [--sentido]`: sincroniza el índice con las notas; solo reprocesa las que cambiaron. Con `--sentido`, también embebe los fragmentos de terceros que no tienen vector (la primera vez tarda unos 0.4 s por fragmento en CPU).
- `doll buscar "consulta" [-k N] [--tipo T] [--dominio D] [--sentido]`: fragmentos con ruta y líneas. Con `--sentido`, busca por sentido y solo en notas de terceros.
- `doll preguntar "consulta" [-k N] [--tipo T] [--dominio D]`: respuesta con citas verificadas.
- `doll acomodar RUTA...`: propone dónde va cada nota; no escribe nada. Notas de una carpeta con tabla de clases: clase y enlaces. Las demás: carpeta, `tipo`, `estado`, dominio principal, proyecto y enlaces.
- `doll mcp`: servidor MCP por stdio, con las herramientas `buscar`, `buscar_inspiracion` (por sentido, en notas de terceros) y `preguntar_notas`.
- `doll evaluar [--motor fts|grep] [--generacion] [--set preguntas|control|nuevas|confirmacion|docs|acomodar|acomodar-boveda|inspo-busquedas] [-k N]`: mide contra `~/.doll/eval/<set>.toml`. `inspo-busquedas` compara FTS5 y la búsqueda por sentido.
- `--corpus NOMBRE`, antes del comando: elige el corpus; por defecto, `boveda`.

```bash
uv run doll preguntar "¿Cuándo se inventó el escape de áncora?"
```

Para usarlo desde Claude Code:

```bash
claude mcp add --scope user doll -- uv run --no-sync --project /ruta/a/Doll doll mcp
```

`--no-sync` evita que `uv` intente reinstalar `doll.exe` al arrancar: en Windows falla si otra sesión tiene el servidor abierto. Después de un `uv sync`, reinicia las sesiones que usan el MCP.

## Features

- Fragmentos por encabezado, con ruta, líneas y hash por nota, partidos por `doll-parser`, un filtro en Rust.
- Búsqueda FTS5 que ignora acentos, sin servicios externos.
- Búsqueda por sentido en las notas de terceros, con vectores de bge-m3 que calcula el gateway de Bakery en CPU. Los vectores se guardan en el índice por hash del texto: una nota que no cambia no se vuelve a embeber. Sin gateway, responde con FTS5 sobre las mismas notas y lo dice.
- Tope de fragmentos por nota y expansión a las notas enlazadas con `[[wikilinks]]` desde la mejor.
- Filtro por `tipo` y `dominio` del frontmatter.
- Si la pregunta pide una carpeta, `preguntar` solo busca ahí; las frases que lo activan se configuran.
- Un enlace a una nota excluida se tapa en el índice: no queda ni su nombre.
- Servidor MCP para consultar las notas desde Claude Code.
- `preguntar` le da al modelo el resto de la mejor nota; `buscar` entrega solo lo que coincide.
- Si la pregunta nombra algo que no aparece en lo recuperado, responde "no encontrado" sin llamar al modelo.
- Citas comprobadas contra el texto recuperado; si ninguna sobrevive, responde "no encontrado".
- Texto de terceros marcado como no confiable en el prompt y en la salida.
- `buscar` sigue funcionando sin modelo, y `preguntar` lo dice y entrega los fragmentos.
- Log local con tiempos y conteos, sin preguntas ni fragmentos.
- `acomodar` propone la clase de una nota con el Baker `clasificador` y sus enlaces según la tabla de clases de la carpeta. La clase que la nota ya trae no entra al modelo, y nada se escribe: la propuesta la aplica una persona.
- Para las demás notas, `acomodar` propone carpeta, `tipo`, `estado`, dominio principal, proyecto y enlaces. El modelo lee el título y el inicio de la nota, sin frontmatter, ruta ni enlaces. Las opciones salen del índice y se describen con notas que ya las tienen, y cada carpeta con la línea de la nota índice que la nombra. `tipo` y `estado` se toman de la carpeta propuesta cuando casi todas sus notas los comparten. Si casi todas las notas de la carpeta propuesta declaran su proyecto con `ficha:`, la nota se lee completa y el modelo elige entre los proyectos que ella nombra.

## Limitaciones

Medido con un modelo local contra preguntas privadas sobre un corpus real.

- Sobre 521 notas, en un set nuevo: citó todas sus notas en 19 de 22 preguntas con respuesta, y el dato exacto salió en 17 de 22. Citar la nota no prueba contestar. En los sets de ajuste baja a cerca del 75 %.
- En ese set rechazó las 11 preguntas sin respuesta, después de reclasificar 2 que sí se podían contestar; en otras pruebas limpias rechazó 5 de 7. Si el tema aparece en las notas, puede contestar algo cercano con citas reales: una cita verificada prueba que el texto existe, no que responda la pregunta.
- A veces dice "no encontrado" aunque el dato esté en lo recuperado.
- `buscar` y `preguntar` buscan por palabras: si la pregunta usa otro vocabulario que la nota, pueden no encontrarla. La búsqueda por sentido solo cubre notas de terceros.
- En 16 búsquedas sobre notas de terceros, la búsqueda por sentido trajo el 71 % de las notas relevantes entre las 5 primeras, contra 58 % de FTS5, y las dos acertaron la primera nota en 11 de 16. Cuando la búsqueda repite las palabras de la nota, FTS5 puede ganar. No es ciego: las notas relevantes se eligieron leyendo las notas.
- El alcance solo actúa con las frases configuradas y por carpeta: "qué dice X sobre Y" puede contestar con otra nota.
- El chequeo de nombres solo reconoce palabras con mayúscula, y basta con que el nombre salga en cualquier fragmento recuperado.
- Agregar notas puede bajar el recall de las que ya estaban: al crecer el corpus hay que volver a medir. Pasó al llegar a 521 notas: tres notas recortadas sobre un mismo tema llenaron los 5 lugares y una pregunta perdió la ficha de proyecto que también necesitaba. Ni el alcance por carpeta ni la fusión con vectores la recuperan.
- Las preguntas de recuperación y de generación se ajustaron sobre el mismo set, y ningún set es del todo ciego.
- `acomodar` acertó la clase en 29 de 34 notas etiquetadas (85 %) y los enlaces en 29 de 34. No es ciego: las etiquetas partieron de la clase que ya había puesto el mismo clasificador. Solo cubre notas de una carpeta con tabla de clases.
- Para las demás notas, en 30 notas etiquetadas y medidas en dos mitades: carpeta 26/30 (87 %), `tipo` 22/30, `estado` 22/30, dominio principal 29/30 y proyecto 15/17 (88 %, sin contar fichas, donde el título lo dice). `tipo` es una sugerencia que hay que revisar. El proyecto se ajustó sobre el mismo set: falta confirmarlo con notas nuevas. Los enlaces por FTS tienen precisión 0.31 y recall 0.42. Cambiar una nota del lote movió una propuesta de carpeta en otra: las notas del lote le dan contexto al modelo. No es ciego: las etiquetas salen del frontmatter de las notas.
- `acomodar` manda todas las notas en una sola llamada a propósito. Con lotes de 10, 5 o 1 nota acertó 24 de 34: las otras notas del lote le sirven de contexto al modelo.

Probado y descartado, con las mismas preguntas y etiquetas:

- **Búsqueda híbrida con vectores** (bge-m3 y fusión RRF con FTS5): recupera paráfrasis que FTS5 pierde, pero hace perder otras preguntas, en 2 de 5 sets con RRF a partes iguales y en 1 de 5 al darle el doble de peso a FTS5. FTS5 sigue sola.
- **[Laya](https://huggingface.co/convaiinnovations/laya-multilingual) en lugar del clasificador:** sin especializar, acertó la clase en 11 de 34 notas en su mejor variante, contra 29 de 34. Es unas 5 veces más rápido, pero da confianzas altas cuando se equivoca, y especializarlo pide cientos de notas bien etiquetadas.

## Future Features

- Confirmar el proyecto que propone `acomodar` con notas que no estuvieron en el ajuste.

## Autoría

por RemLam ([@RemiH06](https://github.com/RemiH06))
