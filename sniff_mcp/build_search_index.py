#!/usr/bin/env python3
"""Build the Sniff knowledge index on Azure AI Search — hybrid (vector+keyword) retrieval
over the whole knowledge base: disease entries, breeds, and Scout discoveries.

Embeddings via Azure OpenAI (text-embedding-3-small). Run once per refresh:
  python -m sniff_mcp.build_search_index
Config: /home/ubuntu/.sniff_openai.env (OpenAI) + /home/ubuntu/.sniff_search_key (AI Search admin key).
"""
import os, json, glob, time, urllib.request
import pyarrow.parquet as pq

SEARCH_ENDPOINT = os.environ.get('SNIFF_SEARCH_ENDPOINT', 'https://sniff-search.search.windows.net')
SEARCH_KEY = open(os.environ.get('SNIFF_SEARCH_KEY_FILE', '/home/ubuntu/.sniff_search_key')).read().strip()
INDEX = os.environ.get('SNIFF_SEARCH_INDEX', 'sniff-kb')
API = '2024-07-01'
KG = os.environ.get('SNIFF_KGDIR', '/home/ubuntu/sniff-atlas-v1.0.1/knowledge_graph')
BREEDDIM = os.environ.get('SNIFF_BREEDDIM', '/home/ubuntu/sniff-research/mamba-experiments/dimensions/breed_dimensions.json')
DISC = os.environ.get('SNIFF_DISCOVERIES', '/home/ubuntu/sniff-research/scout/discoveries')

# --- Azure OpenAI embeddings -------------------------------------------------
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
        batch = texts[i:i+16]
        body = json.dumps({'input': batch}).encode()
        req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json', 'api-key': c['AZURE_OPENAI_KEY']})
        r = json.loads(urllib.request.urlopen(req, timeout=60).read())
        out += [d['embedding'] for d in r['data']]
        time.sleep(0.1)
    return out

# --- AI Search REST ----------------------------------------------------------
def search_api(method, path, body=None):
    url = f"{SEARCH_ENDPOINT}/{path}?api-version={API}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={'Content-Type': 'application/json', 'api-key': SEARCH_KEY})
    resp = urllib.request.urlopen(req, timeout=60).read()
    return json.loads(resp) if resp else {}

def create_index():
    schema = {
        'name': INDEX,
        'fields': [
            {'name': 'id', 'type': 'Edm.String', 'key': True},
            {'name': 'type', 'type': 'Edm.String', 'filterable': True, 'facetable': True},
            {'name': 'title', 'type': 'Edm.String', 'searchable': True},
            {'name': 'content', 'type': 'Edm.String', 'searchable': True},
            {'name': 'url', 'type': 'Edm.String', 'retrievable': True},
            {'name': 'vector', 'type': 'Collection(Edm.Single)', 'searchable': True,
             'dimensions': 1536, 'vectorSearchProfile': 'vp'},
        ],
        'vectorSearch': {
            'algorithms': [{'name': 'hnsw', 'kind': 'hnsw'}],
            'profiles': [{'name': 'vp', 'algorithm': 'hnsw'}],
        },
    }
    try:
        search_api('DELETE', f'indexes/{INDEX}')
    except Exception:
        pass
    search_api('PUT', f'indexes/{INDEX}', schema)
    print(f'index {INDEX} created')

# --- document assembly -------------------------------------------------------
def docs():
    out = []
    # 1) disease / known-variant entries (the gold)
    n = pq.read_table(f'{KG}/nodes.parquet').to_pandas()
    sv = n[n['category'].astype(str).str.contains('SequenceVariant')]
    for _, r in sv.iterrows():
        g = r.get('gene_symbol'); name = r.get('name'); summ = r.get('disease_summary')
        inh = r.get('inheritance') or r.get('inheritance_mode')
        content = f"Canine disease: {name}. Gene: {g}. {summ or ''} Inheritance: {inh or 'n/a'}."
        out.append({'id': 'dz_' + str(r['id']).replace(':', '_').replace('/', '_'),
                    'type': 'disease', 'title': f"{name} ({g})", 'content': content,
                    'url': str(r.get('omia_url') or 'https://sniff.world')})
    # 2) breeds
    bd = json.load(open(BREEDDIM))['breeds']
    for b in bd:
        near = ', '.join(x['breed'] for x in (b.get('nearest_5_breeds') or [])[:5])
        content = (f"Dog breed: {b['breed'].replace('_',' ')}. Group: {b.get('breed_group')}. "
                   f"Genetic diversity (heterozygosity): {b.get('mean_heterozygosity')}. "
                   f"Bottleneck rank: {b.get('bottleneck_rank')}. Size: {b.get('breed_weight_kg')} kg. "
                   f"Size-adjusted lifespan residual: {b.get('lifespan_residual_years')} yr. "
                   f"Genetically nearest breeds: {near}.")
        out.append({'id': 'breed_' + b['breed'], 'type': 'breed',
                    'title': b['breed'].replace('_', ' '), 'content': content,
                    'url': f"https://sniff.world/breed/{b['breed']}/"})
    # 3) Scout discoveries
    for f in glob.glob(f'{DISC}/*.md'):
        key = os.path.basename(f)[:-3]
        if key in ('INDEX', 'LEADERBOARD'):
            continue
        txt = open(f).read()
        title = txt.splitlines()[0].lstrip('# ').strip()
        out.append({'id': 'disc_' + key, 'type': 'discovery', 'title': title,
                    'content': txt[:1800], 'url': 'https://sniff.world'})
    return out


def main():
    create_index()
    D = docs()
    print(f'assembled {len(D)} documents; embedding...')
    vecs = embed([d['content'] for d in D])
    for d, v in zip(D, vecs):
        d['vector'] = v
    # push in batches
    for i in range(0, len(D), 100):
        batch = {'value': [dict(d, **{'@search.action': 'mergeOrUpload'}) for d in D[i:i+100]]}
        search_api('POST', f'indexes/{INDEX}/docs/index', batch)
    print(f'indexed {len(D)} docs into {INDEX}')
    by = {}
    for d in D:
        by[d['type']] = by.get(d['type'], 0) + 1
    print('by type:', by)


if __name__ == '__main__':
    main()
