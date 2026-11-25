# Auditoría del prototipo de abril de 2026 y lo que cambió

> **Contexto.** ley-energia-mx nació en abril de 2026 como prototipo privado. Antes de publicarlo
> se auditó ese código (rutas como `main.py:1635` se refieren al prototipo, que se conserva en un
> repositorio privado) y se reconstruyó desde cero. La sección final, "Cómo se atendió y cifras del
> después", resume qué pasó con cada hallazgo. Se publica tal cual porque explica las decisiones de
> diseño de la versión 1.0.

Este documento describe el estado del código de abril de 2026 de un RAG sobre regulación energética mexicana, que se va a reemplazar por una versión nueva. El sistema tiene estas piezas: un servidor FastAPI (`server.py`), una CLI con click (`main.py`), búsqueda híbrida con RRF sobre Postgres y pgvector (`db/queries.py`), scrapers del DOF, de CENAGAS y de la CNE (`scrapers/`), extracción de PDF y un chunker que sigue la jerarquía legal (`processors/`), una web de un solo archivo (`web/index.html`), 30 scripts de indexación de un solo uso (`scripts/`) y un golden set (`tests/`). La revisión se hizo el 25 de noviembre de 2026 sobre una copia de sólo lectura y no modificó ningún archivo. No se ejecutó nada que hiciera peticiones de red. La base de datos no está en el repositorio, así que no se pudo consultar. Sí se corrieron tres pruebas locales deterministas, sin red: el chunker, la limpieza de texto de PDF y las regex de detección de artículos. Sus resultados se citan en los hallazgos correspondientes. Las cifras salen de `wc` y `grep` sobre la copia. Todas las rutas son relativas a la raíz del proyecto. Siguiendo la convención del proyecto, todo dato sin fuente directa lleva [ESTIMADO], [SUPUESTO] o [BRECHA DE DATO].

> Esta auditoría es técnica. No constituye opinión legal ni asesoría fiscal. Las observaciones sobre equivalencias normativas, vigencia o transitorios deben validarse con un especialista o con la autoridad competente.

**Severidad.** P0: impide publicar o desplegar el proyecto tal cual (riesgo de seguridad o de costo para terceros, o resultados que nadie más puede reproducir). P1: importante, hay que atenderlo antes de crecer. P2: deseable.

**Semáforo.** ROJO: la dimensión tiene al menos un P0. AMARILLO: tiene P1 y ningún P0. VERDE: sólo tiene P2.

## Tabla resumen

| Dimensión | Semáforo | P0 | P1 | P2 | Motivo |
|---|---|---|---|---|---|
| 1. Arquitectura y calidad | AMARILLO | 0 | 3 | 5 | Funciona, pero duplica lógica entre CLI y servidor, bloquea el event loop y el empaque está roto. |
| 2. Seguridad | ROJO | 1 | 4 | 3 | El servidor escucha en 0.0.0.0 sin autenticación, con endpoints que gastan créditos y lanzan scraping. |
| 3. IA y RAG | AMARILLO | 0 | 6 | 7 | La recuperación está bien diseñada, pero las respuestas no tienen citas verificables y el modelo no ve la vigencia. Es la dimensión con más P1. |
| 4. Datos | ROJO | 1 | 4 | 3 | El corpus no se puede reproducir desde el repositorio. La ingesta tiene errores que alteran texto y fechas. |
| 5. Front y accesibilidad | AMARILLO | 0 | 2 | 1 | Hay filtros que no coinciden con los datos y fallas de accesibilidad (etiquetas, foco, contraste). |
| 6. Higiene | AMARILLO | 0 | 3 | 3 | Falta README, LICENSE, CI y pruebas unitarias. CLAUDE.md describe un estado que no viaja con el repositorio. |
| **Total** | | **2** | **22** | **22** | |

Las fallas de seguridad del front (XSS y terceros sin versión fija) se cuentan sólo en Seguridad (S-03 y S-04).

## 1. Arquitectura y calidad

#### A-01 · P1 · Lógica duplicada entre CLI y servidor, e ingesta repetida
- **Evidencia:** búsqueda multiconsulta en `main.py:398-425` y `server.py:134-151`. Formateo de contexto en `main.py:428-451` (1800 caracteres) y `server.py:64-80` (1500). Embedding de consulta en `main.py:88-95` y `server.py:57-61`. Prompts en tres pares casi iguales: `main.py:365-369` y `server.py:301-307`, `main.py:752-759` y `server.py:370-376`, `main.py:845-849` y `server.py:451-455`. El pipeline chunk, embedding, inserción, transitorios y marcado aparece en `main.py:280-303`, `main.py:1370-1392` y `main.py:1557-1577`, y además en 22 de los 30 scripts (todos llaman a `chunkear_documento` y a `insertar_chunks_batch`).
- **Qué pasa:** las copias ya divergieron. El servidor fija `voyage-law-2` (`server.py:60`) e ignora `VOYAGE_MODEL`, que la indexación sí respeta (`main.py:64`). Si alguien cambia esa variable, consulta e índice quedan en espacios vectoriales distintos sin ningún aviso. Además, la misma pregunta recibe prompt, truncado y modelo distintos según se haga por la CLI o por la web.
- **Arreglo:** crear un módulo de servicio único (recuperar, armar contexto, generar) que usen la CLI y la API, y un solo comando de ingesta que lean scripts y monitores.

#### A-02 · P1 · E/S síncrona dentro de endpoints `async`
- **Evidencia:** `_stream_claude` usa el cliente síncrono `anthropic.Anthropic` e itera `stream.text_stream` dentro de un generador `async` (`server.py:154-167`). `/api/stats`, `/api/documentos`, `/api/linaje` y `/api/dof/novedades` son `async def` con psycopg2 síncrono (`server.py:187-249`, `520-577`, `580-620`, `486-517`). `_construir_fuentes` consulta la BD de forma síncrona dentro de los generadores (`server.py:294`, `363`, `443`). Además, `asyncio.get_event_loop()` dentro de corrutinas (`server.py:270`, `283`, `354`, `435`) es un patrón obsoleto.
- **Qué pasa:** mientras Claude genera una respuesta (hasta 4000 tokens en due diligence), el event loop queda bloqueado y todas las demás peticiones esperan.
- **Arreglo:** usar `AsyncAnthropic`, declarar como `def` los endpoints con E/S síncrona o envolverla en `asyncio.to_thread`, y usar psycopg 3 asíncrono con pool.

#### A-03 · P1 · Empaque roto en `pyproject.toml`
- **Evidencia:** el código importa paquetes que no están declarados: `fastapi` (`server.py:29-31`), `uvicorn` (`main.py:1648`), `pyyaml` (`tests/run_golden.py:32`) y `playwright` (`scrapers/cne_drive.py:117`). En sentido contrario, `pgvector` y `Pillow` están declarados (`pyproject.toml:21`, `24`) pero ningún módulo los importa directamente. El script `ley-energia = "main:cli"` (`pyproject.toml:45-46`) apunta a `main.py`, pero el wheel sólo empaqueta `scrapers`, `processors` y `db` (`pyproject.toml:48-49`). No hay lockfile y todas las dependencias usan sólo cotas `>=`. Se pide `httpx[http2]` pero el cliente usa `http2=False` (`scrapers/dof_scraper.py:247`).
- **Qué pasa:** una instalación limpia no levanta el servidor ni corre el golden set, y en una instalación no editable el comando `ley-energia` falla al importar `main`.
- **Arreglo:** declarar todas las dependencias, empaquetar el código como paquete (`src/`) y fijar versiones con un lockfile.

