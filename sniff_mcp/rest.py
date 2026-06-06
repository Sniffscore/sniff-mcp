#!/usr/bin/env python3
"""Sniff REST API (api.sniff.world/v1) — thin HTTP surface over the SAME query layer as the MCP.
Run: uvicorn sniff_mcp.rest:app  (Cloudflare in front for cache/rate-limit/WAF in prod).

Self-documenting for agents: rich OpenAPI at /openapi.json, human docs at /docs,
an orientation object at /, and a plaintext manual at /llms.txt.
"""
from fastapi import FastAPI, Query
from fastapi.responses import PlainTextResponse
from typing import Optional, List
from .query import SniffQuery

DESCRIPTION = (
    "Open, agent-callable canine genomics over the **Sniff Atlas**: breed-stratified allele "
    "frequencies for 9,667,790 variants across 188 dog breeds (CanFam4), calibrated ESM2 "
    "pathogenicity (AUC 0.935 vs OMIA), Pangolin splice, Zoonomia phyloP, and a "
    "variant/gene/breed/disease knowledge graph. No API key.\n\n"
    "**Identifiers:** positions are CanFam4 `chrom:pos` (e.g. `5:56189113`).\n"
    "**Start with** `/v1/variant/{pos}/context` — the joined query (frequency + pathogenicity + "
    "gene + cross-breed + provenance) in one call.\n"
    "**Rigor:** every response carries a `provenance` block with the dataset DOI, scope "
    "(MAF≥1%, imputed), and `predicted_disease_relevance: UNPROVEN`. Computational predictions, "
    "not clinical diagnoses.\n\n"
    "MCP server: `https://mcp.sniff.world/mcp/` · Dataset: https://doi.org/10.5281/zenodo.20566358 (CC-BY-4.0)"
)

TAGS = [
    {"name": "variants", "description": "Single-variant lookup and the joined context query."},
    {"name": "breeds", "description": "Breed profiles, genetic geometry, nearest breeds."},
    {"name": "genes", "description": "Variants within a gene."},
    {"name": "discovery", "description": "Filtered search, semantic search, metadata."},
    {"name": "diseases", "description": "Disease → gene/variant/breed links (knowledge graph)."},
    {"name": "meta", "description": "Service orientation, health, agent manual."},
]

app = FastAPI(
    title="Sniff API",
    summary="Agent-callable canine genomics over the open Sniff Atlas.",
    description=DESCRIPTION,
    version="0.1.0",
    contact={"name": "Sniff", "url": "https://sniff.world", "email": "matt@sniff.world"},
    license_info={"name": "Data CC-BY-4.0 / Code MIT", "url": "https://creativecommons.org/licenses/by/4.0/"},
    servers=[{"url": "https://api.sniff.world", "description": "Production"}],
    openapi_tags=TAGS,
    terms_of_service="https://sniff.world",
)
Q = SniffQuery()
_ = Q.kg  # pre-warm KG at startup


@app.get("/", tags=["meta"], summary="Service orientation (what this is + where to go)")
def root():
    """Machine-readable orientation for agents arriving at the base URL."""
    return {
        "name": "Sniff API",
        "description": "Agent-callable canine genomics over the open Sniff Atlas.",
        "release": Q.release, "n_variants": Q.n_variants, "n_breeds": len(Q.breeds),
        "assembly": "canfam4",
        "docs": "https://api.sniff.world/docs",
        "openapi": "https://api.sniff.world/openapi.json",
        "llms_txt": "https://api.sniff.world/llms.txt",
        "mcp_endpoint": "https://mcp.sniff.world/mcp/",
        "mcp_registry": "world.sniff/sniff-mcp",
        "start_here": "https://api.sniff.world/v1/variant/5:56189113/context",
        "dataset_doi": "10.5281/zenodo.20566358",
        "license": {"data": "CC-BY-4.0", "code": "MIT"},
        "citation": "Gehring M. (2026) Sniff Atlas. Zenodo. https://doi.org/10.5281/zenodo.20566358",
        "rigor": "Predictions are computational (predicted_disease_relevance=UNPROVEN), not clinical. MAF>=1%.",
    }


