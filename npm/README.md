# sniff-mcp

**Agent-callable canine genomics.** Zero-setup launcher for the hosted [Sniff Atlas](https://sniff.world) MCP server — breed-stratified allele frequencies for 9,667,790 variants across 188 dog breeds, calibrated AI pathogenicity, and a variant/gene/breed/disease knowledge graph. Open, no API key.

## Use it

Modern MCP clients — point straight at the URL (no install):
```json
{ "mcpServers": { "sniff": { "url": "https://mcp.sniff.world/mcp/" } } }
```

stdio-only clients (Claude Desktop, older IDEs) — this package bridges stdio to the hosted server:
```json
{ "mcpServers": { "sniff": { "command": "npx", "args": ["-y", "sniff-mcp"] } } }
```

Or in Claude Code:
```bash
claude mcp add --transport http sniff https://mcp.sniff.world/mcp/
```

Also a plain REST API for web apps: **https://api.sniff.world/** ([docs](https://api.sniff.world/docs) · [llms.txt](https://api.sniff.world/llms.txt)).

Set `SNIFF_MCP_URL` to point the bridge at a self-hosted instance.

## Cite

Gehring, M. (2026). *Sniff Atlas.* Zenodo. https://doi.org/10.5281/zenodo.20566358 (CC-BY-4.0)

Full docs: https://github.com/Sniffscore/sniff-mcp
