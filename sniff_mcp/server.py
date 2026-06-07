#!/usr/bin/env python3
"""Sniff MCP server — Streamable HTTP (MCP spec 2025-11-25), via FastMCP.

Exposes the Sniff Atlas query layer as MCP tools. Structured-call-only.
Run:  python -m sniff_mcp.server   (or `uvx sniff-mcp serve`)
Transport: streamable-http on 0.0.0.0:$PORT (default 8080), behind Cloudflare in prod.
"""
import os
from fastmcp import FastMCP
from .query import SniffQuery

INSTRUCTIONS = (
    "Sniff MCP — agent-callable canine genomics over the Sniff Atlas (open, CC-BY-4.0). "
    "Covers 9,667,790 common (MAF>=1%, incl ~3M at 1-5%) canine coding variants across 188 dog breeds "
    "on the CanFam4 assembly, with breed-stratified allele frequencies, calibrated ESM2 pathogenicity "
    "(AUC 0.935 vs OMIA), Pangolin splice, and Zoonomia phyloP conservation.\n\n"
    "IDENTIFIERS: positions are CanFam4 'chrom:pos' (e.g. '5:56189113' or 'CANFAM4:5:56189113' or 'chr5:56189113'). "
    "Assembly defaults to canfam4.\n"
    "START with `ask_variant_context` for a single variant — it returns frequency + pathogenicity + gene + "
    "cross-breed + provenance in one call. Use `variant_search` for filtered discovery, `gene_summary`/"
    "`breed_summary` for rollups, `metadata`/`breeds_in_atlas` for discovery.\n\n"
    "SAMPLE-SIZE CONFIDENCE: breed-level responses carry n_dogs, an af_ci95 (Wilson interval), and a "
    "confidence grade (high/moderate/low/very_low). The atlas is sample-skewed (median ~22 dogs/breed); "
    "an af of 0 in a 12-dog breed is NOT 'absent' (its CI may reach 0.10+). ALWAYS weight by confidence — "
    "do not report a frequency, a popmax, or a 'breed with the most/least X' claim without its n_dogs/CI.\n"
    "RIGOR CONTRACT: every response carries a provenance block (data DOI, evidence grade, citation). "
    "Pathogenicity outputs ALWAYS include predicted_disease_relevance='UNPROVEN' — these are computational "
    "predictions, NOT clinical diagnoses, and the resource is common-variant only (MAF>=1%). The OMIA disease "
    "layer ships in v1.1. Always surface the citation and the UNPROVEN caveat to the user."
)

mcp = FastMCP(name="Sniff", instructions=INSTRUCTIONS)
Q = SniffQuery()
_ = Q.kg  # pre-warm the in-RAM knowledge graph at startup so queries are always fast

@mcp.tool
def ask_variant_context(position: str, breed_context: str = "", top_n: int = 5,
                        cross_breed_full: bool = False) -> dict:
    """THE headline query. Given a CanFam4 position (e.g. '5:56189113'), return the variant's global +
    popmax frequency, breed-stratified cross-breed frequencies, ESM2/Pangolin/phyloP pathogenicity, gene
    context, linked diseases (v1.1), provenance, and deep links — in one call. Pass breed_context to also
    get that breed's AF + rank. cross_breed_full=True returns all 188 breeds (default: top_n)."""
    return Q.ask_variant_context(position, breed_context or None, top_n, cross_breed_full)

@mcp.tool
def variant_lookup(position: str) -> dict:
    """Single-variant lookup by CanFam4 position: ref/alt, global + popmax AF, consequence, gene,
    ESM2/Pangolin/phyloP, deleteriousness tier, canonical URL, provenance."""
    return Q.variant_lookup(position)

@mcp.tool
def breed_variant_frequency(breed: str, variant: str = "", gene: str = "") -> dict:
    """Breed-stratified allele frequency. Give a breed (e.g. 'bernese_mountain_dog') plus either a
    variant position or a gene symbol. Returns AF (+ rank) for the variant, or per-variant AFs in the gene."""
    return Q.breed_variant_frequency(breed, variant or None, gene or None)