#### A-04 · P2 · SQL: no hay inyección, pero tampoco pool y hay índices que no se usan
- **Evidencia:** cada llamada abre una conexión nueva (`db/queries.py:33-45`, `48-64`). `buscar_hibrido` abre entre 3 y 6 conexiones por consulta (`db/queries.py:655`, `670`, `671`, `682`, `691`, `697`), así que una due diligence de 5 consultas abre entre 15 y 30 conexiones más 1 (conteo por lectura de código). El FTS consulta `to_tsvector('spanish', unaccent(c.contenido))` (`db/queries.py:384`, `425`), pero el índice existe sobre `unaccent_immutable(contenido)` (`db/schema.sql:212-213`). Como las expresiones no coinciden, el índice no se usa y el `tsvector` se calcula fila por fila dos veces por consulta. La regex `~*` sobre `contenido` (`db/queries.py:491`) tampoco tiene índice.
- **Qué pasa:** con los 11,112 fragmentos que reporta `CLAUDE.md:37` el costo es tolerable [ESTIMADO], pero crece de forma lineal.
- **Arreglo:** usar un pool, la misma expresión en la consulta que en el índice (o una columna `tsvector` generada) y un índice trigram si se conserva la regex.

#### A-05 · P2 · Archivos grandes y responsabilidades mezcladas
- **Evidencia:** `main.py` tiene 1,669 líneas y mezcla CLI, pipeline, prompts, reportes en markdown y arranque del servidor. 22 scripts importan de `main.py` (la CLI hace de librería) y 29 manipulan `sys.path`. `web/index.html` tiene 4,135 líneas.
- **Arreglo:** separar en módulos (ingesta, recuperación, generación, reportes, CLI y API).

#### A-06 · P2 · Manejo de errores amplio y con fugas
- **Evidencia:** hay 53 `except Exception` en el código Python. El servidor devuelve `str(e)` al cliente (`server.py:249`, `323`, `401`, `481`, `517`, `577`, `620`, `640`). `_claude` agrega su propio reintento (`main.py:454-484`) encima del del SDK.
- **Qué pasa:** se exponen mensajes internos de la BD. Ante un 429, una llamada puede intentarse hasta 12 veces y esperar más de 105 s [ESTIMADO, con los 2 reintentos por omisión del SDK].
- **Arreglo:** registrar el error en el servidor y devolver un mensaje genérico con un id de correlación, y confiar en los reintentos del SDK.

#### A-07 · P2 · Tipado presente, validación ausente
- **Evidencia:** hay anotaciones de tipo en casi todo el código y mypy está configurado (`pyproject.toml:58-60`), pero nada lo ejecuta. Los cuerpos de las peticiones se leen con `await request.json()` sin modelos Pydantic (`server.py:255`, `331`, `409`). El texto del DOF viaja como atributo dinámico de un dataclass (`scrapers/dof_scraper.py:739`, `main.py:126`).
- **Arreglo:** definir modelos Pydantic de entrada y salida y correr mypy en CI.

#### A-08 · P2 · Código muerto y rutas cableadas
- **Evidencia:** sin uso: `docs_antes` (`main.py:1008`), `_descargar_uno` (`main.py:1512-1513`), el parámetro `overlap_chars` (`processors/chunker.py:580`) y los imports `re`, `Any` y `StaticFiles` (`server.py:20`, `24`, `31`). `procesar_directorio(actualizar_bd=True)` no actualiza la BD (`processors/pdf_extractor.py:426-455`). `/api/dof/novedades` no tiene consumidor en la web. El docstring de uso (`main.py:11-16`) documenta banderas que no existen: el comando real es `run --solo-scrape`. `.venv/bin/python` está cableado (`server.py:648`, `scripts/monitor_dof.py:29`) en lugar de `sys.executable`. `logs/` se resuelve contra el directorio de trabajo en `main.py:1063` y contra el archivo en `server.py:627`.
- **Arreglo:** borrar lo que no se usa, usar `sys.executable` y centralizar la configuración de rutas.

## 2. Seguridad

#### S-01 · P0 · Servidor expuesto en la red sin autenticación, con endpoints que gastan y lanzan procesos
- **Evidencia:** `serve` escucha en `0.0.0.0` por omisión (`main.py:1635`). Ninguna de las 10 rutas tiene autenticación ni límite de uso (`server.py:179-673`). `POST /api/monitor/run` lanza un subproceso que hace scraping, extracción, embeddings y una llamada a Claude (`server.py:643-673`, `main.py:1011-1113`). `/api/due-diligence` hace 5 embeddings y una generación de hasta 4000 tokens por petición (`server.py:345-351`, `396`).
- **Qué pasa:** cualquier equipo de la misma red, o de internet si el puerto queda expuesto, puede gastar los créditos de Voyage y de Anthropic y disparar scraping contra sitios del gobierno a nombre del operador.
- **Arreglo:** escuchar en `127.0.0.1` por omisión, exigir un token, limitar la frecuencia por cliente, y sacar `monitor/run` de la API pública (o protegerlo y encolarlo).

#### S-02 · P1 · Peticiones entre sitios (CSRF) y DNS rebinding
- **Evidencia:** el servidor no configura CORS (no hay `CORSMiddleware`), lo cual es correcto. Sin embargo, `await request.json()` parsea cualquier cuerpo sin exigir `Content-Type: application/json` (`server.py:255`, `331`, `409`), y `/api/monitor/run` no necesita cuerpo. Tampoco se valida el encabezado `Host` (no hay `TrustedHostMiddleware`).
- **Qué pasa:** una página externa puede mandar un POST "simple", sin preflight, al servidor local y provocar el gasto o el scraping. La única barrera es que el navegador bloquee el acceso de sitios públicos a la red local. Sin validar `Host`, un ataque de DNS rebinding podría además leer las respuestas.
- **Arreglo:** exigir JSON y un token por petición, y validar `Host`.

#### S-03 · P1 · XSS por markdown sin sanitizar y datos interpolados en `innerHTML`
- **Evidencia:** `marked.parse` se inserta con `innerHTML` (`web/index.html:2489-2490`, `2735`, `2813`, `2909`, `3013`, `3170`, `3498`, `3567`), y marked no sanitiza el HTML. Los títulos y URLs que vienen de la BD se interpolan sin escapar (`web/index.html:2573`, `2580`, `2742`, `2831`).
- **Qué pasa:** el HTML que llegue en un título raspado, en un log o en la salida del modelo (que puede repetir texto de los documentos) se ejecuta en la página, y desde ahí tiene acceso a toda la API local.
- **Arreglo:** pasar la salida por un sanitizador (por ejemplo DOMPurify), escapar todo lo que se interpola y aceptar sólo `http(s)` en los `href`.

