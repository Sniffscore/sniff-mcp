#!/usr/bin/env python3
"""Sniff MCP — query layer (structured-call-only; NL translation is the Web lane).

Implements the FUNCTION_SURFACE.md contract. Hot path = packed point store (mmap'd
SQLite, 188-breed float16 vectors); filter/range tail = DuckDB over local parquet;
KG = in-RAM. Every response carries the provenance+confidence block, including
predicted_disease_relevance=UNPROVEN on pathogenicity output.

Data paths are dev defaults; at deploy they are pulled to local NVMe (R2 = distribution).
"""
import sqlite3, numpy as np, re, json, os

STORE   = os.environ.get('SNIFF_STORE',  '/home/ubuntu/sniff-mcp/point_store.sqlite')
MASTER  = os.environ.get('SNIFF_MASTER', '/home/ubuntu/canvas-zenodo/canvas_variant_master.parquet')
BREEDAF = os.environ.get('SNIFF_BREEDAF','/home/ubuntu/canvas-zenodo/canvas_breed_af.parquet')
KGDIR   = os.environ.get('SNIFF_KGDIR',  '/home/ubuntu/sniff-atlas-v1.0.1/knowledge_graph')
BREEDDIM= os.environ.get('SNIFF_BREEDDIM','/home/ubuntu/sniff-research/mamba-experiments/dimensions/breed_dimensions.json')
CONCEPT_DOI = '10.5281/zenodo.20566358'


