from backend.app.main import _load, state
from backend.app.mcp_server import server
import sys

_load()
if state["error"]:
    print(f"TransitGap data unavailable: {state['error']}", file=sys.stderr)
server.run(transport="stdio")
