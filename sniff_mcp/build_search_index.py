#!/usr/bin/env python3
"""Build the Sniff knowledge index on Azure AI Search — a faceted, multi-dimensional,
hybrid (vector + keyword + semantic-ranker) retrieval layer over the knowledge base.

Docs: disease entries, breeds (with plain-language owner summaries folded in), Scout discoveries.
Facetable dimensions: type, breed, breed_group, gene, evidence_tier, severity, confounding_risk,
cohort_n, confidence_tier, diversity_tier — so agents can cross any of them.

Embeddings via Azure OpenAI (text-embedding-3-small). Run once per refresh:
  python -m sniff_mcp.build_search_index
"""
import os, json, glob, time, urllib.request
import pyarrow.parquet as pq

SEARCH_ENDPOINT = os.environ.get('SNIFF_SEARCH_ENDPOINT', 'https://sniff-search.search.windows.net')
SEARCH_KEY = open(os.environ.get('SNIFF_SEARCH_KEY_FILE', '/home/ubuntu/.sniff_search_key')).read().strip()
INDEX = os.environ.get('SNIFF_SEARCH_INDEX', 'sniff-kb')
API = '2024-07-01'
KG = os.environ.get('SNIFF_KGDIR', '/home/ubuntu/sniff-atlas-v1.0.1/knowledge_graph')
BREEDDIM = os.environ.get('SNIFF_BREEDDIM', '/home/ubuntu/sniff-research/mamba-experiments/dimensions/breed_dimensions.json')
PLAIN = os.environ.get('SNIFF_PLAIN', '/home/ubuntu/sniff-research/mamba-experiments/dimensions/breed_plain_summaries.json')
DISC = os.environ.get('SNIFF_DISCOVERIES', '/home/ubuntu/sniff-research/scout/discoveries')


def _oai():
    c = {}
    for line in open('/home/ubuntu/.sniff_openai.env'):
        if '=' in line:
            k, v = line.strip().split('=', 1); c[k] = v
    return c

def embed(texts):
    c = _oai()
    url = c['AZURE_OPENAI_ENDPOINT'].rstrip('/') + '/openai/deployments/embed/embeddings?api-version=2024-10-21'
    out = []
    for i in range(0, len(texts), 16):
        body = json.dumps({'input': texts[i:i+16]}).encode()
        for attempt in range(6):
            try:
                req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', 'api-key': c['AZURE_OPENAI_KEY']})
                out += [d['embedding'] for d in json.loads(urllib.request.urlopen(req, timeout=60).read())['data']]
                break
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 5:
                    time.sleep(6 * (attempt + 1)); continue
                raise
        time.sleep(0.3)
    return out


def search_api(method, path, body=None):
    url = f"{SEARCH_ENDPOINT}/{path}?api-version={API}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json', 'api-key': SEARCH_KEY})
    resp = urllib.request.urlopen(req, timeout=60).read()
    return json.loads(resp) if resp else {}


def _facet(name):  # filterable + facetable string field
    return {'name': name, 'type': 'Edm.String', 'searchable': True, 'filterable': True, 'facetable': True, 'sortable': True}

def create_index():
    schema = {
        'name': INDEX,
        'fields': [
            {'name': 'id', 'type': 'Edm.String', 'key': True},
            _facet('type'), _facet('breed'), _facet('breed_group'), _facet('gene'),
            _facet('evidence_tier'), _facet('severity'), _facet('confounding_risk'),
            _facet('confidence_tier'), _facet('diversity_tier'),
            {'name': 'cohort_n', 'type': 'Edm.Int32', 'filterable': True, 'sortable': True, 'facetable': True},
            {'name': 'title', 'type': 'Edm.String', 'searchable': True},
            {'name': 'content', 'type': 'Edm.String', 'searchable': True},
            {'name': 'url', 'type': 'Edm.String', 'retrievable': True},
            {'name': 'vector', 'type': 'Collection(Edm.Single)', 'searchable': True,
             'dimensions': 1536, 'vectorSearchProfile': 'vp'},
        ],
        'vectorSearch': {'algorithms': [{'name': 'hnsw', 'kind': 'hnsw'}],
                         'profiles': [{'name': 'vp', 'algorithm': 'hnsw'}]},
        'semantic': {'configurations': [{
            'name': 'sem',
            'prioritizedFields': {
                'titleField': {'fieldName': 'title'},
                'prioritizedContentFields': [{'fieldName': 'content'}],
                'prioritizedKeywordsFields': [{'fieldName': 'breed'}, {'fieldName': 'gene'}, {'fieldName': 'type'}],
            }}]},
    }
    try:
        search_api('DELETE', f'indexes/{INDEX}')
    except Exception:
        pass
    search_api('PUT', f'indexes/{INDEX}', schema)
    print(f'index {INDEX} created (faceted + semantic)')


