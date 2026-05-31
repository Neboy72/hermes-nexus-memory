#!/usr/bin/env python3
"""Hermes Nexus Memory MCP Server (SDK-based) — BM25 + Vector Hybrid Search.

Launched by Hermes Gateway as an MCP subprocess (stdio transport).
Registers tool `nexus_search(query, top_k=5)`.
"""
import json
import os
import sys
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", str(Path.home() / ".hermes")))
# Try repo-relative path first, then HERMES_HOME fallback
_repo_root = Path(__file__).resolve().parent.parent
if (_repo_root / "nexus" / "retrieval.py").exists():
    sys.path.insert(0, str(_repo_root))
else:
    sys.path.insert(0, str(HERMES_HOME / "hermes-nexus-memory"))

try:
    from nexus.retrieval import HybridRetriever
except ImportError:
    HybridRetriever = None

qdrant_host = os.environ.get("QDRANT_HOST", "127.0.0.1")
qdrant_port = int(os.environ.get("QDRANT_PORT", "6333"))
collection_name = os.environ.get("NEXUS_COLLECTION", "hermes-memory")

import asyncio
import logging

logger = logging.getLogger("nexus-memory-mcp")

import mcp.server.stdio
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions


server = Server("nexus-memory-mcp")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="nexus_search",
            description="Search Nexus Memory (BM25 + Vector + RRF hybrid)",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "top_k": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of results",
                    },
                },
                "required": ["query"],
            },
        )
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    if name != "nexus_search":
        raise ValueError(f"Unknown tool: {name}")

    query = arguments.get("query", "")
    top_k = arguments.get("top_k", 5)

    try:
        if HybridRetriever is None:
            from nexus.retrieval import BM25Retriever

            retriever = BM25Retriever(
                qdrant_host=qdrant_host,
                qdrant_port=qdrant_port,
                collection_name=collection_name,
            )
            retriever.index_memories()
            results = retriever.search_bm25(query, top_k=top_k)
        else:
            retriever = HybridRetriever(
                qdrant_host=qdrant_host,
                qdrant_port=qdrant_port,
                collection_name=collection_name,
            )
            retriever.index_memories()
            results = retriever.search_hybrid(query, top_k=top_k)

        return [types.TextContent(type="text", text=json.dumps(results, indent=2))]
    except Exception as e:
        return [
            types.TextContent(type="text", text=json.dumps({"error": str(e)}))
        ]


async def main():
    logger.info("Starting Nexus Memory MCP server...")
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="nexus-memory-mcp",
                server_version="2.1.0",
                capabilities=server.get_capabilities(
                    notification_options=mcp.server.lowlevel.NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        filename="/tmp/nexus-mcp-debug.log",
        filemode="w",
    )
    # Also log to stderr for Gateway visibility
    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger("").addHandler(console)
    asyncio.run(main())