#### S-04 · P1 · Scripts de terceros sin versión fija ni SRI
- **Evidencia:** la página carga Tailwind Play CDN (`web/index.html:7`), `marked` sin versión desde jsDelivr (`web/index.html:8`, que resuelve a la última publicada) y `html2pdf.js` 0.10.1 (`web/index.html:9`). Ningún recurso tiene atributo `integrity` (0 en todo el archivo). Además, Google Fonts (`web/index.html:11`) y una imagen de Unsplash de 1920 px (`web/index.html:811`) envían la IP y el Referer de cada visitante a terceros.
- **Qué pasa:** cualquier cambio o compromiso de esos CDN ejecuta código ajeno con acceso a la API local. Una versión mayor nueva de `marked` puede romper la página sin que nadie haya tocado el repositorio.
- **Arreglo:** empaquetar las dependencias localmente o fijarlas con versión exacta e `integrity`, y alojar fuentes e imágenes en el propio proyecto.

#### S-05 · P1 · Verificación TLS desactivada al descargar el corpus
- **Evidencia:** en `scrapers/cenagas_scraper.py:191-196` el `verify=False` está aislado a un solo host y documentado (`scrapers/cenagas_scraper.py:14-16`), lo cual está bien razonado. Pero ese cliente también sigue redirecciones (`follow_redirects=True`, línea 194), así que si el host redirige a otro, esa conexión tampoco se verifica. Fuera del scraper hay 10 scripts con `verify=False`, entre ellos dos que descargan del DOF (`scripts/re_extraer_texto_dof.py:66`, `scripts/indexar_media_prioridad.py:240`), aunque el scraper principal ya resuelve el DOF con `truststore` (`scrapers/dof_scraper.py:45-49`).
- **Qué pasa:** el texto descargado se convierte en las respuestas legales, y su integridad depende de una red que no se verifica.
- **Arreglo:** usar un bundle con la CA intermedia que falta (`verify=<ruta>`), no seguir redirecciones fuera del host y guardar el hash de cada archivo.

#### S-06 · P2 · Inyección de instrucciones mediante el texto de los documentos
- **Evidencia:** los fragmentos se pegan en el mensaje de usuario sin delimitadores y sin ninguna instrucción de tratarlos como datos (`server.py:308-313`, `377-394`, `456-474`, `main.py:378-382`).
- **Qué pasa:** el riesgo es bajo porque las fuentes son oficiales. Aun así, junto con S-05 (texto sin verificar) y S-03 (salida renderizada como HTML) forma una cadena de ataque posible.
- **Arreglo:** envolver cada documento en etiquetas XML con su id, indicar en el sistema que el contenido de esas etiquetas son datos y no instrucciones, y sanitizar la salida.

#### S-07 · P2 · Entradas sin límites
- **Evidencia:** no hay longitud máxima para `pregunta`, `proyecto` ni `tema`. En `/api/documentos`, `limit` no tiene tope y `page` no se valida (`server.py:526-527`): un `page` menor que 1 genera un `OFFSET` negativo, que termina en un 500 con el error de la BD. En `/api/linaje`, `max_profundidad` tampoco tiene tope (`server.py:581`) y alimenta un CTE recursivo con `UNION ALL` sin detección de ciclos (`db/queries.py:980-1024`).
- **Arreglo:** validar con Pydantic (longitudes, rangos) y limitar la profundidad del linaje.

#### S-08 · P2 · Manejo de llaves correcto y BD con privilegios de más
- **Evidencia:** lo que está bien: las llaves se leen sólo de variables de entorno, `.env` está ignorado (`.gitignore:2`) y `.env.example` sólo trae marcadores. Una búsqueda de patrones de llaves en todo el repositorio no encontró secretos. Lo que falta: por omisión la aplicación se conecta como `postgres` (`db/queries.py:43`, `.env.example:16-23`).
- **Arreglo:** usar un rol de mínimo privilegio en tiempo de ejecución y otro distinto para las migraciones.

## 3. IA y RAG

#### IA-01 · P1 · Las respuestas no citan fuentes de forma verificable
- **Evidencia:** el prompt pide "cita el artículo y la ley" (`server.py:305`), pero el contexto no incluye identificadores de fragmento (`server.py:64-80`) y la salida es markdown libre. La lista de "fuentes" que ve el usuario es el conjunto recuperado completo, hasta 20 fragmentos (`server.py:283-296`), no lo que el modelo citó. El semáforo dice "La respuesta cita N documento(s) abrogado(s)" (`web/index.html:2597`), pero en realidad cuenta documentos recuperados. Nada comprueba que un artículo citado esté en el contexto.
- **Qué pasa:** un abogado no puede saber qué afirmación viene de qué fragmento, y una cita inventada luce igual que una real.
- **Arreglo:** usar citas nativas (bloques `document` con `citations` activado) o salida estructurada con `chunk_id` por afirmación, validar las citas contra el contexto y mostrar sólo las fuentes citadas.

#### IA-02 · P1 · El modelo no recibe la vigencia de cada fragmento
- **Evidencia:** el encabezado de cada fragmento lleva título, emisor, tipo, fecha y referencia (`server.py:68-75`, `main.py:439-446`), pero no `vigente`, `fecha_abrogacion`, `nota_vigencia` ni `es_version_historica`. Aun así, el prompt de régimen temporal le pide al modelo "si un documento fue abrogado antes de la fecha, no lo apliques" (`main.py:942`).
- **Qué pasa:** cuando entra un documento abrogado (ver IA-03) o uno con salvedad, por ejemplo los manuales de subastas que `CLAUDE.md:57-58` describe como inoperantes, el modelo lo trata como plenamente vigente. La web pinta el semáforo en rojo, pero la CLI no muestra nada.
- **Arreglo:** agregar una línea `VIGENCIA:` al encabezado de cada fragmento y una regla explícita en el prompt de sistema.

#### IA-03 · P1 · El filtro "sólo vigentes" se salta en la señal por ley nombrada
- **Evidencia:** los `doc_ids` de la ley detectada se resuelven sin ningún filtro de vigencia (`db/queries.py:652-666`), y la minibúsqueda usa `filtros_ley = {"doc_ids": ...}` sin `vigente` (`db/queries.py:680-685`). `/api/chat` activa "sólo vigentes" por omisión (`server.py:278-279`).
- **Qué pasa:** una consulta que nombre "Ley de Hidrocarburos" o "LIE" mete fragmentos de leyes abrogadas (`CLAUDE.md:76-77`). El aporte de esa señal para el primer fragmento es 0.20/20 = 0.01, más alto que el aporte máximo de cualquier otra señal individual (alrededor de 0.0075) [ESTIMADO, calculado con los pesos del código].
- **Arreglo:** pasar los mismos filtros de vigencia y fecha a la resolución y a la minibúsqueda de la ley.

