# Changelog

## 1.0.0 (2026-11-25)

Public version, rebuilt from scratch. See [audits/2026-11-auditoria.md](audits/2026-11-auditoria.md)
for what was wrong with the April version and how each finding was handled.

- Reproducible corpus: a manifest (`corpus/fuentes.yaml`) with 35 documents and their official
  source; texts segmented by article, provision or transitory article and versioned in
  `corpus/textos/`.
- Single-file SQLite index: FTS5 over Spanish Snowball stems plus local embeddings
  (`paraphrase-multilingual-MiniLM-L12-v2` via fastembed), fused with weighted RRF together with
  exact-article and named-document signals. No database server, no API keys.
- Validity and lineage: every abrogated law points to its successor; searches can be restricted to
  the regime in force on any date.
- MCP server (`ley-energia mcp`) with five read-only tools and three prompts, plus two Claude Code
  skills. Claude does the reasoning with the user's own subscription.
- Static site for GitHub Pages with in-browser search, article reader, catalog and lineage; the
  same page gets hybrid search when served locally.
- Transitory articles of each amending decree get their own key with the DOF date, so every
  citation points to one unit.
- 40-case evaluation set (`evaluacion/golden.yaml`) run against both engines (Python and the
  in-browser one), 41 unit tests, CI, weekly corpus refresh that opens a pull request when an
  official text changes.

## 0.1.0 (2026-04-14)

Private prototype: Postgres + pgvector, Voyage embeddings and Claude API calls with keys, 30
one-off indexing scripts, a single 4,135-line HTML page. Its database was deleted in October 2026
and is not reproducible; it lives on only as history.
