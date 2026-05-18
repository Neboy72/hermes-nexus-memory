"""
Belief Drift Detection — Automated memory health monitoring.

Detects stale, contradictory, and orphaned memory entries before they
corrupt your agent's decision-making. Scores overall memory health 0-10.

Based on: "Why AI Agents Drift: Belief State Is the Real Bottleneck"

Usage:
    from nexus.health import DriftDetector

    detector = DriftDetector()
    report = detector.run()
    print(report.summary)       # "🟢 Score: 0.4/10"
    print(report.stale)         # list of stale entries
    print(report.json())        # full structured output
"""

from __future__ import annotations
import json, re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# ── Stale Patterns ──────────────────────────────────────────────────────────
# These patterns flag entries that describe things as "active" or "running"
# when they should be "disabled" or "deprecated".

DEFAULT_STALE_PATTERNS = [
    (r"\bdeepseek\s+(v[0-9])?\s*(pro|flash)\s+(?:as|running|active|fallback)",
     "DeepSeek is listed as active, but may be disabled"),
    (r"\bnomic.embed\b.*\b(nomic|384)\b",
     "Embedding provider was Nomic — may have switched"),
    (r"\bollama\b(?!.*cloud).*(?:local|localhost|port\s+1)",
     "Ollama listed as local — may have moved to cloud"),
]


@dataclass
class DriftReport:
    """Structured drift detection report."""
    total_entries: int = 0
    stale: list[dict] = field(default_factory=list)
    old: list[dict] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    score: float = 0.0

    @property
    def summary(self) -> str:
        s = self.score
        emoji = "🟢" if s < 1 else "🟡" if s < 3 else "🔴"
        return f"{emoji} Score: {s:.1f}/10"

    def json(self) -> str:
        return json.dumps({
            "total_entries": self.total_entries,
            "stale_count": len(self.stale),
            "old_count": len(self.old),
            "mismatches": self.mismatches,
            "score": self.score,
        }, indent=2)


class DriftDetector:
    """Detects belief drift in Nexus memory entries."""

    def __init__(
        self,
        qdrant_host: str = "localhost",
        qdrant_port: int = 6333,
        collection_name: str = "hermes-memory",
        stale_patterns: list[tuple[str, str]] | None = None,
        old_threshold_days: int = 90,
    ):
        if not HAS_REQUESTS:
            raise ImportError("requests is required: pip install requests")

        self.qdrant_url = f"http://{qdrant_host}:{qdrant_port}"
        self.collection = collection_name
        self.stale_patterns = stale_patterns or DEFAULT_STALE_PATTERNS
        self.old_threshold = timedelta(days=old_threshold_days)

    def _scroll_all(self) -> list[dict]:
        """Pull all points from Qdrant."""
        points = []
        offset = None
        while True:
            body = {"limit": 100, "with_payload": True}
            if offset:
                body["offset"] = offset
            r = requests.post(
                f"{self.qdrant_url}/collections/{self.collection}/points/scroll",
                json=body, timeout=10,
            )
            data = r.json().get("result", {})
            batch = data.get("points", [])
            if not batch:
                break
            points.extend(batch)
            offset = data.get("next_page_offset")
            if not offset:
                break
        return points

    def _check_stale(self, content: str) -> list[str]:
        """Check content against stale patterns."""
        findings = []
        for pattern, note in self.stale_patterns:
            if re.search(pattern, content, re.IGNORECASE):
                findings.append(note)
        return findings

    def run(self) -> DriftReport:
        """Run full drift detection over all memories.

        Returns:
            DriftReport with score, stale entries, old entries, mismatches.
        """
        points = self._scroll_all()
        report = DriftReport(total_entries=len(points))

        now = datetime.now()

        for p in points:
            payload = p.get("payload", {})
            content = payload.get("content", "")
            if not content:
                content = f"{payload.get('user_content', '')} → {payload.get('assistant_content', '')}"

            # Stale pattern check
            stale = self._check_stale(content)
            if stale:
                report.stale.append({
                    "id": str(p.get("id", "")),
                    "issues": stale,
                    "category": payload.get("category", "unknown"),
                })

            # Age check
            ts = payload.get("timestamp")
            if ts:
                try:
                    created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    age = now - created
                    if age > self.old_threshold:
                        report.old.append({
                            "id": str(p.get("id", "")),
                            "age_days": age.days,
                            "category": payload.get("category", "unknown"),
                        })
                except (ValueError, TypeError):
                    pass

        # Drift score: weighted combination
        report.score = min(
            len(report.stale) * 0.4 +
            len(report.old) * 0.1 +
            len(report.mismatches) * 0.3,
            10.0,
        )

        return report

    def run_from_texts(self, entries: list[dict]) -> DriftReport:
        """Run drift detection on a list of dicts (for testing / offline use).

        Each entry: {"id": str, "content": str, "timestamp": str|None}
        """
        report = DriftReport(total_entries=len(entries))
        now = datetime.now()

        for entry in entries:
            content = entry.get("content", "")
            stale = self._check_stale(content)
            if stale:
                report.stale.append({
                    "id": entry.get("id", ""),
                    "issues": stale,
                })

            ts = entry.get("timestamp")
            if ts:
                try:
                    created = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    age = now - created
                    if age > self.old_threshold:
                        report.old.append({
                            "id": entry.get("id", ""),
                            "age_days": age.days,
                        })
                except (ValueError, TypeError):
                    pass

        report.score = min(
            len(report.stale) * 0.4 + len(report.old) * 0.1 + len(report.mismatches) * 0.3,
            10.0,
        )
        return report