#### IA-04 · P1 · La vigencia temporal se maneja a nivel documento, sobre una sola instantánea de texto
- **Evidencia:** el filtro es `fecha_pub <= ref AND (vigente OR fecha_abrogacion >= ref)` (`db/queries.py:296`, `398`, `504`, `588`). Ignora `fecha_vigor` (`db/schema.sql:44`) y deja fuera a los documentos sin `fecha_pub` (31 según `CLAUDE.md:83`). El texto guardado es a veces la publicación original del DOF y a veces el texto consolidado de la Cámara de Diputados al día de la descarga, con `fecha_pub` de la publicación original y una URL que siempre sirve la última versión (`scripts/indexar_reforma_2025.py:70-87`). No se registra la fecha de corte del consolidado.
- **Qué pasa:** para instrumentos reformados, "marco al {fecha}" (`main.py:877-959`; la vista de comparación en `web/index.html:3536-3560`) puede responder con texto posterior o anterior a esa fecha. Aun así, el prompt le asegura al modelo que todos los documentos "estaban vigentes en esa fecha" (`main.py:940`).
- **Arreglo:** guardar versiones por documento con `vigente_desde` y `vigente_hasta`, la fecha de corte de cada consolidado y una advertencia visible cuando la vigencia se resuelve sólo a nivel documento.

#### IA-05 · P1 · El chunker pierde transitorios y artículos cortos
- **Evidencia:** el patrón `TRANSITORIO` (`processors/chunker.py:68-71`) exige una palabra antes, así que no reconoce el encabezado aislado "TRANSITORIOS", que es la forma habitual. Prueba local: con "TRANSITORIOS" seguido de "PRIMERO.-" y "SEGUNDO.-", los transitorios quedaron pegados al fragmento del último artículo. Con "ARTÍCULOS TRANSITORIOS" se genera un solo fragmento para todos. `processors/transitorios_review.py:38-40` sí reconoce ambas formas, así que los dos módulos se contradicen. Los artículos de menos de 50 caracteres se descartan en silencio (`processors/chunker.py:298-303`), contra lo que promete el docstring (`processors/chunker.py:11`). Prueba local: "Artículo 2.- Esta Ley es de orden público." y "Artículo 3.- Se deroga." no generaron fragmento. Además, `CAPITULO` y `SECCION` usan IGNORECASE (`processors/chunker.py:50-57`) y pueden tomar como encabezado una línea del cuerpo que empiece con "capítulo" o "sección". Por último, `articulo` guarda la primera línea completa del artículo (`processors/chunker.py:305`), que luego se repite en el encabezado del embedding (`processors/chunker.py:117-128`).
- **Qué pasa:** se pierde justo la información de entrada en vigor y de derogación, y una búsqueda por el último artículo de una ley devuelve sus transitorios.
- **Arreglo:** aceptar el encabezado aislado, generar un fragmento por transitorio, conservar los artículos cortos y agregar pruebas unitarias con textos reales.

#### IA-06 · P1 · Evaluación mínima y dependiente de la BD local
- **Evidencia:** el golden set tiene 9 casos, todos de recuperación (`tests/golden_queries.yaml`), con `doc_ids` de la BD local (224, 305, 175, 58, 308, 225, 3, 283). Para correr necesita la BD viva y la API de Voyage (`tests/run_golden.py:36-56`). No evalúa la respuesta generada (fidelidad, citas), no usa el filtro por omisión de la web (`vigente=True`) y no cubre el caso del artículo 8 contra el 80 (pendiente reconocido en `CLAUDE.md:237`) ni los transitorios.
- **Qué pasa:** nadie fuera del equipo original puede correrla, y los errores de IA-05 o de D-04 no los detecta ninguna prueba.
- **Arreglo:** escribir pruebas unitarias sin red (chunker, regex, limpieza), un corpus de prueba pequeño y versionado, y una evaluación de generación (citas correctas, abstención cuando falta información).

#### IA-07 · P2 · Modelos distintos para los mismos prompts, cableados en el código
- **Evidencia:** la web usa `claude-opus-4-6` (`server.py:159`) y la CLI usa `claude-sonnet-4-6` (`main.py:372`, `469`) para los mismos prompts. `CLAUDE.md:32` documenta sólo Sonnet. Ninguno de los dos se configura por variable de entorno.
- **Qué pasa:** la misma pregunta tiene respuesta, costo y latencia distintos según la superficie. Los dos ids son válidos, pero a noviembre de 2026 son de la generación anterior, según la tabla de modelos de la documentación de la API consultada en esta auditoría. Al migrar hay un detalle: los modelos con razonamiento siempre activo devuelven primero un bloque `thinking`, así que `msg.content[0].text` (`main.py:388`, `474`) dejaría de funcionar.
- **Arreglo:** leer el modelo de la configuración, usar uno solo por tarea y tomar el texto filtrando los bloques por tipo.

#### IA-08 · P2 · Prompts dispersos, duplicados y sin delimitadores
- **Evidencia:** hay 8 prompts de sistema escritos en línea: `main.py:365`, `752`, `845`, `937` y `1096`, y `server.py:301`, `370` y `451`. Tres pares ya divergieron: el memo de due diligence de la CLI agrega "que el cliente debe investigar", y el chat de la web pide markdown mientras el de la CLI no. Cuatro prompts contienen el guion largo (`main.py:758`, `941`, `1110`, `server.py:375`).
- **Arreglo:** mover los prompts a archivos versionados con pruebas, y separar en etiquetas XML las instrucciones, los documentos y la pregunta.

#### IA-09 · P2 · Sin caché de prompt, sin salida estructurada y sin revisar `stop_reason`
- **Evidencia:** no hay `cache_control` en ninguna llamada. En el diseño actual el caché aportaría poco, porque el prompt de sistema es corto (menos de 100 tokens [ESTIMADO]) y el contexto cambia con cada consulta. Aportaría si se agrega un prefijo estable, como reglas de citación o un glosario. El memo de due diligence y el listado de DACGs tienen formato fijo, pero salen como markdown libre. Ninguna ruta revisa `stop_reason` (`server.py:318`, `396`, `476`; `main.py:793`).
- **Qué pasa:** un memo que llega al tope de 4000 tokens se corta sin aviso.
- **Arreglo:** usar salida estructurada para due diligence y DACG, avisar cuando `stop_reason` sea `max_tokens`, y agregar caché cuando exista un prefijo estable.

#### IA-10 · P2 · Contexto truncado y mal separado
- **Evidencia:** cada fragmento se corta a 1500 caracteres en la web (`server.py:64`, `77-78`) y a 1800 en la CLI (`main.py:428`), aunque los fragmentos llegan a 6000 (`processors/chunker.py:29`). La marca "[…fragmento truncado]" está bien puesta. En `consultar`, la expresión `"\n\n" + "─" * 60 + "\n\n".join(...)` (`main.py:360`) se evalúa por precedencia de operadores de forma que el separador sale una sola vez, y los fragmentos de fuentes distintas quedan separados sólo por una línea en blanco.
- **Qué pasa:** las fracciones finales de los artículos largos no llegan al modelo, que puede completarlas por su cuenta.
- **Arreglo:** recortar por fracción y no por caracteres, y usar delimitadores explícitos por documento.

