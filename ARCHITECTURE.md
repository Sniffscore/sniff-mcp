# Sniff MCP — Architecture (built to compound)

The design goal is not just v1; it's that **every future dimension drops in without a rewrite.** This doc is the contract for how the system grows.

## The four layers
```
ARTIFACTS  (static, produced by precompute from the quarterly release; pulled to local NVMe)
   │   point_store.sqlite (variant scalars + 188-breed float16 vectors) · variant_master.parquet
   │   breed_af.parquet · sites VCF (tabix) · KG parquet · [future: selection, constraint, PRS, ROH, embeddings]
   ▼
LOADERS    (sniff_mcp/query.py — lazy, cached: SQLite mmap, DuckDB-over-parquet, KG-in-RAM, [vector index])
   ▼
RPCs       (query-layer methods — one contract, FUNCTION_SURFACE.md; every return carries the provenance block)
   ▼
SURFACES   (MCP server [Streamable HTTP], REST [api.sniff.world], website internal route — all over the SAME RPCs)
```
**Rule:** surfaces never touch artifacts directly; they only call RPCs. RPCs only call loaders. This is why adding a surface (done: MCP + REST) or a dimension is additive.

## How to add a dimension (the compound pattern)
A new roadmap dimension = **four small, isolated additions**, never a re-architecture:
1. **Precompute** → emit a static artifact (a parquet, a packed binary, or new columns) in the quarterly build. Deterministic, cacheable, portable.
2. **Loader** → a lazy accessor in `query.py` (mmap / DuckDB view / in-RAM dict / vector index).
3. **RPC(s)** → method(s) returning a dict; they get the `provenance` block + `UNPROVEN` discipline for free via `_prov()`.
4. **Expose** → add the `@mcp.tool` wrapper + a REST route. Done.

Nothing above the new RPC changes. The hot-path rule holds: **point lookups never hit the wide parquet; nothing queries R2 at request time.**

## Roadmap mapping (ROADMAP_FUTURE_DIMENSIONS.md → where each plugs in)
| Dimension | Artifact (precompute) | Loader | RPC(s) | Phase |
|---|---|---|---|---|
| Frequency / annotation / pathogenicity | point_store + master.parquet | sqlite + duckdb | ask_variant_context, variant_lookup, gene_summary, variant_search | **v1 (shipped)** |
| Breed carrier-freq KG | kg parquet | in-RAM | breed_variant_frequency, disease_links | v1 |
| **Geometry (PCA-256/UMAP)** | dog/breed embeddings (we already have them) | in-RAM / vector | `nearest_breeds`, `dog_neighbors`, `where_in_space` | **v1.1** |
| **Semantic search** | text embeddings of KG/entities | sqlite-vec | `semantic_search` | **v1.1** |
| D2 Selection Atlas (FST/PBS) | selection.parquet | duckdb | `breed_selection`, `variant_selection` | v1.x |
| D3 Gene constraint (LOEUF analog) | constraint column | duckdb | enrich gene_summary + `gene_constraint` | v1.x |
| D10 Genome ring / ROH-COI | per-dog ROH artifact | sqlite | `dog_genome_ring`, `breed_coi` | v1.x |
| D5 Per-dog PRS | PRS table (needs cohort) | sqlite | `prs` | v2 |
| **Living atlas** | ingest refreshes artifacts on schedule | (same) | `atlas_status` + timestamp in provenance | v2 |
| Multi-cohort frequency (DA+NHGRI WGS) | additional breed-AF artifacts | (same) | (same RPCs, larger cohort) | v2 |

## Why this compounds
- **Static artifact + precompute** → deterministic, edge-cacheable, portable (Azure→AWS→Hetzner is a file copy).
- **Uniform provenance** → every new dimension inherits the rigor/citation/UNPROVEN contract; we can't ship an un-cited claim by construction.
- **Structured-only** → NL stays in the web lane; the contract is stable for agents.
- **Release-pinned versioning** → quarterly data bumps don't break agents; old releases stay reproducible.
- **One query layer, many surfaces** → MCP, REST, website, and future surfaces never diverge.

## Reserved RPC namespace (planned — so the contract anticipates growth)
`nearest_breeds`, `dog_neighbors`, `where_in_space` (geometry) · `semantic_search` (embeddings) · `breed_selection`/`variant_selection` (D2) · `gene_constraint` (D3) · `dog_genome_ring`/`breed_coi` (D10) · `prs` (D5) · `atlas_status` (living atlas). Adding any is additive per the pattern above.
