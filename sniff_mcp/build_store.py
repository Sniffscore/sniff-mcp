#!/usr/bin/env python3
"""Build the variant point store from the release parquets. Env-driven (container-friendly).
SNIFF_MASTER, SNIFF_BREEDAF -> input parquets; SNIFF_STORE -> output sqlite. Run once per release."""
import pyarrow.parquet as pq, numpy as np, sqlite3, os, time
MASTER=os.environ.get('SNIFF_MASTER','/data/variant_master.parquet')
BREED =os.environ.get('SNIFF_BREEDAF','/data/breed_af.parquet')
OUT   =os.environ.get('SNIFF_STORE','/data/point_store.sqlite')
RELEASE=os.environ.get('SNIFF_RELEASE','sniff-atlas-v1.0.1')
def main():
    t0=time.time()
    breed_cols=[c for c in pq.read_schema(BREED).names if c!='variant_id']
    m=pq.read_table(MASTER,columns=['variant_id','chrom','ref','alt','alt_af','popmax_af','popmax_breed',
        'popmax_af_robust_n50','popmax_breed_robust_n50','n_breeds_observed','low_dr2_region','consequence',
        'impact','gene_name','gene_id','is_lof','esm_llr','pangolin_max_score','phyloP_241way','deleteriousness_tier']).to_pandas()
    m['pos']=m.variant_id.str.split(':').str[1].astype('int64')
    if os.path.exists(OUT): os.remove(OUT)
    con=sqlite3.connect(OUT); con.execute('PRAGMA journal_mode=OFF'); con.execute('PRAGMA synchronous=OFF')
    con.execute('''CREATE TABLE variants(variant_id TEXT PRIMARY KEY,chrom TEXT,pos INTEGER,ref TEXT,alt TEXT,
      alt_af REAL,popmax_af REAL,popmax_breed TEXT,popmax_af_n50 REAL,popmax_breed_n50 TEXT,n_breeds_observed INTEGER,
      low_dr2 INTEGER,consequence TEXT,impact TEXT,gene_name TEXT,gene_id TEXT,is_lof INTEGER,esm_llr REAL,
      pangolin REAL,phylop REAL,del_tier TEXT,breed_vec BLOB) WITHOUT ROWID''')
    con.execute('CREATE TABLE meta(k TEXT PRIMARY KEY,v TEXT)')
    con.executemany('INSERT INTO meta VALUES(?,?)',[('release',RELEASE),('assembly','canfam4'),
        ('n_variants',str(len(m))),('breed_order','\t'.join(breed_cols))])
    mv={c:m[c].values for c in m.columns}; pf=pq.ParquetFile(BREED); off=0
    INS='INSERT INTO variants VALUES('+','.join('?'*22)+')'
    for b in pf.iter_batches(columns=breed_cols,batch_size=250_000):
        arr=np.column_stack([b.column(c).to_numpy(zero_copy_only=False) for c in breed_cols]).astype(np.float16)
        n=arr.shape[0]; sl=slice(off,off+n); rows=[]
        g=lambda k:mv[k][sl]
        for i in range(n):
            f=lambda v: None if v!=v else float(v)
            rows.append((g('variant_id')[i],g('chrom')[i],int(g('pos')[i]),g('ref')[i],g('alt')[i],
                f(g('alt_af')[i]),f(g('popmax_af')[i]),(None if g('popmax_breed')[i] is None else str(g('popmax_breed')[i])),
                f(g('popmax_af_robust_n50')[i]),(None if g('popmax_breed_robust_n50')[i] is None else str(g('popmax_breed_robust_n50')[i])),
                (None if g('n_breeds_observed')[i]!=g('n_breeds_observed')[i] else int(g('n_breeds_observed')[i])),
                int(bool(g('low_dr2_region')[i])),(None if g('consequence')[i] is None else str(g('consequence')[i])),
                (None if g('impact')[i] is None else str(g('impact')[i])),(None if g('gene_name')[i] is None else str(g('gene_name')[i])),
                (None if g('gene_id')[i] is None else str(g('gene_id')[i])),int(bool(g('is_lof')[i])),
                f(g('esm_llr')[i]),f(g('pangolin_max_score')[i]),f(g('phyloP_241way')[i]),
                (None if g('deleteriousness_tier')[i] is None else str(g('deleteriousness_tier')[i])),arr[i].tobytes()))
        con.executemany(INS,rows); off+=n
    con.commit(); con.execute('VACUUM'); con.commit(); con.close()
    print(f'built {OUT}: {len(m):,} rows, {round(os.path.getsize(OUT)/1e9,2)} GB, {time.time()-t0:.0f}s')
if __name__=='__main__': main()
