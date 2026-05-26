"""
Nexus Memory Skill Export (v1.9.0).

Searches canonical facts in Nexus Memory, clusters them by topic, and
generates a ready-to-use SKILL.md file.

Usage:
    from nexus.export import export_skill
    export_skill("review-patterns", topic="code review")

    # CLI:
    # nexus-export --skill "review-patterns" --topic "code review"
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

import requests

_logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

COLLECTION_ALL = "hermes-memory"

SKILL_TEMPLATE = """\
---
name: {name}
description: "{description}"
tags: {tags}
version: 1.0.0
created: {created}
source: "Auto-generated from Nexus Memory v1.9.0"
facts:
{fact_refs}
---

# {skill_title}

{summary}

---

## Prerequisites

{prerequisites}

---

## Steps

{steps}

---

## Pitfalls

{pitfalls}

---

## Verification

{verification}

---

Auto-generated from Nexus Memory v1.9.0
"""


# ── Data Models ────────────────────────────────────────────────────────────


@dataclass
class SkillCluster:
    """Clustered facts ready for SKILL.md generation."""
    name: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    pitfalls: list[str] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    fact_ids: list[str] = field(default_factory=list)
    created: str = field(default_factory=lambda: datetime.now().isoformat()[:10])

    def to_skill(self) -> str:
        """Render as SKILL.md using the template."""
        tags_str = json.dumps([t for t in self.tags if t])
        fact_lines = []
        for i, fid in enumerate(self.fact_ids[:20]):
            fact_lines.append(f"  - {fid}")
        fact_refs = "\n".join(fact_lines) if fact_lines else "  []"

        def _bullets(items: list[str]) -> str:
            if not items:
                return "None identified yet."
            return "\n".join(f"1. {item}" for item in items)

        return SKILL_TEMPLATE.format(
            name=self.name,
            description=self.description or f"Workflow for {self.name}",
            tags=tags_str,
            created=self.created,
            fact_refs=fact_refs,
            skill_title=self.name.replace("-", " ").title(),
            summary=self.description or "",
            prerequisites=_bullets(self.prerequisites),
            steps=_bullets(self.steps),
            pitfalls=_bullets(self.pitfalls),
            verification=_bullets(self.verification),
        )


# ── Qdrant Helpers ─────────────────────────────────────────────────────────


def _qdrant_url(host: str, port: int, collection: str) -> str:
    return f"http://{host}:{port}/collections/{collection}"


# ── Search: Canonical Facts Only ───────────────────────────────────────────


def search_knowledge(
    topic: str,
    limit: int = 20,
    host: str = "localhost",
    port: int = 6333,
) -> list[dict]:
    """Search for canonical facts matching a topic.

    Queries the full-history collection, filtering to canonical status
    and text-matching the topic against content.

    Args:
        topic: The topic to search for.
        limit: Max results.
        host: Qdrant host.
        port: Qdrant port.

    Returns:
        List of fact payloads (already filtered to canonical).
    """
    url = f"{_qdrant_url(host, port, COLLECTION_ALL)}/points/scroll"

    # Paginated scroll through all entries
    all_points = []
    offset = None
    # Scan at least 200 entries to find topic matches across the collection
    scroll_limit = max(limit * 10, 200)
    fetch_limit = min(100, scroll_limit)
    while len(all_points) < scroll_limit:
        body = {
            "limit": fetch_limit,
            "with_payload": True,
        }
        if offset:
            body["offset"] = offset
        r = requests.post(url, json=body, timeout=10)
        r.raise_for_status()
        data = r.json().get("result", {})
        batch = data.get("points", [])
        if not batch:
            break
        all_points.extend(batch)
        offset = data.get("next_page_offset")
        if not offset:
            break

    facts = []
    for p in all_points:
        payload = p.get("payload", {})

        # Filter: only canonical or legacy (no status = treat as canonical)
        status = payload.get("status", "")
        if status and status != "canonical":
            continue

        # Extract text from various content field formats
        # Legacy: user_content / assistant_content (Hermes conversation format)
        # v1.8.0: content (direct string or dict)
        raw_content = payload.get("content", None)
        if raw_content is None:
            # Legacy format — combine user + assistant
            text = "{} {}".format(
                payload.get("user_content", ""),
                payload.get("assistant_content", ""),
            ).strip()
        elif isinstance(raw_content, dict):
            text = raw_content.get("content", str(raw_content))
        else:
            text = str(raw_content) if raw_content else ""

        # Skip empty entries
        if not text:
            continue

        text_lower = text.lower()
        topic_lower = topic.lower()

        # Simple topic filter: topic appears in content or tags
        # Simple topic filter: topic appears in content or tags
        topic_match = topic_lower in text_lower

        # Also check tags/categories
        if not topic_match:
            tags = payload.get("tags", [])
            categories = payload.get("category", "")
            if isinstance(tags, list) and any(topic_lower in str(t).lower() for t in tags):
                topic_match = True
            if topic_lower in str(categories).lower():
                topic_match = True

        if topic_match:
            facts.append({
                "id": str(p.get("id", "")),
                "fact_id": payload.get("fact_id", ""),
                "version_id": payload.get("version_id", ""),
                "content": text,
                "category": payload.get("category", "fact"),
                "tags": payload.get("tags", []),
                "status": payload.get("status", "canonical"),
                "created_at": payload.get("created_at", ""),
                "provenance": payload.get("provenance", {}),
            })

    # Remove duplicates by content (keep newest)
    seen_content: set[str] = set()
    deduped = []
    for f in sorted(facts, key=lambda x: x.get("created_at", ""), reverse=True):
        c = f.get("content", "")
        if c and c not in seen_content:
            seen_content.add(c)
            deduped.append(f)

    return deduped[:limit]


# ── Clustering ─────────────────────────────────────────────────────────────


def cluster_facts(
    facts: list[dict],
    name: str,
) -> SkillCluster:
    """Cluster facts into SKILL.md sections.

    Uses heuristic extraction to identify:
    - Steps: factual/actionable content
    - Pitfalls: cautionary/failure patterns
    - Prerequisites: dependency/setup facts
    - Verification: confirmation/test patterns

    Args:
        facts: List of fact payloads from search_knowledge().
        name: Skill name.

    Returns:
        SkillCluster with populated sections.
    """
    cluster = SkillCluster(name=name)

    pitfall_keywords = [
        "achtung", "vorsicht", "fehler", "bug", "nicht", "fail",
        "attention", "warning", "pitfall", "dont", "never", "avoid",
        "problem", "issue", "broken", "crashes",
    ]
    prerequisite_keywords = [
        "braucht", "benötigt", "muss", "erforderlich",
        "need", "requires", "must", "prerequisite", "dependency",
        "install", "setup", "config",
    ]
    verification_keywords = [
        "prüfe", "test", "verifizier", "check",
        "verify", "validate", "confirm", "ensure", "test",
    ]

    seen_contents: set[str] = set()
    all_tags: set[str] = set()
    full_text = []

    for fact in facts:
        content = fact.get("content", "")
        if not content or content in seen_contents:
            continue
        seen_contents.add(content)

        category = fact.get("category", "")
        tags = fact.get("tags", [])
        if isinstance(tags, list):
            all_tags.update(str(t) for t in tags)
        all_tags.add(category)
        full_text.append(content)

        # Classify content
        content_lower = content.lower()

        # Check for pitfall keywords
        if any(kw in content_lower for kw in pitfall_keywords):
            cluster.pitfalls.append(content[:200])

        # Check for prerequisite keywords
        if any(kw in content_lower for kw in prerequisite_keywords):
            cluster.prerequisites.append(content[:200])

        # Check for verification keywords
        if any(kw in content_lower for kw in verification_keywords):
            cluster.verification.append(content[:200])

        # Everything else is a step
        cluster.steps.append(content[:200])

        # Track fact_ids for traceability
        fid = fact.get("fact_id") or fact.get("id", "")
        if fid and fid not in cluster.fact_ids:
            cluster.fact_ids.append(fid)

    # Build description from first few facts
    cluster.description = (
        f"Auto-generated skill for {name}. "
        f"Based on {len(facts)} canonical facts from Nexus Memory."
    )

    # Collect tags
    clean_tags = [t for t in all_tags if t and t != "unknown" and len(t) < 40]
    cluster.tags = sorted(set(clean_tags))[:10]  # max 10 tags

    # Merge overlapping sections (pitfall/step duplicates)
    cluster.steps = _dedup_section(cluster.steps)

    return cluster


def _dedup_section(items: list[str]) -> list[str]:
    """Deduplicate and trim section items."""
    seen: set[str] = set()
    result = []
    for item in items:
        # Use first 80 chars as dedup key to catch near-duplicates
        key = item[:80]
        if key not in seen:
            seen.add(key)
            result.append(item.strip())
    return result[:15]  # Max 15 items per section


# ── Export ─────────────────────────────────────────────────────────────────


def export_skill(
    name: str,
    topic: str | None = None,
    limit: int = 20,
    output_dir: str | None = None,
    deploy: bool = False,
    host: str = "localhost",
    port: int = 6333,
) -> tuple[str, str]:
    """Full export pipeline: search → cluster → render → write.

    Args:
        name: Skill name (used as filename + SKILL.md identity).
        topic: Search topic. Defaults to name if omitted.
        limit: Max facts to include.
        output_dir: Custom output directory.
        deploy: If True, write to ~/.hermes/skills/ directly.
        host: Qdrant host.
        port: Qdrant port.

    Returns:
        (file_path, skill_content) tuple.
    """
    topic = topic or name

    _logger.info("Searching for '%s' in Nexus Memory...", topic)
    facts = search_knowledge(topic, limit=limit, host=host, port=port)

    if not facts:
        _logger.warning("No canonical facts found for topic '%s'", topic)
        return ("", "No canonical facts found for topic '{topic}'.")

    _logger.info("Found %d canonical facts", len(facts))
    cluster = cluster_facts(facts, name=name)
    skill_content = cluster.to_skill()

    # Determine output path
    if deploy:
        skills_dir = os.path.expanduser("~/.hermes/skills/")
        os.makedirs(skills_dir, exist_ok=True)
        file_path = os.path.join(skills_dir, f"{name}.md")
    elif output_dir:
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"{name}.md")
    else:
        file_path = f"{name}.md"

    with open(file_path, "w") as f:
        f.write(skill_content)

    _logger.info("Skill written to %s", file_path)
    return file_path, skill_content


# ── List Exportable Topics ─────────────────────────────────────────────────


def list_topics(
    min_facts: int = 3,
    limit: int = 50,
    host: str = "localhost",
    port: int = 6333,
    max_scan: int = 2000,
) -> list[dict]:
    """List topics that have enough canonical facts for a skill export.

    Scans the all-history collection with offset-based pagination,
    groups facts by category, and returns topics with >= min_facts entries.

    Filters to canonical and legacy entries (no status = canonical by default).

    Args:
        min_facts: Minimum facts needed for a valid topic.
        limit: Max topics to return.
        host: Qdrant host.
        port: Qdrant port.
        max_scan: Max entries to scan (prevents runaway on large collections).

    Returns:
        List of {topic, count, sample_fact} dicts.
    """
    url = f"{_qdrant_url(host, port, COLLECTION_ALL)}/points/scroll"

    # Paginated scan — same pattern as search_knowledge()
    all_points: list[dict] = []
    scroll_offset: str | None = None
    page_size = 200
    while len(all_points) < max_scan:
        body: dict[str, Any] = {
            "limit": page_size,
            "with_payload": True,
        }
        if scroll_offset:
            body["offset"] = scroll_offset
        r = requests.post(url, json=body, timeout=10)
        r.raise_for_status()
        data = r.json().get("result", {})
        batch = data.get("points", [])
        if not batch:
            break
        all_points.extend(batch)
        scroll_offset = data.get("next_page_offset")
        if not scroll_offset:
            break

    # Group by category (filtered: only canonical or legacy)
    groups: dict[str, list[str]] = {}
    for p in all_points:
        pl = p.get("payload", {})
        status = pl.get("status", "")
        if status and status != "canonical":
            continue
        cat = pl.get("category", "uncategorized")
        content = pl.get("content", "")
        if isinstance(content, dict):
            text = content.get("content", "")
        else:
            text = content
        if text:
            if cat not in groups:
                groups[cat] = []
            groups[cat].append(text[:100])

    topics = []
    for topic, samples in sorted(groups.items(), key=lambda x: -len(x[1])):
        if len(samples) >= min_facts:
            topics.append({
                "topic": topic,
                "count": len(samples),
                "sample": samples[0] if samples else "",
            })
        if len(topics) >= limit:
            break

    return topics


# ── CLI Entry Point ────────────────────────────────────────────────────────


def cli_main() -> None:
    """Entry point for the ``nexus-export`` CLI command.

    Installed via ``[project.scripts]`` in ``pyproject.toml``.
    """
    import argparse
    import logging
    import sys

    parser = argparse.ArgumentParser(
        description="Nexus Memory Skill Export — generate SKILL.md from canonical facts",
    )
    parser.add_argument(
        "--skill", "-s", type=str, help="Skill name to export",
    )
    parser.add_argument(
        "--topic", "-t", type=str, default=None,
        help="Search topic (defaults to skill name)",
    )
    parser.add_argument(
        "--limit", "-n", type=int, default=20,
        help="Max facts to include (default: 20)",
    )
    parser.add_argument(
        "--deploy", "-d", action="store_true",
        help="Write directly to ~/.hermes/skills/",
    )
    parser.add_argument(
        "--output", "-o", type=str, default=None,
        help="Custom output directory",
    )
    parser.add_argument(
        "--list", "-l", action="store_true",
        help="List exportable topics from Nexus",
    )
    parser.add_argument(
        "--quiet", "-q", action="store_true",
        help="Suppress logging output",
    )

    args = parser.parse_args()

    if not args.quiet:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.list:
        topics = list_topics()
        if not topics:
            print("No topics with enough canonical facts found.")
            sys.exit(0)
        print("Exportable Topics from Nexus Memory:")
        print()
        for t in topics:
            print(f"  {t['topic']:25s} ({t['count']} facts)")
        print()
        print(f"Total: {len(topics)} topics with 3+ facts")
        sys.exit(0)

    if not args.skill:
        parser.print_help()
        sys.exit(1)

    file_path, content = export_skill(
        name=args.skill,
        topic=args.topic,
        limit=args.limit,
        output_dir=args.output,
        deploy=args.deploy,
    )

    if not file_path:
        print(f"No canonical facts found for '{args.topic or args.skill}'.")
        sys.exit(1)

    print(f"Skill written to: {file_path}")
    print(f"  {len(content)} bytes, {content.count('1. ')} instructions")
