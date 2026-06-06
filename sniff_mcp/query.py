#!/usr/bin/env python3
"""Sniff MCP — query layer core. Structured-call-only (NL translation is Web's lane).
v1: ask_variant_context (the killer query) + variant_lookup, served from the packed
point store + in-RAM KG. Disease links: v1 has no public disease layer (OMIA held -> v1.1).
"""
import sqlite3, numpy as np, re, time

STORE = '/home/ubuntu/sniff-mcp/point_store.sqlite'
CONCEPT_DOI = '10.5281/zenodo.20566358'

class SniffQuery:
    def __init__(self, store=STORE):
        self.con = sqlite3.connect(store, check_same_thread=False)
        self.con.execute('PRAGMA mmap_size=8000000000')
        meta = dict(self.con.execute('SELECT k,v FROM meta').fetchall())
        self.breeds = meta['breed_order'].split('\t')
        self.release = meta['release']; self.assembly = meta['assembly']
        self.n_variants = int(meta['n_variants'])

    def _norm_pos(self, position):
        """Normalize CANFAM4:5:56189113 / chr5:56189113 / 5:56189113[:ref:alt] -> 'chr:pos'."""
        p = position.strip()
        p = re.sub(r'^canfam4:', '', p, flags=re.I)
        p = re.sub(r'^chr', '', p, flags=re.I)
        parts = p.split(':')
        return f'{parts[0]}:{parts[1]}'   # store key is chrom:pos

    def _provenance(self, row):
        dr2 = bool(row['low_dr2'])
        return {
            'data_release': self.release, 'dataset_doi': CONCEPT_DOI, 'assembly': self.assembly,
            'evidence_grade': 'Predicted', 'confounding_risk': 'LOW',
            'imputation_dr2_flag': dr2,
            'predicted_disease_relevance': 'UNPROVEN',
            'field_sources': {'af': 'breed_af', 'esm': 'esm2 (AUC 0.935 vs OMIA, n=115)'},
            'citation': f'Gehring M. (2026) Sniff Atlas. Zenodo. https://doi.org/{CONCEPT_DOI}. CC-BY-4.0',
            'scope_note': 'MAF>=1% (incl ~3M variants at 1-5%); imputed; predictions computational, not clinical.'
            + (' chr27/chr32 low-DR2 region.' if dr2 else '')
        }

    def _fetch(self, key):
        cur = self.con.execute('SELECT * FROM variants WHERE variant_id=?', (key,))
        names = [d[0] for d in cur.description]; r = cur.fetchone()
        return dict(zip(names, r)) if r else None

    def variant_lookup(self, position):
        row = self._fetch(self._norm_pos(position))
        if not row: return {'error': 'VARIANT_NOT_FOUND', 'note': 'not in resource (or below MAF>=1% floor)'}
        return {
            'variant_id': row['variant_id'], 'ref': row['ref'], 'alt': row['alt'],
            'global_af': row['alt_af'], 'popmax_af': row['popmax_af'], 'popmax_breed': row['popmax_breed'],
            'consequence': row['consequence'], 'impact': row['impact'],
            'gene': row['gene_name'], 'gene_id': row['gene_id'],
            'esm2_llr': row['esm_llr'], 'pangolin': row['pangolin'], 'phylop_241way': row['phylop'],
            'deleteriousness_tier': row['del_tier'],
            'canonical_url': f"https://sniff.world/variant/canfam4-{row['chrom']}-{row['pos']}/",
            'provenance': self._provenance(row),
        }

    def ask_variant_context(self, position, breed_context=None, top_n=5, cross_breed_full=False):
        row = self._fetch(self._norm_pos(position))
        if not row: return {'error': 'VARIANT_NOT_FOUND', 'note': 'not in resource (or below MAF>=1% floor)'}
        vec = np.frombuffer(row['breed_vec'], dtype=np.float16).astype(float)
        order = np.argsort(vec)[::-1]
        cross = [{'breed': self.breeds[i], 'af': round(float(vec[i]), 4)} for i in order[:top_n] if vec[i] > 0]
        out = {
            'variant': {'id': row['variant_id'], 'ref': row['ref'], 'alt': row['alt'],
                        'global_af': row['alt_af'], 'popmax_af': row['popmax_af'], 'popmax_breed': row['popmax_breed'],
                        'n_breeds_observed': row['n_breeds_observed'], 'imputation_dr2_flag': bool(row['low_dr2'])},
            'pathogenicity': {'esm2_llr': row['esm_llr'], 'esm2_calibration_auc': 0.935,
                              'pangolin_max': row['pangolin'], 'phylop_241way': row['phylop'],
                              'deleteriousness_tier': row['del_tier'], 'predicted_disease_relevance': 'UNPROVEN'},
            'gene': {'symbol': row['gene_name'], 'ncbi_or_ensembl_id': row['gene_id'],
                     'consequence': row['consequence'], 'impact': row['impact']},
            'diseases': [],  # v1: OMIA clinical layer held -> v1.1
            'cross_breed': (cross if not cross_breed_full
                            else [{'breed': self.breeds[i], 'af': round(float(vec[i]), 4)} for i in range(len(vec))]),
            'provenance': self._provenance(row),
            'deep_links': {'gene_page': f"https://sniff.world/gene/{(row['gene_name'] or '').lower()}/",
                           'variant_page': f"https://sniff.world/variant/canfam4-{row['chrom']}-{row['pos']}/"},
        }
        if breed_context:
            bc = breed_context.lower()
            if bc in self.breeds:
                af = float(vec[self.breeds.index(bc)])
                rank = int((vec > af).sum()) + 1
                out['in_breed'] = {'breed': bc, 'af': round(af, 4), 'rank_among_breeds': rank}
            else:
                out['in_breed'] = {'error': 'BREED_NOT_IN_ATLAS', 'breed': breed_context}
        return out


if __name__ == '__main__':
    import json
    q = SniffQuery()
    print(f'loaded store: {q.n_variants:,} variants, {len(q.breeds)} breeds, release {q.release}')
    # demo the killer query + time it
    for pos, breed in [('CANFAM4:28:7981160', 'cairn_terrier'), ('5:56189113', 'labrador_retriever')]:
        t = time.perf_counter()
        r = q.ask_variant_context(pos, breed_context=breed)
        dt = (time.perf_counter() - t) * 1000
        print(f'\n=== ask_variant_context({pos}, {breed}) — {dt:.2f} ms ===')
        print(json.dumps({k: r[k] for k in ['variant','pathogenicity','gene','in_breed','cross_breed']}, indent=1, default=str))
    # tight loop
    ids = [r[0] for r in q.con.execute('SELECT variant_id FROM variants ORDER BY RANDOM() LIMIT 1000')]
    t = time.perf_counter()
    for vid in ids: q.ask_variant_context(vid)
    print(f'\n>> 1000 full killer queries: {(time.perf_counter()-t)/len(ids)*1000:.3f} ms each mean')
