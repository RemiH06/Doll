//! Recibe por stdin un arreglo JSON con el texto de cada nota y devuelve, en el mismo orden,
//! sus fragmentos por encabezado, wikilinks y frontmatter. No lee archivos: las exclusiones
//! viven en un solo lugar, del lado de Python.

use pulldown_cmark::{Event, LinkType, Options, Parser, Tag, TagEnd};
use serde::Serialize;
use serde_json::Value;
use std::error::Error;
use std::io::{self, Read};

#[derive(Serialize, Debug, PartialEq)]
struct Fragmento {
    encabezado: String,
    linea_ini: usize, // 1-indexada, sobre el archivo original
    linea_fin: usize,
    texto: String,
}

#[derive(Serialize, Debug, PartialEq)]
struct Enlace {
    destino: String,
    crudo: String, // el `[[...]]` tal como está en la nota, para poder taparlo
}

#[derive(Serialize, Debug, Default)]
struct Nota {
    fragmentos: Vec<Fragmento>,
    enlaces: Vec<Enlace>,
    frontmatter: Option<Value>,
    frontmatter_invalido: bool,
}

struct Titulo {
    linea: usize, // 0-indexada
    nivel: usize,
    texto: String,
}

fn opciones() -> Options {
    Options::ENABLE_WIKILINKS | Options::ENABLE_YAML_STYLE_METADATA_BLOCKS | Options::ENABLE_TABLES
}

fn inicios_de_linea(texto: &str) -> Vec<usize> {
    let saltos = texto.match_indices('\n').map(|(i, _)| i + 1);
    std::iter::once(0).chain(saltos).collect()
}

/// `# Título ##` -> `Título`. En un encabezado setext la primera línea ya es el título.
fn titulo_limpio(origen: &str) -> String {
    let linea = origen.lines().next().unwrap_or("").trim();
    let sin_marca = linea.trim_start_matches('#').trim();
    sin_marca.trim_end_matches('#').trim_end().to_string()
}

fn enlace(tipo: LinkType, destino: &str, crudo: &str) -> Option<Enlace> {
    if !matches!(tipo, LinkType::WikiLink { .. }) {
        return None;
    }
    // En una tabla el alias va como `[[Nota\|alias]]` y pulldown deja la diagonal en el destino.
    let sin_ancla = destino.split('#').next().unwrap_or("").trim().trim_end_matches('\\');
    (!sin_ancla.is_empty()).then(|| Enlace { destino: sin_ancla.to_string(), crudo: crudo.to_string() })
}

fn partir(texto: &str, inicio: usize, titulos: &[Titulo]) -> Vec<Fragmento> {
    let lineas: Vec<&str> = texto.lines().collect();
    let mut fragmentos = Vec::new();
    let mut agregar = |ruta: &[(usize, &str)], primera: usize, fin: usize| {
        let contenido = lineas[primera..fin].join("\n");
        let contenido = contenido.trim();
        if !contenido.is_empty() {
            let nombres: Vec<&str> = ruta.iter().map(|(_, t)| *t).collect();
            fragmentos.push(Fragmento {
                encabezado: nombres.join(" > "),
                linea_ini: primera + 1,
                linea_fin: fin,
                texto: contenido.to_string(),
            });
        }
    };

    let mut ruta: Vec<(usize, &str)> = Vec::new();
    let mut primera = inicio;
    for titulo in titulos {
        agregar(&ruta, primera, titulo.linea);
        primera = titulo.linea;
        ruta.retain(|(nivel, _)| *nivel < titulo.nivel);
        ruta.push((titulo.nivel, &titulo.texto));
    }
    agregar(&ruta, primera, lineas.len());
    fragmentos
}