#### IA-11 · P2 · La detección de artículos tiene huecos y los pesos no cuadran con su comentario
- **Evidencia:** la regex de la consulta (`db/queries.py:455-461`) no reconoce plurales ni ordinales. Prueba local: "artículos 8 y 9" y "artículo décimo transitorio" no se detectan. Tampoco reconoce "ter" ni "quáter" (sólo "bis") y toma sólo la primera mención. "artículo 8" también trae "8 Bis" (prueba local), lo que puede ser deseable pero no está documentado. Con un artículo detectado, los pesos suman 1.05 (0.45 + 0.15 + 0.25 + 0.20), aunque el comentario dice que suman 1 (`db/queries.py:704-727`). El respaldo de 0.15 nunca se usa porque `peso_titulo` vale 0.20 por omisión y ningún llamador lo cambia (`db/queries.py:616`, `710`).
- **Arreglo:** reconocer plurales, rangos y ordinales, definir los pesos en un solo lugar y probarlos.

#### IA-12 · P2 · Sinónimos y leyes cableados, índice vectorial sin ajustar
- **Evidencia:** hay 5 equivalencias de vocabulario (`db/sinonimos.py:22-31`) y 5 acrónimos más 9 frases de leyes (`db/leyes.py:26-45`). Están cableados, van en un solo sentido, no citan fuente y sólo un caso golden los prueba. Son decisiones jurídicas que debe validar un especialista. `init-db` (`main.py:685-704`) crea el índice IVFFlat (`db/schema.sql:204-206`) antes de que haya datos. La documentación de pgvector recomienda crearlo con la tabla ya poblada, y `ivfflat.probes` (1 por omisión) no se ajusta en ninguna parte. [SUPUESTO] El repositorio no tiene evidencia de que el índice se haya reconstruido. Si no se reconstruyó, la rama vectorial devuelve menos candidatos de los pedidos y con menor recall, y las señales FTS y de título lo compensan en parte.
- **Arreglo:** mover las equivalencias a datos versionados con fuente y pruebas, reconstruir el índice después de cargar (o usar HNSW) y fijar `probes` o `ef_search`.

#### IA-13 · P2 · El chat guarda historial pero no tiene memoria
- **Evidencia:** la web guarda los mensajes en `localStorage` (`web/index.html:2675-2701`), pero cada petición envía sólo la pregunta actual (`web/index.html:2790-2796`; `server.py:255-259`).
- **Qué pasa:** una pregunta de seguimiento ("¿y su reglamento?") se responde sin el contexto de la anterior, aunque la interfaz sugiere una conversación.
- **Arreglo:** mandar los turnos previos (y reescribir la consulta con ellos) o indicar en la interfaz que cada pregunta es independiente.

## 4. Datos

#### D-01 · P0 · El corpus no se puede reproducir desde el repositorio
- **Evidencia:** el repositorio no trae volcado, semillas ni manifiesto de fuentes, y `.gitignore:12-15` excluye `data/pdfs`, `data/raw` y `logs`. La vigencia y las notas se corrigieron a mano directamente en la BD (`CLAUDE.md:55-60`, `72-79`), y ningún script ni migración escribe `vigente` ni `nota_vigencia`. La columna `nota_vigencia` existe en `db/schema.sql:48`, pero no tiene migración. Hay `doc_ids` cableados en los scripts (`scripts/indexar_leyes_2025.py:46`, `scripts/indexar_manual_interconexion.py:54`) y en las pruebas (`tests/golden_queries.yaml:12-65`).
- **Qué pasa:** nadie más puede reconstruir el corpus, ni verificar una respuesta contra el mismo estado de datos, ni correr el golden set. Las cifras de `CLAUDE.md:37` (374 documentos y 11,112 fragmentos) no se pueden comprobar. [BRECHA DE DATO] El estado real de la BD.
- **Arreglo:** un manifiesto versionado (YAML o CSV) con URL, hash, fecha de descarga, vigencia y fuente de cada decisión; ingesta idempotente desde ese manifiesto; migraciones para todo cambio de esquema; ids estables (slug) en lugar de `SERIAL`.

#### D-02 · P1 · 30 scripts de un solo uso con datos cableados y operaciones destructivas
- **Evidencia:** son 30 scripts con 7,152 líneas (51% del Python). Contienen 137 literales `date(...)`, 70 asignaciones `"vigente": True/False` y 81 apariciones de URLs literales (conteo con grep). Cuatro ejecutan `DELETE`. `scripts/indexar_manual_interconexion.py:54` y `127-138` borran los ids 127, 128 y 129 sin confirmación ni dry-run; en otra BD esos ids serían otros documentos. `CLAUDE.md:214` advierte que no se deben volver a correr porque "pueden duplicar datos". A favor: 15 scripts ofrecen `--dry-run`.
- **Arreglo:** convertir cada script en entradas del manifiesto de D-01, borrar por clave estable y no por id, y archivar los scripts.

#### D-03 · P1 · Errores funcionales en el scraper del DOF
- **Evidencia:** `DOFScraper.desde` se guarda pero nunca se usa (`scrapers/dof_scraper.py:541`), así que `--desde` y `--desde-dias` no filtran nada (`main.py:500`, `999-1011`). La paginación incrementa `pagina` pero nunca la envía (`scrapers/dof_scraper.py:604`, `613-624`, `681`), y cada vuelta pide de nuevo la misma página. El ciclo termina por la regla de "toda la página ya está en la BD" (`scrapers/dof_scraper.py:675-677`), pero los resultados descartados como falso positivo no se registran en `scrape_log` (`scrapers/dof_scraper.py:714-720`) y se vuelven a descargar en cada corrida. Los documentos nuevos se detectan con `created_at >= NOW() - INTERVAL '1 hour'` (`main.py:1025`), que falla si la corrida dura más de una hora o si otro proceso inserta en paralelo.
- **Arreglo:** enviar el número de página y el rango de fechas, registrar los descartes y marcar los documentos nuevos con un id de corrida.

#### D-04 · P1 · La limpieza de PDF borra texto legal
- **Evidencia:** la regex `DIARIO OFICIAL.*?\n` con IGNORECASE (`processors/pdf_extractor.py:246-251`) borra todo desde "Diario Oficial" hasta el fin de línea, en cualquier parte del texto. Prueba local: "...entrará en vigor al día siguiente de su publicación en el Diario Oficial de la Federación." quedó como "...su publicación en el". También se eliminan las líneas que sólo contienen un número (`processors/pdf_extractor.py:254`), lo que puede borrar celdas de tablas tarifarias.
- **Qué pasa:** se pierden justo las cláusulas de entrada en vigor y de publicación, en todo documento que entra por PDF (CNE, CENAGAS y la mayoría de los scripts).
- **Arreglo:** quitar encabezados y pies por posición y repetición entre páginas, no por palabra clave, y reextraer los documentos afectados.