LLMS_TXT = """# Sniff Atlas — canine genomics for agents

> Open API + MCP server for dog DNA: breed-stratified allele frequencies for 9,667,790
> variants across 188 dog breeds (CanFam4), calibrated AI pathogenicity, and a
> variant/gene/breed/disease knowledge graph. No API key. Every response is self-citing.

## Use it
- REST base: https://api.sniff.world  (OpenAPI: https://api.sniff.world/openapi.json)
- MCP (Streamable HTTP): https://mcp.sniff.world/mcp/   (registry: world.sniff/sniff-mcp)
- Identifiers: CanFam4 chrom:pos, e.g. 5:56189113

## Key endpoints
- GET /v1/variant/{pos}/context  — START HERE: frequency + pathogenicity + gene + cross-breed + provenance in one call
- GET /v1/variant/{pos}          — single variant
- GET /v1/breed/{breed}          — breed profile (geometry, top variants, nearest breeds)
- GET /v1/breed/{breed}/nearest  — genetically nearest breeds
- GET /v1/gene/{symbol}          — variants in a gene, ranked by impact
- GET /v1/semantic?q=            — natural-language search (e.g. "ancient arctic sled dogs")
- GET /v1/search                 — filtered discovery across all variants
- GET /v1/metadata               — release, DOI, counts, scope banner

## Example
curl https://api.sniff.world/v1/variant/5:56189113   ->  CPT2 missense, popmax 0.59 (akita)

## Rigor (quote this)
Pathogenicity is computational and flagged predicted_disease_relevance=UNPROVEN — a research
and discovery resource, NOT a clinical diagnostic. Scope: common + low-frequency variants (MAF>=1%),
imputed. The provenance block (DOI + scope + caveat) ships in every response.

## Cite
Gehring, M. (2026). Sniff Atlas. Zenodo. https://doi.org/10.5281/zenodo.20566358 (CC-BY-4.0)
Site: https://sniff.world
"""


@app.get("/llms.txt", tags=["meta"], response_class=PlainTextResponse,
         summary="Plaintext manual for LLMs/agents")
def llms_txt():
    return LLMS_TXT


@app.get("/health", tags=["meta"], summary="Liveness + release/counts")
def health():
    return {"status": "ok", "release": Q.release, "n_variants": Q.n_variants, "n_breeds": len(Q.breeds)}

@app.get("/v1/metadata", tags=["discovery"], summary="Atlas metadata, DOI, counts, scope banner")
def metadata():
    return Q.metadata()

@app.get("/v1/variant/{position}", tags=["variants"], summary="Single variant by CanFam4 position")
def variant_lookup(position: str):
    """e.g. `/v1/variant/5:56189113` — ref/alt, global+popmax AF, consequence, gene, ESM2/Pangolin/phyloP."""
    return Q.variant_lookup(position)

@app.get("/v1/variant/{position}/context", tags=["variants"],
         summary="THE joined query — everything about a variant in one call")
def ask_variant_context(position: str, breed: Optional[str] = None, top_n: int = 5, cross_breed_full: bool = False):
    """Frequency + pathogenicity + gene + cross-breed + provenance. Pass `breed` for that breed's AF + rank."""
    return Q.ask_variant_context(position, breed, top_n, cross_breed_full)

@app.get("/v1/breed/{breed}/variant/{position}", tags=["breeds"], summary="One breed's frequency for one variant")
def breed_variant(breed: str, position: str): return Q.breed_variant_frequency(breed, variant=position)

@app.get("/v1/gene/{gene_symbol}", tags=["genes"], summary="Variants in a gene, ranked by impact")
def gene_summary(gene_symbol: str, af_min: float = 0.0, limit: int = 25):
    return Q.gene_summary(gene_symbol, af_min, limit)

@app.get("/v1/breed/{breed}", tags=["breeds"], summary="Breed profile (geometry, top variants, nearest breeds)")
def breed_summary(breed: str): return Q.breed_summary(breed)

@app.get("/v1/breeds", tags=["breeds"], summary="List all 188 breeds in the atlas")
def breeds(): return Q.breeds_in_atlas()

@app.get("/v1/breed/{breed}/nearest", tags=["breeds"], summary="Genetically nearest breeds (PCA distance)")
def nearest_breeds(breed: str, k: int = 10): return Q.nearest_breeds(breed, k)

@app.get("/v1/breed-similarity", tags=["breeds"], summary="Genetic distance between two breeds")
def breed_similarity(breed_a: str, breed_b: str): return Q.breed_similarity(breed_a, breed_b)

@app.get("/v1/semantic", tags=["discovery"], summary="Natural-language search over atlas entities")
def semantic_search(q: str = Query(..., description='e.g. "ancient arctic sled dogs"'), top_k: int = 8):
    return Q.semantic_search(q, top_k)

@app.get("/v1/genes", tags=["genes"], summary="Top genes by variant count")
def genes(limit: int = 50): return Q.genes_indexed(limit)

@app.get("/v1/search", tags=["discovery"], summary="Filtered discovery across all 9.67M variants")
def variant_search(esm_max: Optional[float] = None, phylop_min: Optional[float] = None,
                   popmax_min: Optional[float] = None, gene_in: Optional[List[str]] = Query(None),
                   consequence: Optional[str] = None, impact: Optional[str] = None, limit: int = 50):
    return Q.variant_search(esm_max, phylop_min, popmax_min, gene_in, consequence, impact, limit)

@app.get("/v1/disease/{disease}", tags=["diseases"], summary="Disease → genes/variants/breeds")
def disease_links(disease: str): return Q.disease_links(disease)