fn analizar(texto: &str) -> Nota {
    let inicios = inicios_de_linea(texto);
    let linea_de = |offset: usize| inicios.partition_point(|&i| i <= offset) - 1;

    let mut nota = Nota::default();
    let mut titulos = Vec::new();
    let mut inicio = 0;
    let mut profundidad = 0; // un `#` dentro de una cita o lista no parte la nota
    let mut en_metadatos = false;

    for (evento, rango) in Parser::new_ext(texto, opciones()).into_offset_iter() {
        match evento {
            Event::Start(Tag::BlockQuote(_) | Tag::List(_)) => profundidad += 1,
            Event::End(TagEnd::BlockQuote(_) | TagEnd::List(_)) => profundidad -= 1,
            Event::Start(Tag::MetadataBlock(_)) => {
                en_metadatos = true;
                inicio = linea_de(rango.end - 1) + 1;
            }
            Event::End(TagEnd::MetadataBlock(_)) => en_metadatos = false,
            Event::Text(yaml) if en_metadatos => match serde_saphyr::from_str::<Value>(&yaml) {
                Ok(valor) => nota.frontmatter = Some(valor),
                Err(_) => nota.frontmatter_invalido = true,
            },
            Event::Start(Tag::Heading { level, .. }) if profundidad == 0 => {
                let texto_titulo = titulo_limpio(&texto[rango.clone()]);
                if !texto_titulo.is_empty() {
                    titulos.push(Titulo { linea: linea_de(rango.start), nivel: level as usize, texto: texto_titulo });
                }
            }
            Event::Start(Tag::Link { link_type, dest_url, .. } | Tag::Image { link_type, dest_url, .. }) => {
                nota.enlaces.extend(enlace(link_type, &dest_url, &texto[rango.clone()]));
            }
            _ => {}
        }
    }
    nota.fragmentos = partir(texto, inicio, &titulos);
    nota
}

fn main() -> Result<(), Box<dyn Error>> {
    let mut entrada = String::new();
    io::stdin().read_to_string(&mut entrada)?;
    let textos: Vec<String> = serde_json::from_str(&entrada)?;
    let notas: Vec<Nota> = textos.iter().map(|t| analizar(t)).collect();
    serde_json::to_writer(io::stdout().lock(), &notas)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn encabezados(texto: &str) -> Vec<String> {
        analizar(texto).fragmentos.into_iter().map(|f| f.encabezado).collect()
    }

    fn destinos(texto: &str) -> Vec<String> {
        analizar(texto).enlaces.into_iter().map(|e| e.destino).collect()
    }

    #[test]
    fn frontmatter_sin_cerrar_es_texto() {
        let nota = analizar("---\ntipo: x\n\n# Uno\n");
        assert!(nota.frontmatter.is_none());
        assert_eq!(nota.fragmentos[0].linea_ini, 1);
    }

    #[test]
    fn frontmatter_invalido_no_rompe_la_nota() {
        let nota = analizar("---\na: [b\n---\n# Uno\n");
        assert!(nota.frontmatter_invalido);
        assert_eq!(nota.fragmentos.len(), 1);
    }

    #[test]
    fn dominio_en_lista() {
        let nota = analizar("---\ntipo: nota\ndominio: [a, b]\n---\n");
        assert_eq!(nota.frontmatter.unwrap()["dominio"], serde_json::json!(["a", "b"]));
    }

    #[test]
    fn cita_y_lista_no_parten() {
        assert_eq!(encabezados("# Uno\n\n> # cita\n\n- # lista\n"), ["Uno"]);
    }

    #[test]
    fn cierre_de_encabezado_con_gatos() {
        assert_eq!(encabezados("## Uno ##\ntexto\n"), ["Uno"]);
    }

    #[test]
    fn enlaces_con_ancla_alias_y_embebido() {
        assert_eq!(destinos("[[A#b|c]] ![[D]] [[#solo ancla]] `[[codigo]]`\n"), ["A", "D"]);
    }

    #[test]
    fn enlace_en_tabla_con_alias_escapado() {
        assert_eq!(destinos("| a |\n|---|\n| [[Nota\\|alias]] |\n"), ["Nota"]);
    }

    #[test]
    fn crudo_es_el_texto_de_la_nota() {
        let nota = analizar("ver [[A|alias]] y ![[B]]\n");
        let crudos: Vec<&str> = nota.enlaces.iter().map(|e| e.crudo.as_str()).collect();
        assert_eq!(crudos, ["[[A|alias]]", "![[B]]"]);
    }
}