#### D-05 · P1 · Metadatos inferidos sin ninguna marca
- **Evidencia:** cuando el nombre del archivo sólo trae un año, `fecha_pub` se inventa como 1 de enero de ese año (`scrapers/cenagas_scraper.py:329-333`). `vigente=True` es el valor por omisión de todo lo descubierto (`scrapers/cenagas_scraper.py:434`, `scrapers/dof_scraper.py:184`). Emisor y tipo se deducen de palabras clave (`scrapers/cenagas_scraper.py:246-308`, `scrapers/dof_scraper.py:187-227`). En ningún lugar se guarda si un dato es inferido o verificado.
- **Qué pasa:** el filtro temporal de IA-04 opera sobre fechas que pueden ser inventadas.
- **Arreglo:** guardar el origen y la confianza de cada campo (por ejemplo `fecha_pub_origen`), dejar `NULL` en vez de inventar y revisar a mano lo inferido.

#### D-06 · P2 · URLs de fuente que no llevan al documento o que cambian
- **Evidencia:** la CNE usa una URL sintética, `https://www.cne.gob.mx/Acuerdos/#{numero}` (`main.py:1331`), que lleva al catálogo y no al documento. Los consolidados de Diputados apuntan a un archivo que se reemplaza con cada reforma (`scripts/indexar_reforma_2025.py:76-77`). El esquema no guarda el hash del archivo indexado (`db/schema.sql:52-63`).
- **Arreglo:** guardar la URL directa, el hash y una copia archivada o la fecha de corte.

#### D-07 · P2 · Integridad referencial y transaccional débil
- **Evidencia:** `scrape_log` no tiene restricción única, así que `ON CONFLICT DO NOTHING` no hace nada (`db/schema.sql:165-173`, `db/queries.py:1050-1057`). El upsert de fragmentos no actualiza `articulo` ni `titulo_seccion` (`db/queries.py:204-207`), y si se vuelve a fragmentar sin borrar antes, quedan fragmentos viejos. El documento y sus fragmentos se guardan en transacciones separadas (`main.py:1367-1376`).
- **Arreglo:** agregar restricciones únicas reales, reemplazar los fragmentos de un documento en una sola transacción y validar el resultado.

#### D-08 · P2 · Detalles de los monitores y del raspado
- **Evidencia:** en `monitor-cne`, `url_ya_scrapeada(url_fuente)` (`main.py:1332`) nunca devuelve verdadero, porque ese monitor no llama a `registrar_scrape`. La descarga de la CNE no verifica la firma `%PDF` (`scrapers/cne_drive.py:146-175`). Los scrapers se presentan como Chrome (`scrapers/dof_scraper.py:146-162`, `scrapers/cenagas_scraper.py:138-148`, `scrapers/cne_drive.py:31-34`). A favor: hay pausas de 2 a 3.5 s entre peticiones y reintentos con backoff.
- **Arreglo:** registrar cada descarga, validar el tipo de archivo y usar un User-Agent propio con dato de contacto del proyecto.

## 5. Front y accesibilidad

#### F-01 · P1 · Filtros que no coinciden con los datos
- **Evidencia:** la opción "Norma" envía `tipo=norma` (`web/index.html:1934`, `2090`; también `tipoTag` en `2507`), pero todo el código de ingesta escribe `nom` (`scrapers/dof_scraper.py:200-201`, `scrapers/cenagas_scraper.py:256-257`, `main.py:1316-1317`). Ningún selector de emisor ofrece CNE (`web/index.html:1918-1923`, `2027`, `2074`), aunque `CLAUDE.md:49` reporta 26 documentos de la CNE.
- **Qué pasa:** filtrar por normas devuelve cero resultados [SUPUESTO: la BD usa `nom`, como escribe todo el código de ingesta], y no hay forma de filtrar por el regulador actual.
- **Arreglo:** tomar los valores de los filtros de la API, no de listas cableadas.

