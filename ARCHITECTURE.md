# Sniff MCP: architecture

The aim is that a new kind of data drops in without a rewrite. This note describes how the system is built and how it grows.

## The four layers
```
ARTIFACTS  (static, built from a pinned release and copied to local disk)
   │   point_store.sqlite (variant scalars + per-breed float16 vectors) · variant_master.parquet
   │   breed_af.parquet · sites VCF (tabix) · knowledge-graph parquet · disease layer · text index
   ▼
LOADERS    (sniff_mcp/query.py: lazy and cached; SQLite mmap, DuckDB over parquet, graph in memory)
   ▼
RPCs       (query-layer methods, one contract; every return carries a provenance block)
   ▼
SURFACES   (MCP server over Streamable HTTP, REST at api.sniff.world; both call the same RPCs)
```
**Rule:** surfaces never touch artifacts directly; they only call RPCs, and RPCs only call loaders. That is why adding a surface or a kind of data is additive.

## Adding a kind of data
Four small, isolated steps:
1. **Build** a static artifact (a parquet, a packed binary, or new columns) from the release. Deterministic and cacheable.
2. **Load** it with a lazy accessor in `query.py`.
3. **Serve** it as an RPC that returns a dict; the provenance block and the `UNPROVEN` flag come from `_prov()`.
4. **Expose** it as an MCP tool and a REST route.

Point lookups never read the wide parquet, and nothing reaches remote storage at request time.

## What it serves today
- **Frequency and annotation:** global and per-breed allele frequency, popmax, SnpEff consequence, Pangolin and phyloP values. No pathogenicity is assigned to any variant.
- **Breed carrier frequencies:** the published per-breed carrier-frequency graph, with sample sizes.
- **Breed geometry:** nearest breeds and similarity from the atlas embedding.
- **Search:** semantic search over the graph's entities.
- **Diseases:** the OMIA clinical layer, with the human analog and evidence base.
- **Questions:** `ask`, which answers only from cited data or abstains.

The live tool list, with the data release it serves, is at [`/v1/metadata`](https://api.sniff.world/v1/metadata).

## Why it holds up
- **Static artifacts** are deterministic and portable: moving hosts is a file copy.
- **Uniform provenance:** every RPC inherits the citation and `UNPROVEN` contract, so an uncited claim cannot ship.
- **Structured answers only,** so the contract is stable for agents.
- **Release-pinned versions:** a data update does not break an agent, and old releases stay reproducible.
- **One query layer, many surfaces:** MCP and REST cannot diverge.
