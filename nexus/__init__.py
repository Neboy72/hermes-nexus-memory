"""Nexus Memory — Qdrant vector memory for Hermes Agent.

3-layer architecture (Episodic → Semantic → Community).
Three embedding providers — user chooses, zero code changes needed.

Embedding providers:
  ollama                — nomic-embed-text via localhost:11434  (requires Ollama)
  sentence-transformers — all-MiniLM-L6-v2 in-process            (pip install)
  voyage                — voyage-3-lite via Voyage AI Cloud      (API key)

Install:
  hermes memory setup               → interactive picker
  hermes skills install <url>       → one-liner from GitHub

Config (optional, written by setup wizard):
  plugins:
    nexus-memory:
      embed_provider: sentence-transformers   # or: ollama | voyage
      voyage_api_key: ${VOYAGE_API_KEY}       # only if voyage
      qdrant_url: http://127.0.0.1:6333
      collection: hermes-memory
"""

from __future__ import annotations

import json, logging, time, uuid
from typing import Any, Dict, List, Optional

import requests

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

# ── defaults ─────────────────────────────────────────────────────────────────

QDRANT_URL = "http://127.0.0.1:6333"
COLLECTION = "hermes-memory"
DEFAULT_PROVIDER = "sentence-transformers"
OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "nomic-embed-text"

# ── tool schemas ─────────────────────────────────────────────────────────────

NEXUS_SEARCH_SCHEMA = {
    "name": "nexus_search",
    "description": (
        "Semantic search across all Nexus memories (Qdrant vector DB). "
        "Finds relevant facts, past conversations, and saved knowledge. "
        "Use before asking the user for information and when you need to recall context from previous sessions."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query in natural language"},
            "limit": {"type": "number", "description": "Max results (default: 5, max: 20)"},
        },
        "required": ["query"],
    },
}

NEXUS_REMEMBER_SCHEMA = {
    "name": "nexus_remember",
    "description": (
        "Explicitly save a fact, decision, or insight to Nexus long-term memory (Qdrant). "
        "Use for important information the user would expect you to recall later."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact or insight to remember"},
            "category": {
                "type": "string",
                "enum": ["fact", "preference", "decision", "pattern", "lesson"],
            },
            "source": {"type": "string", "description": "Where this came from (session_id, user, observation)"},
        },
        "required": ["content"],
    },
}

NEXUS_FORGET_SCHEMA = {
    "name": "nexus_forget",
    "description": "Delete a Nexus memory by its ID.",
    "parameters": {
        "type": "object",
        "properties": {
            "memory_id": {"type": "string", "description": "ID of the memory to delete"},
        },
        "required": ["memory_id"],
    },
}

# ── embedding providers ──────────────────────────────────────────────────────

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class EmbeddingProvider:
    """Base class for pluggable embedding backends."""

    def embed(self, text: str) -> List[float]:
        raise NotImplementedError

    def dims(self) -> int:
        raise NotImplementedError

    def health(self) -> bool:
        raise NotImplementedError


class OllamaProvider(EmbeddingProvider):
    def embed(self, text: str) -> list:
        resp = requests.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": OLLAMA_MODEL, "prompt": text},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    def dims(self) -> int:
        return 768

    def health(self) -> bool:
        try:
            resp = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": OLLAMA_MODEL, "prompt": "health"},
                timeout=5,
            )
            return resp.status_code == 200 and "embedding" in resp.json()
        except Exception:
            return False


