#!/usr/bin/env python3
"""Pull the release artifacts from R2 to local NVMe at deploy time (egress is free).
Needs R2_ACCOUNT_ID/R2_ACCESS_KEY_ID/R2_SECRET_ACCESS_KEY + R2_BUCKET (default kg-canonical)."""
import os, boto3
from botocore.config import Config
D=os.environ.get('SNIFF_DATA','/data'); os.makedirs(D,exist_ok=True)
b=os.environ.get('R2_BUCKET','kg-canonical')
s3=boto3.client('s3',endpoint_url=f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com",
    aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
    region_name='auto',config=Config(signature_version='s3v4'))
files={'v2026.12/variants/canvas_variant_master.parquet':'variant_master.parquet',
       'v2026.12/variants/canvas_breed_af.parquet':'breed_af.parquet'}
for k,v in files.items():
    print('fetch',v,flush=True); s3.download_file(b,k,os.path.join(D,v))
print('release fetched to',D)
if __name__=='__main__': import sys; sys.exit(0)
