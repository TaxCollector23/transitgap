# TransitGap MCP

Remote URL: `https://transitgap.vercel.app/mcp` (Streamable HTTP).

Local stdio, from this repository after preparing the data:

```json
{"mcpServers":{"transitgap":{"command":"/absolute/path/to/backend/.venv/bin/python","args":["-m","mcp_server"],"cwd":"/absolute/path/to/transitgap"}}}
```

Use the equivalent `command`, `args`, and working-directory fields in your MCP client. The server imports the web API's routing and evidence functions, loads the same dataset once, and exposes read-only tools. No arbitrary URLs, commands, SQL, verification, or public writes are exposed.
