"""Entry point: python -m mcp_server_mindmap."""

import sys
from pathlib import Path

# Добавляем корень проекта в PYTHONPATH для импорта shared
_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from mcp_server_mindmap.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