class SentenceTransformersProvider(EmbeddingProvider):
    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")

    def embed(self, text: str) -> list:
        self._load()
        return self._model.encode(text, normalize_embeddings=True).tolist()

    def dims(self) -> int:
        return 384

    def health(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer
            return True
        except ImportError:
            return False


class VoyageProvider(EmbeddingProvider):
    def __init__(self, api_key: str = ""):
        self._api_key = api_key or ""

    def embed(self, text: str) -> list:
        resp = requests.post(
            "https://api.voyageai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": [text], "model": "voyage-3-lite"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["data"][0]["embedding"]

    def dims(self) -> int:
        return 512

    def health(self) -> bool:
        if not self._api_key:
            return False
        try:
            self.embed("health")
            return True
        except Exception:
            return False


def _load_embedding_provider(provider_name: str = "", voyage_api_key: str = "") -> EmbeddingProvider:
    name = provider_name or DEFAULT_PROVIDER
    if name == "ollama":
        return OllamaProvider()
    elif name == "sentence-transformers":
        return SentenceTransformersProvider()
    elif name == "voyage":
        return VoyageProvider(api_key=voyage_api_key)
    else:
        logger.warning("Unknown embed_provider '%s', falling back to sentence-transformers", name)
        return SentenceTransformersProvider()


# ── plugin config ────────────────────────────────────────────────────────────

def _load_plugin_config() -> dict:
    from hermes_constants import get_hermes_home
    config_path = get_hermes_home() / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        from hermes_cli.config import cfg_get
        with open(config_path) as f:
            all_config = yaml.safe_load(f) or {}
        return cfg_get(all_config, "plugins", "nexus-memory", default={}) or {}
    except Exception:
        return {}


# ── Qdrant helpers ───────────────────────────────────────────────────────────

def _qdrant(method: str, path: str, **kwargs) -> dict:
    url = f"{QDRANT_URL}{path}"
    resp = requests.request(method, url, timeout=10, **kwargs)
    resp.raise_for_status()
    return resp.json()


# ── MemoryProvider ───────────────────────────────────────────────────────────

class NexusMemoryProvider(MemoryProvider):
    """Qdrant-backed memory with pluggable embedding providers."""

    def __init__(self, plugin_config: dict | None = None):
        config = plugin_config or _load_plugin_config()
        self._session_id: str = ""
        self._available: bool = False
        self._embed: EmbeddingProvider = _load_embedding_provider(
            provider_name=config.get("embed_provider", ""),
            voyage_api_key=config.get("voyage_api_key", ""),
        )
        self._embed_provider_name: str = config.get("embed_provider", DEFAULT_PROVIDER)

    @property
    def name(self) -> str:
        return "nexus"

    def is_available(self) -> bool:
        try:
            if not requests.get(f"{QDRANT_URL}/healthz", timeout=2).status_code == 200:
                return False
            if not self._embed.health():
                return False
            _qdrant("GET", f"/collections/{COLLECTION}")
            return True
        except Exception:
            return False

    def initialize(self, session_id: str, **kwargs) -> None:
        self._session_id = session_id
        self._available = self.is_available()
        status = f"{self._embed.dims()}d via {self._embed_provider_name}"
        if self._available:
            logger.info("Nexus memory initialized (session=%s, %s)", session_id, status)
        else:
            logger.warning("Nexus memory unavailable — Qdrant or %s not reachable", self._embed_provider_name)

    def system_prompt_block(self) -> str:
        if not self._available:
            return ""
        try:
            info = _qdrant("GET", f"/collections/{COLLECTION}")
            count = info.get("result", {}).get("points_count", 0)
        except Exception:
            count = "?"
        return (
            f"# Nexus Memory ({self._embed.dims()}d via {self._embed_provider_name})\n"
            f"Active — {count} memories stored. Use nexus_search(query=...) to recall. "
            f"Use nexus_remember(content=..., category=...) to save important facts."
            if count else
            f"# Nexus Memory ({self._embed.dims()}d via {self._embed_provider_name})\n"
            f"Active — empty. Use nexus_remember(content=..., category=...) to start building memory."
        )

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if not self._available or not query.strip():
            return ""
        try:
            results = self._search(query.strip(), limit=5)
            if not results:
                return ""
            lines = []
            for r in results:
                content = r.get("content", "") or f"{r.get('user_content', '')} → {r.get('assistant_content', '')}"
                category = r.get("category", "")
                prefix = f"[{category}] " if category else ""
                lines.append(f"- {prefix}{content}")
            return "## Nexus Memory\n" + "\n".join(lines)
        except Exception as e:
            logger.debug("Nexus prefetch failed: %s", e)
            return ""

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        if not self._available:
            return
        sid = session_id or self._session_id
        text = f"User: {user_content}\nAssistant: {assistant_content}"
        try:
            vec = self._embed.embed(text[:2000])
            _qdrant(
                "PUT",
                f"/collections/{COLLECTION}/points",
                json={"points": [{
                    "id": str(uuid.uuid4()),
                    "vector": vec,
                    "payload": {
                        "type": "turn",
                        "session_id": sid,
                        "user_content": user_content[:500],
                        "assistant_content": assistant_content[:500],
                        "timestamp": _now_iso(),
                    },
                }]},
            )
        except Exception as e:
            logger.debug("Nexus sync_turn failed: %s", e)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [NEXUS_SEARCH_SCHEMA, NEXUS_REMEMBER_SCHEMA, NEXUS_FORGET_SCHEMA]

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        try:
            if tool_name == "nexus_search":
                query = args["query"]
                limit = min(int(args.get("limit", 5)), 20)
                results = self._search(query, limit=limit)
                return json.dumps({"results": results, "count": len(results)})

            elif tool_name == "nexus_remember":
                return self._remember(
                    args["content"],
                    args.get("category", "fact"),
                    args.get("source", self._session_id),
                )

            elif tool_name == "nexus_forget":
                return self._forget(args["memory_id"])

            return tool_error(f"Unknown tool: {tool_name}")

        except KeyError as exc:
            return tool_error(f"Missing required argument: {exc}")
        except Exception as exc:
            return tool_error(str(exc))

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        if not self._available or not messages:
            return
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if user_msgs:
            try:
                self._remember(
                    f"Last conversation: {user_msgs[-1]['content'][:300]}",
                    category="pattern",
                    source=self._session_id,
                )
            except Exception:
                pass

    def shutdown(self) -> None:
        self._available = False
        self._session_id = ""

    # ── hermes memory setup integration ──────────────────────────────────

    def get_config_schema(self) -> List[Dict[str, Any]]:
        return [
            {
                "key": "embed_provider",
                "description": "Embedding provider",
                "default": DEFAULT_PROVIDER,
                "choices": ["ollama", "sentence-transformers", "voyage"],
            },
            {
                "key": "voyage_api_key",
                "description": "Voyage AI API key (required only for voyage provider)",
                "secret": True,
                "env_var": "VOYAGE_API_KEY",
            },
            {
                "key": "qdrant_url",
                "description": "Qdrant server URL",
                "default": QDRANT_URL,
            },
            {
                "key": "collection",
                "description": "Qdrant collection name",
                "default": COLLECTION,
            },
        ]

    def save_config(self, values: Dict[str, Any], hermes_home: str) -> None:
        from pathlib import Path
        config_path = Path(hermes_home) / "config.yaml"
        try:
            import yaml
            existing = {}
            if config_path.exists():
                with open(config_path) as f:
                    existing = yaml.safe_load(f) or {}
            existing.setdefault("plugins", {})
            existing["plugins"]["nexus-memory"] = values
            with open(config_path, "w") as f:
                yaml.dump(existing, f, default_flow_style=False)
        except Exception:
            pass

    # ── internal ─────────────────────────────────────────────────────────

    def _search(self, query: str, limit: int = 5) -> list:
        vec = self._embed.embed(query)

        # Recreate collection if embedding dimensions changed
        existing = _qdrant("GET", f"/collections/{COLLECTION}")
        config = existing.get("result", {}).get("config", {}).get("params", {}).get("vectors", {})
        if config.get("size") != self._embed.dims():
            logger.info("Embedding dims changed (%d→%d), recreating collection",
                        config.get("size"), self._embed.dims())
            _qdrant("DELETE", f"/collections/{COLLECTION}")
            _qdrant("PUT", f"/collections/{COLLECTION}",
                    json={"vectors": {"size": self._embed.dims(), "distance": "Cosine"}})

        result = _qdrant(
            "POST",
            f"/collections/{COLLECTION}/points/search",
            json={"vector": vec, "limit": limit, "with_payload": True},
        )
        return [
            {"id": p.get("id"), "score": round(p.get("score", 0), 3), **p.get("payload", {})}
            for p in result.get("result", [])
        ]

    def _remember(self, content: str, category: str, source: str) -> str:
        vec = self._embed.embed(content)
        mem_id = str(uuid.uuid4())
        _qdrant(
            "PUT",
            f"/collections/{COLLECTION}/points",
            json={"points": [{
                "id": mem_id,
                "vector": vec,
                "payload": {
                    "type": "memory",
                    "content": content,
                    "category": category,
                    "source": source,
                    "timestamp": _now_iso(),
                },
            }]},
        )
        return json.dumps({"status": "remembered", "id": mem_id})

    def _forget(self, memory_id: str) -> str:
        _qdrant("POST", f"/collections/{COLLECTION}/points/delete",
                json={"points": [memory_id]})
        return json.dumps({"status": "forgotten", "id": memory_id})


# ── entry point ──────────────────────────────────────────────────────────────

def register(ctx) -> None:
    provider = NexusMemoryProvider()
    ctx.register_memory_provider(provider)
    logger.info("Nexus memory provider registered")