#### F-02 · P1 · Accesibilidad: etiquetas, foco, anuncios y contraste
- **Evidencia:** hay 21 `<label>` y ninguna está asociada a su control (0 con `for=` y ninguna lo envuelve; por ejemplo `web/index.html:1913-1914`). Tres elementos clicables son `<div>` sin rol ni `tabindex` (`web/index.html:2350`, `3159`, `3319`). El CSS define `:focus-visible` para `.historial-item` (`web/index.html:1398`), pero ese elemento no puede recibir foco. No hay `aria-live` para las respuestas que llegan en streaming. El token `--text-muted` (#64748B) tiene contraste de 3.75:1 sobre #0F172A y de 3.07:1 sobre #1E293B, por debajo del 4.5:1 que pide WCAG AA. Se usa 33 veces, varias a 11 px (`web/index.html:2576`, `2839`). A favor: las pestañas son `<button>`, la página declara `lang="es"`, hay estilos `:focus-visible` y la página respeta `prefers-reduced-motion`.
- **Arreglo:** asociar las etiquetas, usar `<button>` para todo lo clicable, agregar `aria-live="polite"` a la zona de respuesta y subir el contraste del texto secundario.

#### F-03 · P2 · Peso, capas de estilo y tema
- **Evidencia:** todo está en un solo archivo de 181,145 bytes: unas 1,786 líneas de CSS, 1,651 de JS y 684 de HTML. Hay 243 `!important` y 147 atributos `style` en línea. Las capas de rediseño se apilan; por ejemplo, "F5, Design System V2" redefine los tokens de `:root` con `!important` (`web/index.html:1186-1205`). Precisión sobre el planteamiento original de esta auditoría: no existe un tema claro. El único tema es oscuro y está fijo (`web/index.html:2`, `class="dark"`), sin `prefers-color-scheme`; lo único en fondo blanco son los estilos de impresión (`web/index.html:584-592`). Tailwind Play CDN se carga (`web/index.html:7`), pero en el marcado no se encontró ninguna de sus clases utilitarias (búsqueda de prefijos `flex`, `grid`, `p-`, `m-`, `text-`, `bg-`, `w-`, `h-`, `rounded`, `hidden`). Al final del script se sobrescriben métodos en caliente (monkey patching, `web/index.html:4112-4131`).
- **Arreglo:** separar en componentes con una sola hoja de tokens, quitar Tailwind o usarlo de verdad, y ofrecer tema claro y oscuro según `prefers-color-scheme`.

## 6. Higiene

#### H-01 · P1 · Sin README, LICENSE, CI ni pruebas unitarias
- **Evidencia:** en la raíz no hay `README` ni `LICENSE`, y no existe `.github/` ni otra configuración de CI. `pyproject.toml:37-43` y `62-64` configuran pytest sobre `tests/`, pero no hay ningún `test_*.py`, así que pytest no recolecta nada. ruff y mypy están configurados (`pyproject.toml:51-60`), pero nada los ejecuta.
- **Qué pasa:** sin licencia explícita, los terceros no tienen un permiso claro de reutilización. Esto es una observación técnica: el alcance legal debe validarlo un especialista.
- **Arreglo:** escribir un README con instalación y alcance, elegir una licencia, y montar CI con lint, tipos, pruebas sin red y la búsqueda del guion largo.

#### H-02 · P1 · CLAUDE.md describe una BD que no está en el repositorio, y se contradice
- **Evidencia:**
  - Describe el estado de la BD ("374 documentos / 11,112 chunks") y decenas de `doc_ids` (`CLAUDE.md:35-51`, `55-83`).
  - Se contradice: CENAGAS tiene 26 documentos en `CLAUDE.md:48` y 3 en `CLAUDE.md:91`, y en `CLAUDE.md:232` se habla de "210 docs".
  - Dice que no hay frontend (`CLAUDE.md:236`), cuando `web/index.html` tiene 4,135 líneas.
  - Menciona pytesseract (`CLAUDE.md:29`), pero el código usa el OCR de PyMuPDF (`processors/pdf_extractor.py:1-11`).
  - Los pesos RRF que documenta (70/30 y 50/15/35, en `CLAUDE.md:159-165`) no son los del código (`db/queries.py:704-727`).
  - Da la reconexión al DOF como pendiente (`CLAUDE.md:173`, `225`), pero ya está implementada (`scrapers/dof_scraper.py:629-642`).
  - Llama "pipeline completo" a `python main.py` (`CLAUDE.md:190`), que sólo muestra la ayuda.
  - Sus ejemplos de código fallan: llaman a `buscar_hibrido` sin embedding y a `buscar_similitud` con texto (`CLAUDE.md:242-260`).
  - Documenta un alias del archivo de configuración personal del shell (`CLAUDE.md:147-155`).
  - La skill versionada `.claude/skills/golden-check.md` dice 8 casos en la línea 10 y 9 en la línea 36, y repite los pesos desactualizados (línea 16).
- **Arreglo:** dejar en el repositorio sólo la documentación del código; el estado de los datos debe salir del manifiesto de D-01 o de un comando `stats`.

#### H-03 · P1 · Ruta personal en un archivo versionado
- **Evidencia:** `.claude/skills/golden-check.md:31` contiene una ruta absoluta del equipo del autor, que deja ver su nombre de usuario, y `.gitignore:18-19` versiona esa carpeta a propósito. Es la única ruta personal del repositorio (búsqueda en todos los archivos).
- **Arreglo:** usar rutas relativas a la raíz del proyecto.

#### H-04 · P2 · Imágenes sueltas en la raíz
- **Evidencia:** hay 14 archivos `.png` y `.jpeg` en la raíz, con 4,867,061 bytes en total (cerca de 4.9 MB). Son capturas de iteraciones de diseño (`hero-*`, `pump-jack-*`, `tab-*`, `baseline-hero.png`, `final-with-pump.jpeg`) y ningún archivo del código las referencia.
- **Arreglo:** borrarlas, o moverlas a `docs/` (con Git LFS si se quieren conservar).

#### H-05 · P2 · Uso del guion largo (U+2014)
- **Evidencia:** hay 665 ocurrencias en 636 líneas de 52 archivos de texto: 296 en Python (40 archivos, 184 de ellas en `scripts/`), 306 en Markdown (241 en `audits/`, 51 en `CLAUDE.md` y 14 en la skill), 54 en HTML, 4 en `.env.example`, 3 en SQL y 2 en YAML. Cuatro están dentro de prompts que se envían al modelo (ver IA-08), y otras se usan como marcador de "sin dato" en la salida de la CLI (`main.py:580-586`).
- **Arreglo:** reemplazarlas, y agregar una búsqueda de U+2014 en CI y un marcador de "sin dato" que no sea ese carácter.

#### H-06 · P2 · `audits/` depende de la BD local
- **Evidencia:** son 5 documentos con 1,618 líneas. Registran decisiones editoriales valiosas, como el análisis de transitorios de la reforma de 2025, pero todo está referido a ids de una BD que no viaja con el repositorio.
- **Arreglo:** pasar esas decisiones al manifiesto de D-01, con su fuente, y archivar los informes.

## Qué se conserva

- **Regex de artículo con frontera numérica.** `art[íi]culo\s+N(\s|[^0-9]|$)` (`db/queries.py:489`, `766`) evita que "artículo 8" traiga el 80, y una prueba local lo confirmó. Junto con la bonificación para el fragmento cuyo campo `articulo` coincide (`db/queries.py:777-782`), resuelve bien la consulta por artículo exacto.
- **RRF con pesos por señal.** Fusiona cinco señales (vectorial, FTS, artículo, título por trigramas y ley nombrada) con un piso de 100 candidatos para que los ajustes de peso tengan material (`db/queries.py:611-797`). La expansión de vocabulario va sólo al FTS y no al embedding, para no diluir el vector (`db/queries.py:641-648`, `db/sinonimos.py:1-14`).
- **Chunker por jerarquía legal.** Sigue Título, Capítulo, Sección y Artículo, subdivide por fracciones, agrega el contexto jerárquico al texto que se embebe y tiene un parser aparte para manuales con secciones numéricas (`processors/chunker.py:192-200`, `358-412`, `488-541`).
- **Modelo de vigencia.** Distingue `nota_vigencia` y `es_version_historica` (`db/schema.sql:46-50`), y tiene un grafo de relaciones normativas con restricciones, watchlist y linaje recursivo (`db/schema.sql:128-159`, `db/queries.py:964-1033`).
- **Revisión de transitorios con un humano en el ciclo.** Detecta efectos, los resuelve por número y por trigramas con expansión de acrónimos, y reporta con `match_via` sin tocar la vigencia de forma automática (`processors/transitorios_review.py:15-17`, `231-305`).
- **SQL parametrizado.** No se encontró ningún punto de inyección. Las únicas interpolaciones son nombres de columna sacados de una lista blanca (`db/queries.py:97-116`) y fragmentos fijos.
- **`unaccent_immutable` y trigramas sobre el título** (`db/schema.sql:15-18`, `198-199`).
- **Buenas prácticas de raspado.** Pausas entre peticiones, reintentos con backoff, renovación de la sesión del DOF, filtro de falsos positivos por emisor dentro del contenido y exclusión de convocatorias "REF:" (`scrapers/dof_scraper.py:266-307`, `401-402`, `603-647`, `708-720`). En CENAGAS, el TLS relajado se aísla a un solo host y se documenta por qué.
- **Extracción de PDF en cascada.** pikepdf, luego pdfplumber, luego pymupdf4llm, con OCR sólo en las páginas que lo necesitan (`processors/pdf_extractor.py:273-413`).
- **Distinción entre `portal_origen` y `emisor`** (`db/schema.sql:56-58`).
- **Interfaz que hace visible la vigencia.** Muestra marcas de abrogado, versión histórica y salvedad, además de un semáforo (`web/index.html:2558-2613`). El concepto se conserva; falta aplicarlo a las fuentes citadas y no a las recuperadas (IA-01).
- **Hábito de regresión.** El golden set y la skill que lo corre antes y después de tocar la búsqueda, con las limitaciones conocidas documentadas con honestidad (`tests/golden_queries.yaml:75-91`).
- **Llaves sólo por entorno**, con `.env` ignorado y `.env.example` con marcadores.

## Cifras del antes

**Líneas por archivo principal**

| Archivo | Líneas |
|---|---|
| `main.py` | 1,669 |
| `server.py` | 673 |
| `db/queries.py` | 1,079 |
| `db/schema.sql` | 271 |
| `db/leyes.py` / `db/sinonimos.py` | 76 / 64 |
| `processors/chunker.py` | 710 |
| `processors/pdf_extractor.py` | 477 |
| `processors/transitorios_review.py` | 415 |
| `scrapers/dof_scraper.py` | 861 |
| `scrapers/cenagas_scraper.py` | 589 |
| `scrapers/cne_drive.py` | 192 |
| `web/index.html` | 4,135 (181,145 bytes) |
| `tests/run_golden.py` / `tests/golden_queries.yaml` | 132 / 91 |
| `CLAUDE.md` | 261 |

**Cifras generales**

| Medida | Valor |
|---|---|
| Python total | 45 archivos, 14,089 líneas |
| Scripts de un solo uso | 30 archivos, 7,152 líneas (51% del Python); 29 manipulan `sys.path`, 22 importan de `main.py`, 4 hacen `DELETE`, 10 usan `verify=False` |
| Terceros que carga la web | 5 orígenes declarados (cdn.tailwindcss.com, cdn.jsdelivr.net, cdnjs.cloudflare.com, fonts.googleapis.com, images.unsplash.com), más fonts.gstatic.com de forma implícita; 3 scripts, de ellos 2 sin versión; 0 atributos `integrity` |
| Pruebas | 9 casos golden, sólo de recuperación y con BD viva; 0 pruebas unitarias; 0 flujos de CI |
| Guion largo (U+2014) | 665 ocurrencias en 636 líneas de 52 archivos (Python 296, Markdown 306, HTML 54, `.env.example` 4, SQL 3, YAML 2) |
| Dependencias | 17 de ejecución y 4 de desarrollo declaradas; 4 importadas sin declarar (fastapi, uvicorn, pyyaml, playwright); 2 declaradas sin import directo (pgvector, Pillow); sólo cotas `>=`, sin lockfile |
| Endpoints | 10 rutas, 0 con autenticación, 1 sin consumidor en la web |
| Modelos | 2 ids distintos (`claude-opus-4-6` en la web, `claude-sonnet-4-6` en la CLI) |
| Prompts de sistema | 8 en línea, 3 pares duplicados |
| Manejo de errores | 53 `except Exception` |
| CSS de la web | 243 `!important`, 147 atributos `style` en línea |
| Imágenes sueltas en la raíz | 14 archivos, 4,867,061 bytes |
| Estado de la BD según CLAUDE.md | 374 documentos y 11,112 fragmentos (`CLAUDE.md:37`) [BRECHA DE DATO: no se puede verificar desde el repositorio] |

## Cómo se atendió y cifras del después

La versión 1.0 no parcha el prototipo: lo reemplaza. Así quedó cada hallazgo P0 y P1.

| Hallazgo | Severidad | Cómo quedó en 1.0 |
|---|---|---|
| S-01 Servidor expuesto sin autenticación | P0 | `serve` escucha en 127.0.0.1; la API sólo tiene lecturas (`GET`), no dispara procesos ni gasta créditos: no hay llaves. |
| D-01 Corpus no reproducible | P0 | Manifiesto `corpus/fuentes.yaml` con fuente oficial por documento; textos troceados versionados en `corpus/textos/`; `ley-energia indexar` reconstruye el índice igual en cualquier máquina y en CI. |
| A-01 Lógica duplicada | P1 | Un solo motor (`busqueda.py`) que usan la CLI, la API y el servidor MCP. |
| A-02 E/S síncrona en `async` | P1 | Endpoints síncronos sobre SQLite de sólo lectura; ya no hay llamadas a APIs externas. |
| A-03 Empaque roto | P1 | Paquete en `src/`, dependencias completas y `uv.lock`. |
| S-02 CSRF y DNS rebinding | P1 | Sin endpoints que escriban; cabeceras de seguridad y CSP estricta. |
| S-03 XSS | P1 | La web arma todo con nodos de texto; nada de `innerHTML` con datos (lo verifica una prueba). |
| S-04 Terceros sin versión | P1 | Cero terceros: fuentes y código auto hospedados; CSP `default-src 'self'`. |
| S-05 TLS desactivado | P1 | Todas las descargas verifican TLS. |
| IA-01 Sin citas verificables | P1 | Cada resultado trae `cita` (documento y artículo), `url_oficial` y el texto completo vía `leer_articulo`; Claude cita desde ahí. |
| IA-02 Vigencia invisible para el modelo | P1 | Cada resultado lleva `vigente`, `abrogada_desde`, `sustituido_por` y `nota_vigencia`. |
| IA-03 Filtro de vigentes saltado | P1 | Las señales se calculan sobre el conjunto ya filtrado; una abrogada sólo entra si la consulta la nombra o se pide. |
| IA-04 Vigencia temporal por documento | P1 | Filtro `fecha` con `vigor_desde` y `abrogada_desde` verificados en los transitorios; probado en la evaluación. La versión histórica de cada texto queda pendiente (ver README). |
| IA-05 Transitorios y artículos cortos perdidos | P1 | El chunker reconoce transitorios, disposiciones numeradas, anexos y rubros; los transitorios de cada decreto de reforma llevan clave propia con su fecha del DOF; pruebas unitarias. |
| IA-06 Evaluación mínima | P1 | 40 casos verificados contra el texto, corren en CI. |
| D-02 Scripts de un solo uso | P1 | Eliminados: un manifiesto y un solo indexador. |
| D-03 a D-05 Errores de ingesta y metadatos inferidos | P1 | Fechas sólo del manifiesto (verificadas); limpieza de PDF por líneas de encabezado, sin borrar texto. |
| F-01 y F-02 Filtros y accesibilidad | P1 | Filtros con los mismos tipos que el manifiesto; etiquetas asociadas, foco visible, navegación con teclado y contraste de 4.5:1 o más en texto. |
| H-01 a H-03 Higiene | P1 | README bilingüe, licencias, CI, pruebas; `CLAUDE.md` nuevo; sin rutas personales. |

| Medida | Abril 2026 | 1.0 |
|---|---|---|
| Python | 45 archivos, 14,089 líneas | 22 archivos, 3,061 líneas (código y pruebas) |
| Archivo más grande | `web/index.html`, 4,135 líneas | `chunker.py`, 503 líneas |
| Web | 1 archivo de 181 KB, 5 orígenes de terceros | 4 archivos, 55 KB, 0 terceros |
| Pruebas | 9 casos que exigen BD viva, 0 unitarias, 0 CI | 41 pruebas sin red, 40 casos de evaluación que corren en dos motores, 3 flujos de CI |
| Evaluación (40 casos) | no existía | híbrida: recall@5 1.00, MRR 0.89, 40 de 40; motor del sitio estático: recall@5 1.00, MRR 0.92, 40 de 40 |
| Llaves de servicios | 2 (Voyage y Anthropic) | 0 |
| Endpoints que escriben o lanzan procesos | 2 | 0 |
| `except Exception` | 53 | 0 |
| Guion largo (U+2014) | 665 | 0 |
| Corpus reproducible | no | sí: 35 documentos y 4,417 fragmentos desde `corpus/fuentes.yaml` |
