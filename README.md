<p align="center">
  <img src="assets/banner.svg" alt="ley·energía: Mexico's energy regulation, article by article" width="100%">
</p>

<p align="center">
  <b>English</b> · <a href="README.es.md">Español</a>
</p>

<p align="center">
  <a href="https://github.com/BEG-lag/ley-energia-mx/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/BEG-lag/ley-energia-mx/actions/workflows/ci.yml/badge.svg"></a>
  <a href="https://beg-lag.github.io/ley-energia-mx/"><img alt="Site" src="https://img.shields.io/badge/site-live-cfff45?labelColor=0a0c10"></a>
  <img alt="API keys needed" src="https://img.shields.io/badge/API%20keys-none-7fd8ff?labelColor=0a0c10">
  <a href="LICENSE"><img alt="Code: MIT" src="https://img.shields.io/badge/code-MIT-eceee6?labelColor=0a0c10"></a>
  <a href="DATA-LICENSE.md"><img alt="Data: CC0" src="https://img.shields.io/badge/data-CC0-eceee6?labelColor=0a0c10"></a>
</p>

**ley-energia-mx** makes Mexico's energy regulation searchable and citable by article: the laws of
the 2025 energy reform, their regulations, the general administrative provisions (DACG) issued by
the Comisión Nacional de Energía, and the 2014 laws they replaced, with validity dates and
lineage. Every result carries its citation ("LSE, artículo 30"), whether it is in force, what
replaced it, and the link to the official publication.

It works with **Claude over MCP, with no API keys**: Claude does the reasoning with your own
subscription; this repository only serves official text with its citation. There is also a CLI, a
local web app with hybrid search, and a static site that searches in your browser.