@mcp.tool
def gene_summary(gene_symbol: str, af_min: float = 0.0, limit: int = 25) -> dict:
    """Variants in a gene (by gene symbol), ranked by impact then ESM2 damage. Paginated (limit, default 25);
    returns total_variants. Use af_min to filter by global AF."""
    return Q.gene_summary(gene_symbol, af_min, limit)

@mcp.tool
def breed_summary(breed: str) -> dict:
    """Breed profile: top damaging common variants (ESM2<=-5 & breed AF>=5%), n_dogs, breed group.
    Descriptive only — not a health ranking."""
    return Q.breed_summary(breed)

@mcp.tool
def variant_search(esm_max: float = None, phylop_min: float = None, popmax_min: float = None,
                   gene_in: list[str] = None, consequence: str = "", impact: str = "",
                   limit: int = 50) -> dict:
    """Filtered discovery over all 9.67M variants. Predicates (combine freely): esm_max (ESM2 LLR <=),
    phylop_min (phyloP >=), popmax_min (popmax AF >=), gene_in (list of gene symbols), consequence,
    impact (HIGH/MODERATE/LOW/MODIFIER). Returns total_count + a capped list (max 200). Note: popmax may
    be in a wild population (dingo/village) — check popmax_breed."""
    return Q.variant_search(esm_max, phylop_min, popmax_min, gene_in, consequence or None, impact or None, limit)

@mcp.tool
def nearest_breeds(breed: str, k: int = 10) -> dict:
    """Genetically nearest breeds to the given breed (top-10-PC Euclidean in canine genetic space).
    Answers 'what breeds are most genetically similar to X?' via the PCA-256 breed co-embedding."""
    return Q.nearest_breeds(breed, k)

@mcp.tool
def breed_similarity(breed_a: str, breed_b: str) -> dict:
    """Genetic distance between two breeds (top-10-PC Euclidean). Lower = more genetically similar."""
    return Q.breed_similarity(breed_a, breed_b)

@mcp.tool
def semantic_search(query: str, top_k: int = 8, entity_type: str = "", filters: str = "") -> dict:
    """Faceted hybrid + semantic-ranker search over the whole knowledge base (diseases, breeds, Scout
    discoveries). Use for fuzzy/thematic intent ('drug sensitivity in herding dogs', 'breeds prone to eye
    disease', 'genetically diverse breeds'). entity_type filters to 'disease'|'breed'|'discovery'. filters
    is an OData facet expression for cross-dimension queries, e.g. "breed_group eq 'herding' and cohort_n ge 30"
    or "diversity_tier eq 'severe_bottleneck'" (facets: type, breed, breed_group, gene, evidence_tier,
    confidence_tier, diversity_tier, cohort_n). Returns ranked entities with snippets, dimension fields, links."""
    return Q.semantic_search(query, top_k, entity_type or None, filters or None)

@mcp.tool
def disease_links(disease: str = "") -> dict:
    """Disease -> genes/variants/breeds. NOTE: the v1 public release is OMIA-free; the disease/clinical
    layer ships in v1.1. For now use gene/variant/breed RPCs."""
    return Q.disease_links(disease or None)

@mcp.tool
def breeds_in_atlas() -> dict:
    """List all 188 breeds with breed-stratified frequencies in the atlas."""
    return Q.breeds_in_atlas()

@mcp.tool
def genes_indexed(limit: int = 50) -> dict:
    """Top genes by number of variants in the atlas (discovery aid)."""
    return Q.genes_indexed(limit)

@mcp.tool
def metadata() -> dict:
    """Atlas metadata: release, DOI, assembly, variant/breed counts, scope banner, and the RPC catalog."""
    return Q.metadata()


def main():
    port = int(os.environ.get("PORT", "8080"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