class SniffQuery:
    def __init__(self):
        self.con = sqlite3.connect(STORE, check_same_thread=False)
        self.con.row_factory = sqlite3.Row
        self.con.execute('PRAGMA mmap_size=8000000000')
        meta = dict(self.con.execute('SELECT k,v FROM meta').fetchall())
        self.breeds = meta['breed_order'].split('\t'); self.breed_set = set(self.breeds)
        self.release = meta['release']; self.assembly = meta['assembly']; self.n_variants = int(meta['n_variants'])
        self._duck = None; self._kg = None; self._bdim = None

    # ---- lazy backends -------------------------------------------------------
    @property
    def duck(self):
        if self._duck is None:
            import duckdb
            self._duck = duckdb.connect(':memory:')
            self._duck.execute(f"CREATE VIEW m AS SELECT * FROM read_parquet('{MASTER}')")
        return self._duck

    @property
    def bdim(self):
        if self._bdim is None:
            try:
                self._bdim = {b['breed']: b for b in json.load(open(BREEDDIM))['breeds']}
            except Exception:
                self._bdim = {}
        return self._bdim

    @property
    def kg(self):
        if self._kg is None:
            self._kg = self._load_kg()
        return self._kg

    def _load_kg(self):
        import pyarrow.parquet as pq
        kg = {'nodes': {}, 'var_to_disease': {}}
        try:
            n = pq.read_table(f'{KGDIR}/nodes.parquet').to_pandas()
            kg['nodes'] = {r['id']: {'name': r.get('name'), 'category': r.get('category')} for _, r in n.iterrows()}
            e = pq.read_table(f'{KGDIR}/edges.parquet').to_pandas()
            for _, r in e[e.predicate == 'biolink:causes'].iterrows():
                kg['var_to_disease'].setdefault(r['subject'], []).append(r['object'])
        except Exception:
            pass  # public v1 KG is OMIA-free -> no disease nodes/edges; disease_links returns the v1.1 note
        return kg

    # ---- helpers -------------------------------------------------------------
    def _norm(self, position):
        p = re.sub(r'^canfam4:', '', position.strip(), flags=re.I)
        p = re.sub(r'^chr', '', p, flags=re.I)
        parts = p.split(':')
        return f'{parts[0]}:{parts[1]}'

    def _prov(self, dr2=False, grade='Predicted'):
        return {'data_release': self.release, 'dataset_doi': CONCEPT_DOI, 'assembly': self.assembly,
                'evidence_grade': grade, 'confounding_risk': 'LOW', 'imputation_dr2_flag': bool(dr2),
                'predicted_disease_relevance': 'UNPROVEN',
                'field_sources': {'af': 'breed_af', 'esm': 'esm2 (AUC 0.935 vs OMIA, n=115)'},
                'citation': f'Gehring M. (2026) Sniff Atlas. Zenodo. https://doi.org/{CONCEPT_DOI}. CC-BY-4.0',
                'scope_note': 'MAF>=1% (incl ~3M variants at 1-5%); imputed; predictions computational, not clinical.'
                + (' chr27/chr32 low-DR2 region.' if dr2 else '')}

    def _row(self, key):
        r = self.con.execute('SELECT * FROM variants WHERE variant_id=?', (key,)).fetchone()
        return dict(r) if r else None

    def _vurl(self, row): return f"https://sniff.world/variant/canfam4-{row['chrom']}-{row['pos']}/"

    # ---- RPCs ----------------------------------------------------------------
    def metadata(self):
        return {'name': 'Sniff MCP', 'data_release': self.release, 'dataset_doi': CONCEPT_DOI,
                'assembly': self.assembly, 'n_variants': self.n_variants, 'n_breeds': len(self.breeds),
                'scope_banner': ('Sniff Atlas: 9,667,790 common (MAF>=1%, incl ~3M at 1-5%) canine coding '
                                 'variants x 188 breeds (CanFam4). Calibrated ESM2 pathogenicity (AUC 0.935 vs '
                                 'OMIA), Pangolin, phyloP. Predictions are computational; disease relevance '
                                 'UNPROVEN. OMIA clinical layer ships v1.1.'),
                'rpcs': ['ask_variant_context', 'variant_lookup', 'breed_variant_frequency', 'gene_summary',
                         'breed_summary', 'disease_links', 'variant_search', 'breeds_in_atlas', 'genes_indexed',
                         'metadata']}

    def breeds_in_atlas(self):
        return {'n_breeds': len(self.breeds), 'breeds': self.breeds}

    def genes_indexed(self, limit=50):
        rows = self.duck.execute(
            "SELECT gene_name, count(*) n FROM m WHERE gene_name IS NOT NULL GROUP BY gene_name ORDER BY n DESC LIMIT ?",
            [limit]).fetchall()
        return {'top_genes_by_variant_count': [{'gene': g, 'n_variants': n} for g, n in rows]}

    def variant_lookup(self, position):
        row = self._row(self._norm(position))
        if not row:
            return {'error': 'VARIANT_NOT_FOUND', 'note': 'not in resource (or below MAF>=1% floor)'}
        return {'variant_id': row['variant_id'], 'ref': row['ref'], 'alt': row['alt'], 'global_af': row['alt_af'],
                'popmax_af': row['popmax_af'], 'popmax_breed': row['popmax_breed'],
                'consequence': row['consequence'], 'impact': row['impact'], 'gene': row['gene_name'],
                'gene_id': row['gene_id'], 'esm2_llr': row['esm_llr'], 'pangolin': row['pangolin'],
                'phylop_241way': row['phylop'], 'deleteriousness_tier': row['del_tier'],
                'canonical_url': self._vurl(row), 'provenance': self._prov(row['low_dr2'])}

    def ask_variant_context(self, position, breed_context=None, top_n=5, cross_breed_full=False):
        row = self._row(self._norm(position))
        if not row:
            return {'error': 'VARIANT_NOT_FOUND', 'note': 'not in resource (or below MAF>=1% floor)'}
        vec = np.frombuffer(row['breed_vec'], dtype=np.float16).astype(float)
        order = np.argsort(vec)[::-1]
        cross = ([{'breed': self.breeds[i], 'af': round(float(vec[i]), 4)} for i in range(len(vec))]
                 if cross_breed_full else
                 [{'breed': self.breeds[i], 'af': round(float(vec[i]), 4)} for i in order[:top_n] if vec[i] > 0])
        dz = self.kg['var_to_disease'].get(f"CANFAM4:{row['variant_id']}", [])
        out = {'variant': {'id': row['variant_id'], 'ref': row['ref'], 'alt': row['alt'], 'global_af': row['alt_af'],
                           'popmax_af': row['popmax_af'], 'popmax_breed': row['popmax_breed'],
                           'n_breeds_observed': row['n_breeds_observed'], 'imputation_dr2_flag': bool(row['low_dr2'])},
               'pathogenicity': {'esm2_llr': row['esm_llr'], 'esm2_calibration_auc': 0.935,
                                 'pangolin_max': row['pangolin'], 'phylop_241way': row['phylop'],
                                 'deleteriousness_tier': row['del_tier'], 'predicted_disease_relevance': 'UNPROVEN'},
               'gene': {'symbol': row['gene_name'], 'id': row['gene_id'], 'consequence': row['consequence'],
                        'impact': row['impact']},
               'diseases': ([{'id': d, 'name': self.kg['nodes'].get(d, {}).get('name')} for d in dz] if dz
                            else {'note': 'No disease layer in v1 (OMIA clinical integration ships v1.1).'}),
               'cross_breed': cross,
               'provenance': self._prov(row['low_dr2']),
               'deep_links': {'gene_page': f"https://sniff.world/gene/{(row['gene_name'] or '').lower()}/",
                              'variant_page': self._vurl(row)}}
        if breed_context:
            bc = breed_context.lower()
            if bc in self.breed_set:
                af = float(vec[self.breeds.index(bc)]); rank = int((vec > af).sum()) + 1
                out['in_breed'] = {'breed': bc, 'af': round(af, 4), 'rank_among_breeds': rank}
            else:
                out['in_breed'] = {'error': 'BREED_NOT_IN_ATLAS', 'breed': breed_context}
        return out

    def breed_variant_frequency(self, breed, variant=None, gene=None):
        bc = breed.lower()
        if bc not in self.breed_set:
            return {'error': 'BREED_NOT_IN_ATLAS', 'breed': breed, 'n_breeds': len(self.breeds)}
        if variant:
            row = self._row(self._norm(variant))
            if not row:
                return {'error': 'VARIANT_NOT_FOUND'}
            vec = np.frombuffer(row['breed_vec'], dtype=np.float16).astype(float)
            af = float(vec[self.breeds.index(bc)])
            return {'breed': bc, 'variant_id': row['variant_id'], 'af': round(af, 4),
                    'rank_among_breeds': int((vec > af).sum()) + 1, 'provenance': self._prov(row['low_dr2'])}
        if gene:
            q = '"' + bc + '"'
            rows = self.duck.execute(
                f"SELECT b.variant_id, b.{q} af, m.consequence, m.impact, m.esm_llr "
                f"FROM read_parquet('{BREEDAF}') b JOIN m USING(variant_id) "
                f"WHERE m.gene_name=? AND b.{q}>0 ORDER BY b.{q} DESC LIMIT 50", [gene]).fetchall()
            return {'breed': bc, 'gene': gene,
                    'variants': [{'variant_id': v, 'af': round(af, 4), 'consequence': c, 'impact': im, 'esm2_llr': e}
                                 for v, af, c, im, e in rows], 'provenance': self._prov()}
        return {'error': 'NEED_VARIANT_OR_GENE'}

    def gene_summary(self, gene_symbol, af_min=0.0, limit=25):
        total = self.duck.execute("SELECT count(*) FROM m WHERE gene_name=?", [gene_symbol]).fetchone()[0]
        if total == 0:
            return {'error': 'AMBIGUOUS_GENE', 'note': f'no variants for gene_name={gene_symbol}'}
        rows = self.duck.execute(
            "SELECT variant_id, alt_af, popmax_af, popmax_breed, consequence, impact, esm_llr, phyloP_241way "
            "FROM m WHERE gene_name=? AND alt_af>=? ORDER BY (impact='HIGH') DESC, esm_llr ASC NULLS LAST LIMIT ?",
            [gene_symbol, af_min, limit]).fetchall()
        return {'gene': gene_symbol, 'total_variants': total, 'returned': len(rows),
                'variants': [{'variant_id': v, 'global_af': af, 'popmax_af': pm, 'popmax_breed': pb,
                              'consequence': c, 'impact': im, 'esm2_llr': e, 'phylop_241way': php}
                             for v, af, pm, pb, c, im, e, php in rows],
                'provenance': self._prov()}

    def breed_summary(self, breed):
        bc = breed.lower()
        if bc not in self.breed_set:
            return {'error': 'BREED_NOT_IN_ATLAS', 'breed': breed}
        q = '"' + bc + '"'
        top = self.duck.execute(
            f"SELECT b.variant_id, b.{q} af, m.gene_name, m.consequence, m.esm_llr "
            f"FROM read_parquet('{BREEDAF}') b JOIN m USING(variant_id) "
            f"WHERE m.esm_llr<=-5 AND b.{q}>=0.05 ORDER BY b.{q} DESC LIMIT 20", []).fetchall()
        bd = self.bdim.get(bc, {})
        return {'breed': bc, 'n_dogs': bd.get('n_dogs'), 'breed_group': bd.get('breed_group'),
                'top_damaging_common_variants': [{'variant_id': v, 'af': round(af, 4), 'gene': g,
                                                  'consequence': c, 'esm2_llr': e} for v, af, g, c, e in top],
                'note': 'Descriptive (damaging = ESM2<=-5 & breed AF>=5%); not a health ranking. Disease layer v1.1.',
                'provenance': self._prov()}

    def disease_links(self, disease=None):
        if not self.kg['nodes']:
            return {'note': 'No disease layer in the v1 public release (OMIA clinical integration ships v1.1).',
                    'available_now': 'variant->gene + breed carrier frequencies via the other RPCs.'}
        return {'note': 'Disease layer ships v1.1.'}

    def variant_search(self, esm_max=None, phylop_min=None, popmax_min=None, gene_in=None,
                       consequence=None, impact=None, limit=50):
        w, p = [], []
        if esm_max is not None: w.append('esm_llr<=?'); p.append(esm_max)
        if phylop_min is not None: w.append('phyloP_241way>=?'); p.append(phylop_min)
        if popmax_min is not None: w.append('popmax_af>=?'); p.append(popmax_min)
        if consequence: w.append('consequence=?'); p.append(consequence)
        if impact: w.append('impact=?'); p.append(impact)
        if gene_in: w.append('gene_name IN (' + ','.join('?' * len(gene_in)) + ')'); p += list(gene_in)
        if not w:
            return {'error': 'NO_FILTERS', 'note': 'provide at least one predicate'}
        where = ' AND '.join(w)
        total = self.duck.execute(f"SELECT count(*) FROM m WHERE {where}", p).fetchone()[0]
        rows = self.duck.execute(
            f"SELECT variant_id, gene_name, alt_af, popmax_af, popmax_breed, consequence, impact, esm_llr, phyloP_241way "
            f"FROM m WHERE {where} ORDER BY esm_llr ASC NULLS LAST LIMIT ?", p + [min(limit, 200)]).fetchall()
        return {'total_count': total, 'returned': len(rows),
                'variants': [{'variant_id': v, 'gene': g, 'global_af': af, 'popmax_af': pm, 'popmax_breed': pb,
                              'consequence': c, 'impact': im, 'esm2_llr': e, 'phylop_241way': php}
                             for v, g, af, pm, pb, c, im, e, php in rows],
                'provenance': self._prov()}
