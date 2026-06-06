#!/usr/bin/env python3
"""Sniff REST API (api.sniff.world/v1) — thin HTTP surface over the SAME query layer as the MCP.
Run: uvicorn sniff_mcp.rest:app  (Cloudflare in front for cache/rate-limit/WAF in prod).
"""
from fastapi import FastAPI, Query
from typing import Optional, List
from .query import SniffQuery

app = FastAPI(title="Sniff API", version="v1",
              description="Agent- and developer-callable canine genomics over the Sniff Atlas. "
                          "Same query layer as the MCP. Every response carries provenance + the UNPROVEN caveat. "
                          "Dataset: https://doi.org/10.5281/zenodo.20566358 (CC-BY-4.0).")
Q = SniffQuery()
_ = Q.kg  # pre-warm KG at startup

@app.get("/health")
def health(): return {"status": "ok", "release": Q.release, "n_variants": Q.n_variants, "n_breeds": len(Q.breeds)}

@app.get("/v1/metadata")
def metadata(): return Q.metadata()

@app.get("/v1/variant/{position}")
def variant_lookup(position: str): return Q.variant_lookup(position)

@app.get("/v1/variant/{position}/context")
def ask_variant_context(position: str, breed: Optional[str] = None, top_n: int = 5, cross_breed_full: bool = False):
    return Q.ask_variant_context(position, breed, top_n, cross_breed_full)

@app.get("/v1/breed/{breed}/variant/{position}")
def breed_variant(breed: str, position: str): return Q.breed_variant_frequency(breed, variant=position)

@app.get("/v1/gene/{gene_symbol}")
def gene_summary(gene_symbol: str, af_min: float = 0.0, limit: int = 25):
    return Q.gene_summary(gene_symbol, af_min, limit)

@app.get("/v1/breed/{breed}")
def breed_summary(breed: str): return Q.breed_summary(breed)

@app.get("/v1/breeds")
def breeds(): return Q.breeds_in_atlas()

@app.get("/v1/breed/{breed}/nearest")
def nearest_breeds(breed: str, k: int = 10): return Q.nearest_breeds(breed, k)

@app.get("/v1/breed-similarity")
def breed_similarity(breed_a: str, breed_b: str): return Q.breed_similarity(breed_a, breed_b)

@app.get("/v1/semantic")
def semantic_search(q: str, top_k: int = 8): return Q.semantic_search(q, top_k)

@app.get("/v1/genes")
def genes(limit: int = 50): return Q.genes_indexed(limit)

@app.get("/v1/search")
def variant_search(esm_max: Optional[float] = None, phylop_min: Optional[float] = None,
                   popmax_min: Optional[float] = None, gene_in: Optional[List[str]] = Query(None),
                   consequence: Optional[str] = None, impact: Optional[str] = None, limit: int = 50):
    return Q.variant_search(esm_max, phylop_min, popmax_min, gene_in, consequence, impact, limit)

@app.get("/v1/disease/{disease}")
def disease_links(disease: str): return Q.disease_links(disease)
