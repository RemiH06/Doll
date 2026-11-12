# Configuración

## Corpus

Doll lee `~/.doll/corpus.toml`; con `DOLL_HOME` se cambia la carpeta. Cada tabla es un corpus, y las rutas son relativas a `ruta`:

```toml
[boveda]
ruta = "/ruta/a/tus/notas"
excluir = ["privado/**"]
terceros = ["recortes/**"]
mcp_excluir = ["borradores/**"]

[boveda.alcances]
'notas? de recortes' = "recortes/**"
```

| Clave | Para qué |
|---|---|
| `ruta` | Carpeta con las notas. |
| `excluir` | Notas que no entran al índice. `gente/**` y `life/**` quedan fuera siempre. Un enlace a una nota excluida se tapa también en el texto. |
| `terceros` | Notas escritas por otros (recortes, reels). Su texto va marcado como no confiable, y son las únicas que entran a la búsqueda por sentido. |
| `mcp_excluir` | Notas que el MCP no entrega, aunque la CLI sí. Es obligatoria para arrancar el servidor: `[]` si no quieres ocultar nada. |
| `alcances` | Opcional. Si la pregunta coincide con la regex, `preguntar` busca solo en esa carpeta y la frase no cuenta como tema. |

`--corpus NOMBRE`, antes del comando, elige el corpus; por defecto, `boveda`. Después de un cambio grande en las notas, revisa las exclusiones antes de `doll indexar`.

## Bakery

`preguntar`, `acomodar` y la búsqueda por sentido usan el paquete [`bakers`](https://github.com/RemiH06/Bakery) y el gateway de Bakery:

```bash
export BAKERS_URL=http://127.0.0.1:PUERTO
export BAKERS_API_KEY=...
```

`buscar` funciona sin ellas. Sin gateway, `buscar --sentido` usa FTS5 y lo avisa, y `preguntar` entrega los fragmentos sin respuesta.

## MCP

Para usar Doll desde Claude Code:

```bash
claude mcp add --scope user doll -- uv run --no-sync --project /ruta/a/Doll doll mcp
```

Herramientas: `buscar`, `buscar_inspiracion` (por sentido, en notas de terceros) y `preguntar_notas`.

`--no-sync` evita que `uv` intente reinstalar `doll.exe` al arrancar: en Windows eso falla si otra sesión tiene el servidor abierto. Después de un `uv sync`, reinicia las sesiones que usan el MCP.

Las skills de ejemplo de [`skills/`](../skills/) le dicen a un agente cuándo usar cada herramienta: `doll-notas` para buscar y `doll-acomodar` para proponer dónde va una nota. En Claude Code se instalan copiando cada carpeta a `~/.claude/skills/`.

## Instalar sin Rust

`uv sync` compila `doll-parser` con `cargo`. En una máquina sin Rust, compílalo donde sí lo haya y lleva el wheel:

```bash
uv build --wheel parser -o dist                       # en la máquina con Rust
uv venv                                               # en la otra, dentro del clon
uv pip install dist/doll_parser-*.whl
uv pip install -e /ruta/a/Bakery/bakers               # o el paquete bakers desde git
uv pip install -e . --no-sources
```

Ahí no corras `uv sync` ni `uv pip install` sin `--no-sources`: los dos leen `[tool.uv.sources]`, compilan `doll-parser` y cambian `bakers` por el de git. Para actualizar basta `git pull` mientras no cambie `parser/`, porque `doll` queda editable; `uv pip install -e . --no-sources` refresca la versión instalada. Si cambia `parser/`, vuelve a compilar e instala el wheel con `--reinstall`.
