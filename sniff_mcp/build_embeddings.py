#!/usr/bin/env python3
"""Build the semantic index (v1.1). Synthesize entity blurbs -> embed (fastembed, ONNX) ->
save a tiny brute-force index (npz). v1.1 corpus = breeds (rich attributes). Extensible:
add genes/diseases blurbs here as their text corpus arrives (no re-architecture)."""
import json, os, numpy as np
DIM = os.environ.get('SNIFF_BREEDDIM', '/home/ubuntu/sniff-research/mamba-experiments/dimensions/breed_dimensions.json')
OUT = os.environ.get('SNIFF_EMB', '/home/ubuntu/sniff-mcp/semantic_index.npz')
MODEL = "BAAI/bge-small-en-v1.5"

def size_word(kg):
    if kg is None: return ""
    return ("toy/small" if kg < 10 else "medium" if kg < 25 else "large" if kg < 45 else "giant") + f" (~{round(kg)}kg)"

def breed_blurb(b):
    name = b['breed'].replace('_', ' ')
    parts = [f"{name}.", f"{b.get('breed_group','')} group." if b.get('breed_group') else ""]
    if b.get('breed_weight_kg'): parts.append(f"Size: {size_word(b['breed_weight_kg'])}.")
    if b.get('median_lifespan_years'): parts.append(f"Median lifespan {b['median_lifespan_years']} years.")
    h = b.get('mean_heterozygosity')
    if h is not None: parts.append(f"Genetic diversity {'low (inbred)' if h < 0.30 else 'high' if h > 0.36 else 'moderate'} (heterozygosity {h}).")
    if (b.get('isolation_index') or 0) > 40: parts.append("Genetically isolated.")
    if b.get('breed_age_proxy_nearest_wild'): parts.append(f"Closest wild canid: {b['breed_age_proxy_nearest_wild'].replace('_',' ')}.")
    nn = [x['breed'].replace('_', ' ') for x in (b.get('nearest_5_breeds') or [])[:4]]
    if nn: parts.append("Genetically similar to " + ", ".join(nn) + ".")
    return " ".join(p for p in parts if p)

def main():
    from fastembed import TextEmbedding
    breeds = json.load(open(DIM))['breeds']
    items = [{"id": b['breed'], "type": "breed", "blurb": breed_blurb(b),
              "url": f"https://sniff.world/breed/{b['breed'].replace('_','-')}/"} for b in breeds]
    model = TextEmbedding(MODEL)
    vecs = np.array(list(model.embed([it['blurb'] for it in items]))).astype(np.float32)
    vecs /= (np.linalg.norm(vecs, axis=1, keepdims=True) + 1e-9)  # normalize for cosine
    np.savez(OUT, vecs=vecs, ids=[it['id'] for it in items], types=[it['type'] for it in items],
             blurbs=[it['blurb'] for it in items], urls=[it['url'] for it in items], model=MODEL)
    print(f"semantic index: {len(items)} entities ({vecs.shape[1]}-d), model {MODEL} -> {OUT}")

if __name__ == "__main__":
    main()
