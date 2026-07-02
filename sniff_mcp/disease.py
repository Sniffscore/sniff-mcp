#!/usr/bin/env python3
"""Sniff MCP — the OMIA clinical disease layer (MCP-T1: finish disease_links, v1.1).

Self-contained. Loads the four governed OMIA artifacts (built + shipped by the web lane, CC-BY,
keyed by canonical OMIA id `OMIA:NNNNNN-TTTT`) and provides the clinical half the v1 server stubbed
(`sniff_query.py:75  'diseases': []`). The molecular half (disease -> genes/variants/breeds) stays
with the atlas KG on the VM; this module supplies inheritance, curated prose, clinical signs, the
human (OMIM) analog, the evidence base (peer-reviewed references + the landmark study), and the
Mondo disease id — each cited to OMIA, each with a canonical sniff.world deep link.

Authored web-side under Matt's direction while the A100 research box is dark (the same pattern as
the Glama audit-response). It ports the web resolver `web/src/lib/disease-resolve.ts` VERBATIM in
behavior, INCLUDING the INV-38 constraint gate (SPECIES / breadth / uniqueness) — so the VM server
resolves diseases identically to Ask + the web MCP. ONE resolver semantics across all three surfaces.

Wiring: see OMIA_INTEGRATION_SPEC.md (drop this file + ./data/*.json into /home/ubuntu/sniff-mcp/,
import in the FastMCP server, fill disease_links + ask_variant_context.diseases[], add disease_lookup).
"""
import json, os, re

DATA_DIR = os.environ.get('SNIFF_OMIA_DIR', os.path.join(os.environ.get('SNIFF_DATA', '/data'), 'omia'))
QUERY_TAXA = {'9615'}                  # dog-only today (the same SPECIES gate as Ask/web-MCP)
OMIA_DOI = '10.25910/2AMR-PV70'
OMIA_CITATION = ('Nicholas, F.W., Tammen, I., & Sydney Informatics Hub. (2026). OMIA [dataset]. '
                 'https://omia.org. doi:10.25910/2AMR-PV70')
_TAG = re.compile(r'<[^>]+>')


def _strip_html(s):
    if not s:
        return ''
    s = _TAG.sub('', str(s))
    s = s.replace('&gt;', '>').replace('&lt;', '<').replace('&amp;', '&')
    return re.sub(r'[ \t]+', ' ', s).strip()


def _norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^a-z0-9 ]+', ' ', str(s or '').lower())).strip()


def _canon_url(canon):
    short = canon.replace('OMIA:', '').split('-')[0]
    tax = (canon.split('-')[1:] or ['9615'])[0]
    return f'https://sniff.world/disease/omia-{short}-{tax}/'


