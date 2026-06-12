# sniff-mcp — agent-callable canine genomics

[![PyPI](https://img.shields.io/pypi/v/sniff-mcp)](https://pypi.org/project/sniff-mcp/)
[![npm](https://img.shields.io/npm/v/sniff-mcp)](https://www.npmjs.com/package/sniff-mcp)
[![MCP Registry](https://img.shields.io/badge/MCP_Registry-world.sniff%2Fsniff--mcp-6E40C9)](https://registry.modelcontextprotocol.io)
[![DOI](https://img.shields.io/badge/DOI-10.5281%2Fzenodo.20566358-1f7a1f)](https://doi.org/10.5281/zenodo.20566358)
[![Data: CC-BY-4.0](https://img.shields.io/badge/data-CC--BY--4.0-lightgrey)](https://creativecommons.org/licenses/by/4.0/)

**The reference layer for dog DNA.** A live, open API + [MCP](https://modelcontextprotocol.io) server over the **Sniff Atlas** — breed-stratified allele frequencies for **9,667,790 variants across 188 dog breeds** (CanFam4), calibrated AI pathogenicity (ESM2, AUC 0.935 vs OMIA), Pangolin splice, Zoonomia phyloP conservation, and a variant ⇄ gene ⇄ breed ⇄ disease knowledge graph. **Every response carries its own citation + provenance.**

> Building anything with dogs, breeds, or canine health? This is the data layer. No key, no signup — point your agent or app at it and go.

- 🔌 **MCP endpoint:** `https://mcp.sniff.world/mcp/` (Streamable HTTP, 15 tools) — including **`ask`**, a grounded canine-genetics Q&A that answers **only from cited data or honestly abstains** (no hallucinated dog-health advice), and **`disease_bridge`** (inherited-disease atoms with ACMG-style pathogenicity grades + the dog⇄human homolog)
- 🌐 **REST API:** `https://api.sniff.world/` ([OpenAPI docs](https://api.sniff.world/docs) · [`llms.txt`](https://api.sniff.world/llms.txt))
- 📚 **Dataset:** [10.5281/zenodo.20566358](https://doi.org/10.5281/zenodo.20566358) (CC-BY-4.0)

---

## Add it to your coding agent (copy-paste)

The hosted server is open and needs no auth. Pick your tool:

**Claude Code**
```bash
claude mcp add --transport http sniff https://mcp.sniff.world/mcp/
```

**Cursor / Windsurf / VS Code** — add to your MCP config (`.cursor/mcp.json`, `mcp.json`, etc.):
```json
{
  "mcpServers": {
    "sniff": { "url": "https://mcp.sniff.world/mcp/" }
  }
}
```

**Claude Desktop** or any stdio-only client (uses the hosted server via a local bridge):
```json
{
  "mcpServers": {
    "sniff": { "command": "npx", "args": ["-y", "sniff-mcp"] }
  }
}
```

That's it. Ask your agent: *"What's the frequency of CPT2 5:56189113 across breeds?"* or *"Find HIGH-impact variants in DLA genes."*

---

## Use the REST API (for web apps)

No SDK needed — it's plain HTTP/JSON.

```bash
curl https://api.sniff.world/v1/variant/5:56189113
```
```jsonc
{
  "variant_id": "5:56189113", "ref": "A", "alt": "G",
  "global_af": 0.0185, "popmax_af": 0.591, "popmax_breed": "akita",
  "consequence": "missense_variant", "impact": "MODERATE",
  "gene": "CPT2", "esm2_llr": -6.1, "deleteriousness_tier": "...",
  "provenance": { "dataset_doi": "10.5281/zenodo.20566358",
                  "predicted_disease_relevance": "UNPROVEN", "...": "..." }
}
```

```js
// JavaScript / TypeScript
const r = await fetch("https://api.sniff.world/v1/variant/5:56189113/context?breed=akita");
const ctx = await r.json(); // frequency + pathogenicity + gene + cross-breed + provenance
```

| Endpoint | What it returns |
|---|---|
| `GET /v1/variant/{pos}` | single variant: AF, popmax, consequence, gene, ESM2/Pangolin/phyloP |
| `GET /v1/variant/{pos}/context` | **the joined query** — everything about a variant in one call |
| `GET /v1/breed/{breed}` | breed profile (top variants, geometry, nearest breeds) |
| `GET /v1/breed/{breed}/nearest` | genetically nearest breeds (PCA distance) |
| `GET /v1/gene/{symbol}` | variants in a gene, ranked by impact |
| `GET /v1/semantic?q=` | natural-language search ("ancient arctic sled dogs") |
| `GET /v1/search` | filtered discovery across all 9.67M variants |
| `GET /v1/metadata` | release, DOI, counts, scope banner |

Positions are **CanFam4** `chrom:pos` (e.g. `5:56189113`). Full schema: **https://api.sniff.world/openapi.json**.

---

## Self-host (optional)

```bash
uvx sniff-mcp          # run the MCP server locally (needs the release data on disk)
pip install sniff-mcp  # or install into your env
```
See [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`Dockerfile`](Dockerfile). The hosted endpoint is the easy path; self-hosting is for air-gapped or high-volume use.

---

## What it is (and isn't)

Built from [CanVAS](https://doi.org/10.5281/zenodo.19186944) (14,478 dogs, Beagle-imputed, MAF≥1%) plus projected community cohorts. Pathogenicity is **computational** — every prediction is flagged `predicted_disease_relevance: "UNPROVEN"`. This is a research and discovery resource, **not a clinical diagnostic.** The scope (common + low-frequency variants, MAF≥1%) and the UNPROVEN caveat ride in every response's `provenance` block, so anything an agent quotes stays honest and self-citing.

## Citation

> Gehring, M. (2026). *Sniff Atlas.* Zenodo. https://doi.org/10.5281/zenodo.20566358 (CC-BY-4.0)

```bibtex
@dataset{sniff_atlas_2026,
  author    = {Gehring, Matt},
  title     = {Sniff Atlas},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.20566358},
  url       = {https://sniff.world}
}
```

**Code** MIT · **Data** CC-BY-4.0 · world.sniff/sniff-mcp · https://sniff.world