def _diversity_tier(h):
    if h is None: return 'unknown'
    return 'diverse' if h >= 0.35 else 'moderate' if h >= 0.28 else 'tight' if h >= 0.22 else 'severe_bottleneck'

def docs():
    out = []
    n = pq.read_table(f'{KG}/nodes.parquet').to_pandas()
    sv = n[n['category'].astype(str).str.contains('SequenceVariant')]
    for _, r in sv.iterrows():
        g = r.get('gene_symbol'); name = r.get('name'); summ = r.get('disease_summary')
        inh = r.get('inheritance') or r.get('inheritance_mode')
        out.append({'id': 'dz_' + str(r['id']).replace(':', '_').replace('/', '_'), 'type': 'disease',
                    'breed': '', 'breed_group': '', 'gene': str(g or ''), 'evidence_tier': 'Limited',
                    'severity': '', 'confounding_risk': 'medium', 'confidence_tier': '', 'diversity_tier': '',
                    'cohort_n': 0, 'title': f"{name} ({g})",
                    'content': f"Canine disease: {name}. Gene: {g}. {summ or ''} Inheritance: {inh or 'n/a'}.",
                    'url': str(r.get('omia_url') or 'https://sniff.world')})
    plain = json.load(open(PLAIN)) if os.path.exists(PLAIN) else {}
    for b in json.load(open(BREEDDIM))['breeds']:
        slug = b['breed']; ndog = b.get('n_dogs') or 0
        near = ', '.join(x['breed'].replace('_', ' ') for x in (b.get('nearest_5_breeds') or [])[:5])
        ps = (plain.get(slug) or {}).get('plain_summary') or ''
        content = (f"Dog breed: {slug.replace('_',' ')}. Group: {b.get('breed_group')}. "
                   f"Diversity: {_diversity_tier(b.get('mean_heterozygosity'))}. Size: {b.get('breed_weight_kg')} kg. "
                   f"Median lifespan: {b.get('median_lifespan_years')} yr. Nearest breeds: {near}. "
                   f"Plain summary: {ps}")
        out.append({'id': 'breed_' + slug, 'type': 'breed', 'breed': slug, 'breed_group': str(b.get('breed_group') or ''),
                    'gene': '', 'evidence_tier': 'Moderate', 'severity': '', 'confounding_risk': 'low',
                    'confidence_tier': (plain.get(slug) or {}).get('confidence_tier', ''),
                    'diversity_tier': _diversity_tier(b.get('mean_heterozygosity')), 'cohort_n': int(ndog),
                    'title': slug.replace('_', ' '), 'content': content,
                    'url': f"https://sniff.world/breed/{slug}/"})
    for f in glob.glob(f'{DISC}/*.md'):
        key = os.path.basename(f)[:-3]
        if key in ('INDEX', 'LEADERBOARD'):
            continue
        txt = open(f).read()
        out.append({'id': 'disc_' + key, 'type': 'discovery', 'breed': '', 'breed_group': '', 'gene': '',
                    'evidence_tier': 'Predicted', 'severity': '', 'confounding_risk': '', 'confidence_tier': '',
                    'diversity_tier': '', 'cohort_n': 0, 'title': txt.splitlines()[0].lstrip('# ').strip(),
                    'content': txt[:1800], 'url': 'https://sniff.world'})
    return out


def main():
    create_index()
    D = docs()
    print(f'assembled {len(D)} documents; embedding...')
    for d, v in zip(D, embed([d['content'] for d in D])):
        d['vector'] = v
    for i in range(0, len(D), 100):
        search_api('POST', f'indexes/{INDEX}/docs/index',
                   {'value': [dict(d, **{'@search.action': 'mergeOrUpload'}) for d in D[i:i+100]]})
    by = {}
    for d in D:
        by[d['type']] = by.get(d['type'], 0) + 1
    print(f'indexed {len(D)} docs into {INDEX}; by type: {by}')


if __name__ == '__main__':
    main()
