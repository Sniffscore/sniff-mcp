#!/usr/bin/env python3
"""Sniff MCP server — Streamable HTTP (MCP spec 2025-11-25), via FastMCP.

Exposes the Sniff Atlas query layer as MCP tools. Structured-call-only.
Run:  python -m sniff_mcp.server   (or `uvx sniff-mcp serve`)
Transport: streamable-http on 0.0.0.0:$PORT (default 8080), behind Cloudflare in prod.
"""
import os, json, urllib.request, urllib.error
from fastmcp import FastMCP
from .query import SniffQuery

BRAIN_URL = os.environ.get("SNIFF_BRAIN_URL", "https://brain.sniff.world")

INSTRUCTIONS = (
    "Sniff MCP — agent-callable canine genomics over the Sniff Atlas (open, CC-BY-4.0). "
    "Covers 9,667,790 common (MAF>=1%, incl ~3M at 1-5%) canine coding variants across 188 dog breeds "
    "on the CanFam4 assembly, with breed-stratified allele frequencies, calibrated ESM2 pathogenicity "
    "(AUC 0.935 vs OMIA), Pangolin splice, and Zoonomia phyloP conservation.\n\n"
    "IDENTIFIERS: positions are CanFam4 'chrom:pos' (e.g. '5:56189113' or 'CANFAM4:5:56189113' or 'chr5:56189113'). "
    "Assembly defaults to canfam4.\n"
    "START: for a natural-language question ('what is X', 'does breed Y get Z', 'human equivalent of W'), "
    "call `ask` — it returns a GROUNDED, CITED answer (or an honest abstain) over the fused knowledge layer "
    "(OMIA inherited diseases + dog<->human homolog bridge, AVCG variant pathogenicity grades, carrier risk, "
    "longevity, temperament, diversity). For the documented-disease atoms of a breed or disease, call "
    "`disease_bridge`. For a single variant, `ask_variant_context` returns frequency + pathogenicity + gene + "
    "cross-breed + provenance in one call. Use `variant_search` for filtered discovery, `gene_summary`/"
    "`breed_summary` for rollups, `metadata`/`breeds_in_atlas` for discovery.\n\n"
    "SAMPLE-SIZE CONFIDENCE: breed-level responses carry n_dogs, an af_ci95 (Wilson interval), and a "
    "confidence grade (high/moderate/low/very_low). The atlas is sample-skewed (median ~22 dogs/breed); "
    "an af of 0 in a 12-dog breed is NOT 'absent' (its CI may reach 0.10+). ALWAYS weight by confidence — "
    "do not report a frequency, a popmax, or a 'breed with the most/least X' claim without its n_dogs/CI.\n"
    "RIGOR CONTRACT: every response carries a provenance block (data DOI, evidence grade, citation). "
    "Pathogenicity outputs ALWAYS include predicted_disease_relevance='UNPROVEN' — these are computational "
    "predictions, NOT clinical diagnoses, and the resource is common-variant only (MAF>=1%). The OMIA disease "
    "layer + grounded `ask` are LIVE (cite-or-abstain; carrier != affected; educational, not diagnostic). "
    "Always surface the citation and the UNPROVEN caveat to the user."
)

mcp = FastMCP(name="Sniff", instructions=INSTRUCTIONS)
Q = SniffQuery()
_ = Q.kg  # pre-warm the in-RAM knowledge graph at startup so queries are always fast

def _brain(path: str, payload: dict = None, timeout: int = 45) -> dict:
    """Thin client to the Sniff brain (grounded reasoning seam). GET if no payload, else POST JSON."""
    url = f"{BRAIN_URL}{path}"
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"User-Agent": "sniff-mcp"}   # Cloudflare 403s the default urllib UA
    if data: headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
        return {"error": f"brain unavailable: {e}", "answer": None}

@mcp.tool
def ask(question: str) -> dict:
    """Ask Sniff a natural-language canine-genetics question and get a GROUNDED, CITED answer (or an honest
    abstain). Covers inherited diseases (OMIA) and their human homologs (the dog<->human disease bridge),
    breed disease/carrier risk, variant pathogenicity grades (AVCG; Boeykens et al. 2024, curated in OMIA),
    longevity/life-expectancy (McMillan 2024), temperament (Darwin's Ark/Morrill 2022, with breed-explains-X%
    caveats), and genetic diversity. The engine answers ONLY from cited Sniff atoms and returns
    `abstained: true` if it lacks grounded data — it never guesses. Educational, not diagnostic
    (carrier != affected; advise a vet). Returns {answer, citations:[atom_ids], abstained}. USE THIS for any
    'what is X / does breed Y get Z / human equivalent of W' question; use the variant/breed/gene tools for
    structured lookups by identifier."""
    r = _brain("/v1/ask", {"question": question})
    if r.get("answer") is None:
        return {"error": r.get("error", "brain unavailable"), "answer": None, "abstained": None, "citations": []}
    return {"answer": r["answer"], "citations": r.get("citations", []), "abstained": r.get("abstained"),
            "provenance": {"engine": "sniff-brain (grounded RAG)", "contract": "cite-or-abstain",
                           "sources": "OMIA, AVCG/Boeykens 2024, Donner 2023, McMillan 2024, Morrill 2022",
                           "note": "educational, not diagnostic; carrier is not affected"}}