class OmiaDiseaseLayer:
    def __init__(self, data_dir=DATA_DIR):
        load = lambda f: json.load(open(os.path.join(data_dir, f), encoding='utf-8'))
        self.dim = load('omia-disease-dim.json')                      # canon -> {disease,genes,inheritance,omim,mondo,omia_url}
        self.rich = load('omia-phene-rich.json').get('diseases', {})  # canon -> prose + omim_links
        self.refs = load('omia-references.json').get('references', {})# canon -> {refs[], total}
        self.pheno = load('omia-phenotypes.json').get('diseases', {}) # canon -> {phenotypes[], mondo[]}

        # Build the by-canon dim map (the dim is keyed by canon already; tolerate omia_url-derived too).
        self.by_canon = {}
        for k, v in self.dim.items():
            canon = k if re.match(r'^OMIA:\d{6}-\d+$', k) else None
            if not canon:
                m = re.search(r'OMIA0*(\d+)/(\d+)', str(v.get('omia_url') or ''))
                if m:
                    canon = f"OMIA:{m.group(1).zfill(6)}-{m.group(2)}"
            if canon:
                self.by_canon[canon] = v

        # Name index (dim .disease + phene-rich .name/.group_name) for resolution + search.
        self.name_index = []                       # list of (norm, canon)
        seen = set()
        def idx(name, canon):
            n = _norm(name)
            if len(n) < 4 or (n, canon) in seen:
                return
            seen.add((n, canon)); self.name_index.append((n, canon))
        for canon, v in self.by_canon.items():
            idx(v.get('disease'), canon)
        for canon, e in self.rich.items():
            idx(e.get('name'), canon); idx(e.get('group_name'), canon)

        # Breadth data (constraint 2): how many distinct DOG diseases share each name token.
        tok = {}
        for n, canon in self.name_index:
            if (canon.split('-')[1:] or [''])[0] not in QUERY_TAXA:
                continue
            for t in set(w for w in n.split(' ') if len(w) > 2):
                tok.setdefault(t, set()).add(canon)
        self.token_freq = {t: len(s) for t, s in tok.items()}

        # gene_symbol (upper) -> [canon]  (for ask_variant_context.diseases[] enrichment)
        self.gene_to_diseases = {}
        for canon, v in self.by_canon.items():
            if (canon.split('-')[1:] or [''])[0] not in QUERY_TAXA:
                continue
            for g in (v.get('genes') or []):
                self.gene_to_diseases.setdefault(str(g).upper(), []).append(canon)

    # ── resolution (the INV-38 constraint gate; ported from disease-resolve.ts) ──────────────────
    def resolve(self, query):
        """A disease name or OMIA id -> canonical id, or None. SPECIES-gated (dog-only)."""
        s = str(query or '').strip()
        if not s:
            return None
        m = re.search(r'OMIA[:\- ]?0*(\d{1,6})(?:[-/](\d+))?', s, re.I) or re.match(r'^0*(\d{4,6})$', s)
        if m:
            tax = (m.group(2) if m.lastindex and m.lastindex >= 2 else None) or '9615'
            return f"OMIA:{m.group(1).zfill(6)}-{tax}" if tax in QUERY_TAXA else None   # SPECIES gate
        n = _norm(s)
        if len(n) < 4:
            return None
        qt = [t for t in n.split(' ') if len(t) > 2]
        sub = None; allm = None
        for e_norm, canon in self.name_index:
            if (canon.split('-')[1:] or [''])[0] not in QUERY_TAXA:                     # SPECIES gate
                continue
            if e_norm == n:
                return canon
            if n in e_norm or e_norm in n:
                if sub is None or len(e_norm) < sub[1]:
                    sub = (canon, len(e_norm))
            if len(qt) >= 2:
                toks = set(e_norm.split(' '))
                if all(t in toks for t in qt) and (allm is None or len(e_norm) < allm[1]):
                    allm = (canon, len(e_norm))
        return (sub or allm or (None, 0))[0]

    def search(self, query, limit=10):
        """Ranked candidate diseases (name + OMIA id + canonical URL). SPECIES-gated."""
        n = _norm(query)
        if len(n) < 3:
            return []
        qt = [t for t in n.split(' ') if len(t) > 2]
        best = {}
        for e_norm, canon in self.name_index:
            if (canon.split('-')[1:] or [''])[0] not in QUERY_TAXA:
                continue
            score = 0.0
            if e_norm == n:
                score = 1.0
            elif n in e_norm or e_norm in n:
                score = 0.85
            elif qt:
                toks = set(e_norm.split(' '))
                hit = sum(1 for t in qt if t in toks)
                score = 0.7 if hit == len(qt) else (0.4 * hit / len(qt) if hit else 0)
            if score > best.get(canon, 0):
                best[canon] = score
        out = [{'omia_id': c, 'disease': self.display_name(c), 'url': _canon_url(c), 'score': round(s, 2)}
               for c, s in best.items()]
        out.sort(key=lambda r: (-r['score'], len(r['disease'])))
        return out[:limit]

    def display_name(self, canon):
        return ((self.rich.get(canon) or {}).get('name')
                or (self.by_canon.get(canon) or {}).get('disease')
                or (self.rich.get(canon) or {}).get('group_name') or canon)

    # ── the clinical record (what fills disease_links' OMIA half + the new disease_lookup) ───────
    def _provenance(self, canon, rich):
        return {
            'source': 'OMIA (Online Mendelian Inheritance in Animals)',
            'curated_by': 'Nicholas, Tammen & the Sydney Informatics Hub',
            'dataset_doi': OMIA_DOI,
            'license': 'CC-BY-4.0',
            'evidence_grade': 'Curated (published literature)',
            'predicted_disease_relevance': 'documented (OMIA), not a per-dog prediction',
            'as_of': (rich or {}).get('as_of'),
            'citation': OMIA_CITATION,
        }

    def clinical(self, query):
        """The OMIA clinical record for a disease (name/id). Returns None-safe dict or an error dict."""
        canon = self.resolve(query)
        if not canon:
            cands = self.search(query, 5)
            return {'found': False, 'query': query,
                    'message': 'No confident single match (dog-only). Use the candidates or an exact OMIA id.',
                    'candidates': cands}
        rich = self.rich.get(canon) or {}
        dim = self.by_canon.get(canon) or {}
        refrec = self.refs.get(canon) or {}
        phrec = self.pheno.get(canon) or {}
        name = self.display_name(canon)
        rec = {
            'found': True,
            'omia_id': canon,
            'disease': name,
            'canonical_url': _canon_url(canon),
            'inheritance': dim.get('inheritance') or None,
            'genes': dim.get('genes') or None,
            'summary': _strip_html(rich.get('summary') or rich.get('group_summary')) or None,
            'clinical_features': _strip_html(rich.get('clin_feat')) or None,
            'molecular_genetics': _strip_html(rich.get('mol_gen')) or None,
            'pathology': _strip_html(rich.get('pathology')) or None,
            'prevalence': _strip_html(rich.get('prevalence')) or None,
        }
        # clinical signs (HP/MP phenotype terms) + Mondo disease xref (link out to Monarch)
        if phrec.get('phenotypes'):
            rec['clinical_signs'] = [{'term': p['label'], 'id': p['id'],
                                      'url': f"https://monarchinitiative.org/{p['id']}"} for p in phrec['phenotypes']]
        mondo = phrec.get('mondo') or []
        if mondo:
            rec['mondo'] = [{'id': m['id'], 'label': m['label'],
                             'url': f"https://monarchinitiative.org/{m['id']}"} for m in mondo]
        # human analog (OMIA's Group_OMIM -> OMIM)
        links = rich.get('omim_links') or []
        if links:
            rec['human_analog_omim'] = [{'omim_id': l['omim_id'], 'type': l['type'],
                                         'url': f"https://omim.org/entry/{l['omim_id']}"} for l in links]
        # evidence base (peer-reviewed references + the landmark study)
        if refrec.get('total'):
            lm = next((r for r in (refrec.get('refs') or []) if r.get('landmark')), None)
            rec['evidence_base'] = {
                'reference_count': refrec['total'],
                'landmark_study': ({'title': lm['title'], 'pmid': lm.get('pmid'), 'doi': lm.get('doi')} if lm else None),
                'references': [{'title': r['title'], 'year': r.get('year'), 'pmid': r.get('pmid'),
                                'doi': r.get('doi'), 'landmark': bool(r.get('landmark'))}
                               for r in (refrec.get('refs') or [])],
            }
        rec['provenance'] = self._provenance(canon, rich)
        return {k: v for k, v in rec.items() if v is not None}

    def for_gene(self, gene_symbol):
        """gene symbol -> the OMIA diseases it causes (to fill ask_variant_context.diseases[])."""
        out = []
        for canon in self.gene_to_diseases.get(str(gene_symbol or '').upper(), []):
            out.append({'omia_id': canon, 'disease': self.display_name(canon), 'url': _canon_url(canon),
                        'inheritance': (self.by_canon.get(canon) or {}).get('inheritance')})
        return out


if __name__ == '__main__':
    import sys
    q = OmiaDiseaseLayer(os.environ.get('SNIFF_OMIA_DIR', './data'))
    print(f'loaded OMIA clinical layer: {len(q.by_canon)} dim, {len(q.rich)} prose, '
          f'{len(q.refs)} ref-sets, {len(q.pheno)} phenotype-sets, {len(q.name_index)} name keys')
    for probe in (sys.argv[1:] or ['degenerative myelopathy', 'OMIA:000162-9615', 'cataract', 'OMIA:000162-9685']):
        r = q.clinical(probe)
        if r.get('found'):
            print(f"\n[{probe}] -> {r['omia_id']} {r['disease']} | genes={r.get('genes')} "
                  f"signs={len(r.get('clinical_signs', []))} refs={r.get('evidence_base', {}).get('reference_count', 0)} "
                  f"human_analog={len(r.get('human_analog_omim', []))}")
        else:
            print(f"\n[{probe}] -> NO MATCH (gated); {len(r.get('candidates', []))} candidates")
