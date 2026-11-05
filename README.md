![Made with Python](https://forthebadge.com/images/badges/made-with-python.svg)
![SQLite](https://img.shields.io/badge/-SQLite-003B57?style=for-the-badge&logo=sqlite&logoColor=white)

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

1. Instala [uv](https://docs.astral.sh/uv/).
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
```

`gente/**` y `life/**` quedan fuera siempre. `preguntar` usa el paquete [`bakers`](https://github.com/RemiH06/Bakery) y necesita `BAKERS_URL` y `BAKERS_API_KEY`; `buscar` funciona sin ellas.

## Launch arguments

- `doll indexar`: sincroniza el índice con las notas; solo reprocesa las que cambiaron.
- `doll buscar "consulta" [-k N]`: fragmentos con ruta y líneas.
- `doll preguntar "consulta" [-k N]`: respuesta con citas verificadas.
- `doll evaluar [--motor fts|grep] [--generacion] [-k N]`: mide contra `~/.doll/eval/preguntas.toml`.
- `--corpus NOMBRE`, antes del comando: elige el corpus; por defecto, `boveda`.

```bash
uv run doll preguntar "¿Cuándo se inventó el escape de áncora?"
```

## Features

- Fragmentos por encabezado, con ruta, líneas y hash por nota.
- Búsqueda FTS5 que ignora acentos, sin servicios externos.
- Citas comprobadas contra el texto recuperado; si ninguna sobrevive, responde "no encontrado".
- Texto de terceros marcado como no confiable en el prompt y en la salida.
- `buscar` sigue funcionando sin modelo, y `preguntar` lo dice y entrega los fragmentos.
- Log local con tiempos y conteos, sin preguntas ni fragmentos.

## Future Features

- Filtro por taxonomía y expansión por `[[wikilinks]]`.
- Servidor MCP.
- Acomodar notas nuevas con propuestas de carpeta, etiquetas y enlaces.

## Autoría

por RemLam ([@RemiH06](https://github.com/RemiH06))