@mcp.tool
def disease_bridge(disease: str = "", breed: str = "") -> dict:
    """The fused OMIA disease layer as cited atoms. Give a `disease` (name or 'OMIA:001870-9615') for its
    genes, inheritance, human homolog (OMIM/Mondo bridge), and variant pathogenicity grade (AVCG, ACMG/AMP
    5-tier, curated in OMIA) when graded. Or give a `breed` (e.g. 'doberman_pinscher') for the inherited
    conditions documented in that breed with carrier frequency + confidence tier + grade. Every atom carries
    its source + atom_id. Educational, not diagnostic."""
    if breed:
        r = _brain(f"/v1/atoms?entity=breed:{urllib.request.quote(breed)}&claim=HEALTH_CARRIER")
    elif disease:
        eid = disease if disease.upper().startswith("OMIA:") else disease
        r = _brain(f"/v1/atoms?entity=disease:{urllib.request.quote(eid)}")
    else:
        return {"error": "provide a disease (name or OMIA id) or a breed"}
    return r if "error" in r else {"atoms": r.get("atoms", []), "count": len(r.get("atoms", [])),
                                   "provenance": {"source": "OMIA + AVCG (Boeykens 2024) + Donner 2023",
                                                  "note": "documented in OMIA; educational, not diagnostic"}}

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
    """A canine inherited disease (name or OMIA id) -> its governed OMIA clinical record: mode of inheritance,
    causal gene(s), curated description (summary / clinical features / molecular genetics / pathology /
    prevalence), clinical signs as HP/MP phenotype terms (-> Monarch), the human OMIM analog + Mondo id, and
    the evidence base (peer-reviewed reference count + landmark study) -- plus molecular links (variants/breeds)
    when the KG carries them. Sourced to OMIA (CC-BY); returns a canonical sniff.world URL. Dog-only.
    Educational, not diagnostic. For fuzzy candidates use search_diseases."""
    return Q.disease_links(disease or None)

@mcp.tool
def disease_lookup(query: str) -> dict:
    """Look up a canine inherited disease by name or OMIA id -> its governed OMIA clinical record (inheritance,
    causal gene(s), curated description, clinical signs, human OMIM analog + Mondo id, evidence base). Sourced
    to OMIA (CC-BY); returns a canonical sniff.world URL. Dog-only. For candidate disambiguation use
    search_diseases; for a disease's molecular links use disease_links."""
    return Q.disease_lookup(query or None)

@mcp.tool
def search_diseases(query: str, limit: int = 10) -> dict:
    """Search the canine disease catalogue by free text -> ranked candidates [{omia_id, disease, url, score}].
    Use before disease_lookup when the exact name is unknown. Dog-only."""
    return Q.search_diseases(query or None, limit)

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


def _assert_tool_catalog():
    """Anti-drift gate: the live registered MCP tool surface MUST equal metadata's catalog
    (query.TOOL_CATALOG, which also drives /v1/metadata rpcs and the generated llms.txt). Adding an
    @mcp.tool without updating TOOL_CATALOG (or vice-versa) fails startup — verified in isolation before deploy."""
    import asyncio, sys
    try:
        registered = {t.name for t in asyncio.run(mcp.list_tools())}
    except Exception as e:
        sys.stderr.write(f"[gate] WARN: could not enumerate MCP tools ({e}); skipping catalog check\n")
        return
    catalog = set(Q.metadata()["rpcs"])
    if registered != catalog:
        raise RuntimeError(
            "[gate] MCP tool surface != metadata catalog (query.TOOL_CATALOG). "
            f"in catalog, not registered: {sorted(catalog - registered)}; "
            f"registered, not in catalog: {sorted(registered - catalog)}")
    sys.stderr.write(f"[gate] OK: {len(catalog)} tools; MCP surface == metadata catalog == llms.txt\n")

def main():
    _assert_tool_catalog()
    port = int(os.environ.get("PORT", "8080"))
    mcp.run(transport="streamable-http", host="0.0.0.0", port=port)

if __name__ == "__main__":
    main()
