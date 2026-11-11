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

       by RemLam (@RemiH06)          version 0.1.0
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

- `doll indexar`: sincroniza el índice con las notas; solo reprocesa las que cambiaron.
- `doll buscar "consulta" [-k N] [--tipo T] [--dominio D]`: fragmentos con ruta y líneas.
- `doll preguntar "consulta" [-k N] [--tipo T] [--dominio D]`: respuesta con citas verificadas.
- `doll acomodar RUTA...`: propone clase y enlaces para notas de una carpeta con tabla de clases; no escribe nada.
- `doll mcp`: servidor MCP por stdio, con las herramientas `buscar` y `preguntar_notas`.
- `doll evaluar [--motor fts|grep] [--generacion] [--set preguntas|control|nuevas|confirmacion|docs|acomodar] [-k N]`: mide contra `~/.doll/eval/<set>.toml`.
- `--corpus NOMBRE`, antes del comando: elige el corpus; por defecto, `boveda`.

```bash
uv run doll preguntar "¿Cuándo se inventó el escape de áncora?"
```

## Features

- Fragmentos por encabezado, con ruta, líneas y hash por nota, partidos por `doll-parser`, un filtro en Rust.
- Búsqueda FTS5 que ignora acentos, sin servicios externos.
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

## Limitaciones

Medido con un modelo local contra preguntas privadas sobre un corpus real.

- Sobre 337 notas, en un set nuevo: citó todas sus notas en 19 de 22 preguntas con respuesta, y el dato exacto salió en 17 de 22. Citar la nota no prueba contestar. En los sets de ajuste baja a cerca del 75 %.
- En ese set rechazó las 11 preguntas sin respuesta, después de reclasificar 2 que sí se podían contestar; en otras pruebas limpias rechazó 5 de 7. Si el tema aparece en las notas, puede contestar algo cercano con citas reales: una cita verificada prueba que el texto existe, no que responda la pregunta.
- A veces dice "no encontrado" aunque el dato esté en lo recuperado.
- La búsqueda es por palabras: si la pregunta usa otro vocabulario que la nota, puede no encontrarla.
- El alcance solo actúa con las frases configuradas y por carpeta: "qué dice X sobre Y" puede contestar con otra nota.
- El chequeo de nombres solo reconoce palabras con mayúscula, y basta con que el nombre salga en cualquier fragmento recuperado.
- Agregar notas puede bajar el recall de las que ya estaban: al crecer el corpus hay que volver a medir.
- Las preguntas de recuperación y de generación se ajustaron sobre el mismo set, y ningún set es del todo ciego.
- `acomodar` acertó la clase en 29 de 34 notas etiquetadas (85 %) y los enlaces en 29 de 34. No es ciego: las etiquetas partieron de la clase que ya había puesto el mismo clasificador. Solo cubre notas de una carpeta con tabla de clases; todavía no propone carpeta ni proyecto para otras notas.

## Future Features

- Acomodar notas que no traen tabla de clases: propuestas de carpeta, etiquetas y proyecto.

## Autoría

por RemLam ([@RemiH06](https://github.com/RemiH06))
