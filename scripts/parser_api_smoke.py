"""Run the lightweight parser capability fixture against one configured API."""

import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.llm_gateway import GatewayConfig
from backend.parser_capability import verify_parser_capabilities


async def main():
    config = GatewayConfig(
        role="parser",
        base_url=os.environ["PARSER_SMOKE_URL"],
        model=os.environ["PARSER_SMOKE_MODEL"],
        api_key=os.environ["PARSER_SMOKE_KEY"],
        adapter=os.getenv("PARSER_SMOKE_ADAPTER", "auto"),
    )
    result = await verify_parser_capabilities(config)
    safe = {
        "success": result["success"],
        "adapter": result["adapter"],
        "checks": result["checks"],
        "errors": {
            kind: {"type": details.get("error"), "preview": details.get("raw_preview", "")}
            for kind, details in result["details"].items()
            if details.get("error")
        },
    }
    print(json.dumps(safe, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
