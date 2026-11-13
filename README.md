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

**Doll** es un RAG local sobre notas Markdown: busca en tus notas sin leerlas completas, responde con un modelo propio y verifica por código que cada cita exista en el texto recuperado. También propone dónde va una nota nueva, sin escribir en ella. El nombre viene de RAG doll, muñeca de trapo.

El código es público y los datos no: cada corpus es un floppy en `~/.doll/floppies/`, con su configuración, su índice y sus preguntas de evaluación. Los ejemplos y las pruebas usan solo la bóveda ficticia de `tests/boveda/`.

Documentación completa: [remih06.github.io/Doll](https://remih06.github.io/Doll/). Para que un agente use Doll hay dos skills de ejemplo en [`skills/`](skills/).

```diff
- En desarrollo: funciona en la CLI; la interfaz puede cambiar.
```

## Instalación

1. Instala [uv](https://docs.astral.sh/uv/) y [Rust](https://rustup.rs/): `uv sync` compila `doll-parser` con `cargo`. Sin Rust, ver [Instalar sin Rust](https://remih06.github.io/Doll/#sin-rust).
2. Clona el repo y sincroniza el entorno:

```bash
git clone https://github.com/RemiH06/Doll.git
cd Doll
uv sync
uv run pytest
```

3. Crea un floppy: `~/.doll/floppies/notas/floppy.toml` con la carpeta de tus notas (todas las claves en [configuración](https://remih06.github.io/Doll/#configuracion)):

```toml
fuente = "/ruta/a/tus/notas"
mcp_excluir = []
```

4. Móntalo, indexa y busca:

```bash
uv run doll montar notas
uv run doll indexar
uv run doll buscar "escape de áncora"
```

`preguntar`, `acomodar` y la búsqueda por sentido necesitan el gateway de [Bakery](https://github.com/RemiH06/Bakery) (`BAKERS_URL` y `BAKERS_API_KEY`); `buscar` funciona sin él.

## Launch arguments

- `doll indexar [--sentido]`: sincroniza el índice con las notas; solo reprocesa las que cambiaron. Con `--sentido`, también embebe los fragmentos de terceros que no tienen vector (la primera vez tarda unos 0.4 s por fragmento en CPU).
- `doll buscar "consulta" [-k N] [--tipo T] [--dominio D] [--sentido]`: fragmentos con ruta y líneas. Con `--sentido`, busca por sentido y solo en notas de terceros.
- `doll preguntar "consulta" [-k N] [--tipo T] [--dominio D]`: respuesta con citas verificadas.
- `doll acomodar RUTA...`: propone dónde va cada nota; no escribe nada.
- `doll montar [NOMBRE]`: monta un floppy para la CLI, el MCP y el panel de Bakery; sin nombre, lista los floppies y marca el montado.
- `doll mcp`: servidor MCP por stdio, con las herramientas `buscar`, `buscar_inspiracion` y `preguntar_notas`. Cada llamada usa el floppy montado en ese momento. Cómo registrarlo en Claude Code: [MCP](https://remih06.github.io/Doll/#mcp).
- `doll evaluar [--motor fts|grep] [--generacion] [--set NOMBRE] [-k N]`: mide contra `eval/<set>.toml` del floppy (ver [evaluación](https://remih06.github.io/Doll/#evaluacion)).
- `--floppy NOMBRE`, antes del comando: usa ese floppy y no el montado, solo en ese comando.

```bash
uv run doll preguntar "¿Cuándo se inventó el escape de áncora?"
```

## Features

- Fragmentos por encabezado, con ruta, líneas y hash por nota, partidos por `doll-parser`, un filtro en Rust.
- Búsqueda FTS5 que ignora acentos, sin servicios externos, con tope de fragmentos por nota, a lo más 2 lugares para notas de terceros y expansión a las notas enlazadas con `[[wikilinks]]`.
- Búsqueda por sentido en las notas de terceros, con vectores de bge-m3 que calcula Bakery en CPU.
- Filtro por `tipo` y `dominio` del frontmatter, y alcance por carpeta según frases configurables.
- Citas comprobadas contra el texto recuperado; si ninguna sobrevive, o si la pregunta nombra algo que no se recuperó, responde "no encontrado".
- Texto de terceros marcado como no confiable en el prompt y en la salida.
- Un enlace a una nota excluida se tapa en el índice: no queda ni su nombre.
- `acomodar` propone clase y enlaces para notas de inspiración, y carpeta, `tipo`, `estado`, dominio, proyecto y enlaces para las demás. La propuesta la aplica una persona.
- Servidor MCP para consultar las notas desde Claude Code.
- Log local con tiempos y conteos, sin preguntas ni fragmentos.
- `buscar` sigue funcionando sin modelo, y `preguntar` lo dice y entrega los fragmentos.

## Limitaciones

Medido con un modelo local sobre un corpus real de 521 notas; detalle, sets y lo que se probó y se descartó en [evaluación](https://remih06.github.io/Doll/#evaluacion).

- `preguntar` citó todas sus notas en 19 de 22 preguntas de un set nuevo, y en los sets de ajuste baja a cerca del 75 %. Una cita verificada prueba que el texto existe, no que responda la pregunta.
- Rechazó las 11 preguntas sin respuesta de ese set, pero en otras pruebas limpias solo 5 de 7.
- `buscar` y `preguntar` buscan por palabras. La búsqueda por sentido (71 % de recall@5 contra 58 % de FTS5) solo cubre notas de terceros.
- Agregar notas puede bajar el recall de las que ya estaban: al crecer el corpus hay que volver a medir.
- `acomodar` acierta la carpeta en 87 % y el proyecto en 88 %, pero `tipo` en 73 %: es una sugerencia que hay que revisar. Ningún set es del todo ciego.

## Autoría

por RemLam ([@RemiH06](https://github.com/RemiH06))