**Site:** [beg-lag.github.io/ley-energia-mx](https://beg-lag.github.io/ley-energia-mx/) ·
**Corpus:** [`corpus/fuentes.yaml`](corpus/fuentes.yaml) ·
**Evaluation:** [`evaluacion/golden.yaml`](evaluacion/golden.yaml)

| Home | Search | Phone |
| --- | --- | --- |
| <img src="assets/captura-escritorio.png" alt="Home page: headline, search box with filters by type, abrogated laws and date, and corpus figures" width="420"> | <img src="assets/captura-busqueda.png" alt="Results for 'artículo 30 de la LSE': LSE article 30 first, marked as in force, with links to read it in full and to the official source" width="420"> | <img src="assets/captura-celular.png" alt="The same page on a 375 px phone" width="160"> |

<p align="center"><sub>Real screenshots of the site built from the committed corpus and served locally. The interface is in Spanish.</sub></p>

## Use it with Claude

```bash
git clone https://github.com/BEG-lag/ley-energia-mx
cd ley-energia-mx
uv sync
uv run ley-energia indexar     # builds data/ley-energia.sqlite locally (about a minute)
```

- **Claude Code:** open Claude Code inside the folder; `.mcp.json` registers the server. Or add it
  from anywhere: `claude mcp add ley-energia -- uv --directory /path/to/ley-energia-mx run ley-energia mcp`.
- **Claude Desktop:** add to `claude_desktop_config.json`:

  ```json
  "mcpServers": {
    "ley-energia": {
      "command": "uv",
      "args": ["--directory", "/path/to/ley-energia-mx", "run", "ley-energia", "mcp"]
    }
  }
  ```

The server is read-only and exposes five tools and three prompts:

| Tool | What it returns |
| --- | --- |
| `buscar` | Hybrid search with filters by type, issuer, abrogated laws and **date** (the regime in force that day). Each hit has `cita`, validity, successor and `url_oficial`. |
| `leer_articulo` | The full text of an article, provision ("1.2") or transitory article ("transitorio segundo"; those of each amending decree carry its DOF date, e.g. "transitorio primero (dof 2021-03-09)"). |
| `documento` | Publication data, validity, lineage and the table of contents of a document. |
| `linaje` | What a norm replaced and what replaced it, with the date and legal basis. |
| `catalogo` | Everything in the corpus with its status. |

Prompts: `due_diligence` (regulatory review of a project), `regimen_temporal` (what applied on a
date) and `regulacion_aplicable`. The repository also ships two Claude Code skills in
[`.claude/skills/`](.claude/skills). The server instructions tell Claude to read before citing, to
cite document and article, to flag abrogated norms, to say when the corpus has no support, and to
treat document text as data, not instructions.

Nothing to install: the site's **Copiar para Claude** button copies your question,
the full text of the top results with their citations, and the answering instructions, ready to
paste into Claude.

## Command line

```bash
uv run ley-energia buscar "permisos de generación de energía eléctrica"
uv run ley-energia buscar "permisos de generación" --fecha 2020-01-01   # regime in force that day
uv run ley-energia articulo LSE 30
uv run ley-energia linaje LIE
uv run ley-energia serve        # http://127.0.0.1:8000 with hybrid search
uv run ley-energia evaluar -v   # runs the 40-case evaluation
```

## What is in the corpus

Cutoff: **25 November 2026**. 35 documents, 4,417 fragments, 3,376 articles and provisions.

| Group | Documents |
| --- | --- |
| Laws in force (2025 reform and related) | LSE, LSH, LPTE, Ley de la CNE, LEPECFE, LEPEPM, Ley de Geotermia, Ley de Biocombustibles, LIH, Ley de la ASEA (from [leyes-mx](https://github.com/BEG-lag/leyes-mx)) |
| Regulations | Reglamentos of the LSE, LSH, LPTE, Geotermia, Biocombustibles, LEPECFE, LEPEPM and LIH (Cámara de Diputados) |
| CNE DACG | Generation and storage permits, transmission tariffs, self-supply, competitive mechanisms, cogeneration, storage integration, hydrocarbon permit terms, commercialization (DOF) |
| Abrogated, with lineage | LIE → LSE, LH → LSH, LTE → LPTE, LORCME → Ley de la CNE, LCFE → LEPECFE, LPM → LEPEPM, Ley de Energía Geotérmica → Ley de Geotermia, LPDB → Ley de Biocombustibles, CRE Agreement A/113/2024 → CNE storage DACG |

Abrogation dates were checked against the transitory articles of each replacing instrument (for
example, the 2025 laws took effect on 19 March 2025; the CNE storage DACG took effect on the next
business day after 16 April 2026 and left A/113/2024 without effect).

## How search works

1. **Manifest.** [`corpus/fuentes.yaml`](corpus/fuentes.yaml) declares each document, its official
   source, publication and validity dates and its successor. `ley-energia actualizar` downloads and
   segments; the segmented texts are versioned in `corpus/textos/`, so the index can be rebuilt
   anywhere without touching government sites.
2. **Segmentation by legal unit.** One fragment per article, numbered provision (DACG) or
   transitory article, keeping its path (Title, Chapter, Section). Long articles are split into
   numbered parts without losing the article key.
3. **Single-file index.** SQLite with FTS5 over Spanish Snowball stems and local embeddings
   ([`paraphrase-multilingual-MiniLM-L12-v2`](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)
   through fastembed/ONNX). No database server, no extensions, no keys.
4. **Weighted reciprocal rank fusion** of four signals: lexical, vector, exact article (so
   "artículo 8" never returns article 80) and named document (acronyms, aliases and titles; the
   longest name wins, so "Reglamento de la LSE" is the regulation, not the law). Old 2014 vocabulary
   ("venta directa", "autoabasto") is mapped to the 2025 terms.
5. **Validity filters.** By default only norms in force; an abrogated one is included when the
   query names it or when you ask for a date.

### Evaluation

40 cases written from the official text, not from what the engine returned: exact articles, named
documents, topics, 2014 vocabulary and point-in-time regimes.

| Engine | Recall@5 | MRR | Cases passed |
| --- | --- | --- | --- |
| Hybrid, Python (CLI, local web, MCP) | 1.00 | 0.89 | 40 / 40 |
| In-browser, JavaScript (the static site, `web/js/motor.js`, measured with Node) | 1.00 | 0.92 | 40 / 40 |

CI rebuilds the index and runs both evaluations on every push. The browser engine is
deterministic and must pass every case; the hybrid one must pass every exact-article,
first-place and validity case and keep recall@5 at 0.95 or more and MRR at 0.85 or more,
because the ONNX model can differ slightly between platforms on borderline topic cases.

## Add a document

Add an entry to `corpus/fuentes.yaml` (formats: `leyes-mx`, `pdf`, `dof`), then:

```bash
uv run ley-energia actualizar --solo <id>
uv run ley-energia indexar
uv run ley-energia evaluar
```

A scheduled workflow re-downloads every source each Monday and opens a pull request if any
official text changed.

## Limitations

- It is a curated corpus, not all of Mexico's energy regulation: no NOMs, CENACE market manuals or
  CRE/CNH regulation other than A/113/2024.
- The date filter selects which documents were in force on a date, but each text is the version as
  of the cutoff. For laws reformed after publication (for example, the LIH), the historical wording
  of each article is not reconstructed.
- DOF notes are extracted from HTML; tables and images in annexes may be incomplete.
- The embedding model is small and general-purpose. On this evaluation set the lexical, exact-article
  and named-document signals carry most of the work; the vectors help with paraphrased questions.

## Legal notice

Information from official sources, for informational purposes only. It is not legal or tax advice.
The only authoritative versions are the official publications in the DOF and of each issuing
authority; validate with the competent authority.

## Background

The first version (April 2026) was a private prototype with Postgres, paid embeddings and Claude API
calls. It was audited and rebuilt from scratch for this release; the audit and a before-and-after
table are in [audits/2026-11-auditoria.md](audits/2026-11-auditoria.md) (Spanish).

## License and credits

Code under the [MIT License](LICENSE). Data and the project's additions under CC0; see
[DATA-LICENSE.md](DATA-LICENSE.md). Fonts under the SIL Open Font License.

Made by Benjamín Esponda García, [PIVOTEK](https://pivotek.mx). Related:
[leyes-mx](https://github.com/BEG-lag/leyes-mx) (federal laws with history),
[radar·energía](https://beg-lag.github.io/radar-energia/) (daily energy radar). For lawyers:
[Con Criterio](https://concriterio.mx), an AI toolkit for legal practice in Mexico.
