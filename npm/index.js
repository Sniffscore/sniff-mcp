#!/usr/bin/env node
/**
 * sniff-mcp — zero-setup launcher for the hosted Sniff MCP server.
 *
 * Bridges stdio <-> the live Streamable-HTTP endpoint (https://mcp.sniff.world/mcp/)
 * via `mcp-remote`, so any stdio-only MCP client (Claude Desktop, older IDEs)
 * can use the hosted Sniff Atlas with no local data or build.
 *
 * Modern clients can skip this entirely and point straight at the URL:
 *   { "mcpServers": { "sniff": { "url": "https://mcp.sniff.world/mcp/" } } }
 *
 * Override the endpoint with SNIFF_MCP_URL (e.g. a self-hosted instance).
 */
const { spawn } = require("child_process");

const url = process.env.SNIFF_MCP_URL || "https://mcp.sniff.world/mcp/";
const extra = process.argv.slice(2);

const child = spawn("npx", ["-y", "mcp-remote", url, ...extra], {
  stdio: "inherit",
  shell: process.platform === "win32",
});

child.on("error", (err) => {
  console.error("[sniff-mcp] failed to start bridge:", err.message);
  console.error("[sniff-mcp] tip: modern clients can use the URL directly: " + url);
  process.exit(1);
});
child.on("exit", (code) => process.exit(code == null ? 0 : code));
