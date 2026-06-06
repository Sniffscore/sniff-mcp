#!/bin/sh
set -e
export SNIFF_DATA="${SNIFF_DATA:-/data}"
export SNIFF_STORE="${SNIFF_STORE:-$SNIFF_DATA/point_store.sqlite}"
export SNIFF_MASTER="${SNIFF_MASTER:-$SNIFF_DATA/variant_master.parquet}"
export SNIFF_BREEDAF="${SNIFF_BREEDAF:-$SNIFF_DATA/breed_af.parquet}"
if [ ! -f "$SNIFF_STORE" ]; then
  [ -f "$SNIFF_MASTER" ] || python -m sniff_mcp.fetch_release   # pull from R2 if not mounted
  python -m sniff_mcp.build_store
fi
case "${SNIFF_ROLE:-mcp}" in
  rest) exec uvicorn sniff_mcp.rest:app --host 0.0.0.0 --port "${PORT:-8080}" ;;
  *)    exec python -m sniff_mcp.server ;;   # mcp (Streamable HTTP) — default
esac
