#!/usr/bin/env python3
"""
Nexus Memory v2.7 — Trust-Recompute Service (Phase 3)

Rechnet den trust-Wert für Beliefs neu basierend auf Events.
Trust-Aggregation: max() über alle evidence.trust_contribution.
Agent-Governance: Agent-Events setzen CONTESTED, User-Events bestätigen → ACTIVE.

Usage:
  # Einzelnes Belief recomputen
  python3 trust_recompute.py --belief bel-primary-provider

  # Full-Scan aller Beliefs
  python3 trust_recompute.py --all

  # Dry-Run (nur anzeigen, nichts schreiben)
  python3 trust_recompute.py --all --dry-run

  # Nur CONTESTED-Beliefs prüfen (User-Governance)
  python3 trust_recompute.py --check-governance
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

QDRANT_URL = "http://localhost:6333"

# ─── Status-Enum ─────────────────────────────────────────────────────
STATUS_ACTIVE = "ACTIVE"
STATUS_SUPERSEDED = "SUPERSEDED"
STATUS_CONTESTED = "CONTESTED"
STATUS_RETRACTED = "RETRACTED"
STATUS_HISTORICAL = "HISTORICAL"

# ─── Trust-Levels ────────────────────────────────────────────────────
TRUST_MAP = {
    "chat": 1.0,
    "ingest": 0.9,
    "cron": 0.8,
    "manual": 0.7,
    "inferred": 0.5,
    "unknown": 0.3,
    "legacy": 0.3,
    "config": 0.8,
}


# ─── Qdrant Helpers ──────────────────────────────────────────────────
def qdrant_post(collection: str, action: str, body: dict) -> dict:
    url = f"{QDRANT_URL}/collections/{collection}/{action}"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def qdrant_get(collection: str, action: str, params: str = "") -> dict:
    url = f"{QDRANT_URL}/collections/{collection}/{action}{params}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def scroll_all(
    collection: str, filter_: Optional[dict] = None, limit: int = 100
) -> list[dict]:
    """Scroll through ALL points in a collection, handling pagination."""
    points = []
    offset = None
    while True:
        body: dict[str, Any] = {
            "limit": limit,
            "with_payload": True,
            "with_vector": False,
        }
        if filter_:
            body["filter"] = filter_
        if offset is not None:
            body["offset"] = offset

        result = qdrant_post(collection, "points/scroll", body)
        page = result.get("result", {})
        batch = page.get("points", [])
        points.extend(batch)

        next_offset = page.get("next_page_offset")
        if next_offset is None:
            break
        offset = next_offset

    return points


def get_belief(belief_id: str) -> Optional[dict]:
    """Get a single belief by belief_id (payload keyword filter)."""
    result = qdrant_post(
        "nexus_beliefs",
        "points/scroll",
        {
            "limit": 1,
            "with_payload": True,
            "with_vector": False,
            "filter": {
                "must": [{"key": "belief_id", "match": {"value": belief_id}}]
            },
        },
    )
    points = result.get("result", {}).get("points", [])
    return points[0] if points else None


def get_events_for_belief(belief_id: str) -> list[dict]:
    """Get all events targeting a belief_id, ordered by temporal.event_time."""
    result = qdrant_post(
        "nexus_events",
        "points/scroll",
        {
            "limit": 5000,
            "with_payload": True,
            "with_vector": False,
            "filter": {
                "must": [
                    {"key": "target_belief", "match": {"value": belief_id}}
                ]
            },
        },
    )
    points = result.get("result", {}).get("points", [])

    # Sort by event_time ascending
    points.sort(
        key=lambda p: p.get("payload", {}).get("temporal", {}).get(
            "event_time", ""
        )
    )
    return points


def update_belief(
    point_id: int, payload: dict, dry_run: bool = False
) -> Optional[dict]:
    """Update a belief point's payload. Returns response or None if dry_run."""
    if dry_run:
        return None
    return qdrant_post(
        "nexus_beliefs",
        "points/payload",
        {"payload": payload, "points": [point_id]},
    )


# ─── Core Logic ──────────────────────────────────────────────────────
def compute_trust(events: list[dict], belief: dict) -> tuple[float, str, str]:
    """
    Compute new trust value and status for a belief based on its events.

    Returns: (new_trust, new_status, reason)
    """
    payload = belief.get("payload", {})
    current_status = payload.get("status", STATUS_ACTIVE)

    # 1. Trust aggregation: max trust_level from events
    trust_values = []
    for evt in events:
        ep = evt.get("payload", {})
        tl = ep.get("trust_level", 0.0)
        if tl is not None:
            trust_values.append(float(tl))

    new_trust = max(trust_values) if trust_values else payload.get("trust", 0.3)

    # 2. Governance check: determine status
    has_agent_contest = any(
        e.get("payload", {}).get("assertion") == "contest"
        and e.get("payload", {}).get("actor", {}).get("type") == "agent"
        for e in events
    )
    has_user_confirm = any(
        e.get("payload", {}).get("assertion") == "confirm"
        and e.get("payload", {}).get("actor", {}).get("type") == "user"
        for e in events
    )
    has_user_override = any(
        e.get("payload", {}).get("assertion") == "override"
        and e.get("payload", {}).get("actor", {}).get("type") == "user"
        for e in events
    )
    has_retraction = any(
        e.get("payload", {}).get("assertion") == "retract" for e in events
    )

    if has_retraction:
        new_status = STATUS_RETRACTED
        reason = "Retracted by event"
    elif has_user_override:
        new_status = STATUS_ACTIVE
        reason = "User override confirmed"
    elif has_user_confirm:
        new_status = STATUS_ACTIVE
        reason = "User confirmed belief"
    elif has_agent_contest and not has_user_confirm:
        new_status = STATUS_CONTESTED
        reason = "Contested by agent, awaiting user confirmation"
    elif current_status == STATUS_CONTESTED and not has_user_confirm:
        new_status = STATUS_CONTESTED
        reason = "Still contested, no user confirmation yet"
    else:
        new_status = STATUS_ACTIVE
        reason = "Trust recomputed, no contestation"

    return new_trust, new_status, reason


def recompute_belief(
    belief_point: dict, dry_run: bool = False
) -> Optional[dict]:
    """
    Recompute trust + status for a single belief point.

    Returns the update response or None if no change / dry_run.
    """
    payload = belief_point.get("payload", {})
    belief_id = payload.get("belief_id", "unknown")
    point_id = belief_point.get("id")

    if not point_id:
        print(f"  ⚠ {belief_id}: no point_id, skipping")
        return None

    events = get_events_for_belief(belief_id)
    new_trust, new_status, reason = compute_trust(events, belief_point)

    old_trust = payload.get("trust", 0.0)
    old_status = payload.get("status", STATUS_ACTIVE)

    if abs(new_trust - old_trust) < 0.001 and new_status == old_status:
        print(
            f"  ~ {belief_id}: trust={old_trust} status={old_status} — unchanged"
        )
        return None

    print(
        f"  {'→' if not dry_run else '?'} {belief_id}: "
        f"trust {old_trust}→{new_trust}, "
        f"status {old_status}→{new_status} "
        f"({reason})"
    )

    if dry_run:
        return None

    new_payload = dict(payload)
    new_payload["trust"] = new_trust
    new_payload["status"] = new_status
    new_payload["temporal"] = dict(payload.get("temporal", {}))
    new_payload["temporal"]["last_recomputed"] = datetime.now(
        timezone.utc
    ).isoformat()

    return update_belief(point_id, new_payload, dry_run=False)


def check_governance(dry_run: bool = False) -> int:
    """
    Check ALL beliefs with status=CONTESTED.
    If user has since confirmed → set ACTIVE.

    Returns count of beliefs updated.
    """
    print("\n🔍 Governance-Check: CONTESTED-Beliefs prüfen...")
    beliefs = scroll_all(
        "nexus_beliefs",
        filter_={
            "must": [{"key": "status", "match": {"value": STATUS_CONTESTED}}]
        },
    )

    if not beliefs:
        print("  Keine CONTESTED-Beliefs gefunden.")
        return 0

    updated = 0
    for bp in beliefs:
        bid = bp.get("payload", {}).get("belief_id", "?")
        events = get_events_for_belief(bid)
        has_user_confirm = any(
            e.get("payload", {}).get("assertion") == "confirm"
            and e.get("payload", {}).get("actor", {}).get("type") == "user"
            for e in events
        )
        if has_user_confirm:
            result = recompute_belief(bp, dry_run=dry_run)
            if result is not None:
                updated += 1

    return updated


def recompute_all(dry_run: bool = False) -> tuple[int, int]:
    """
    Full-Scan: recompute trust for ALL beliefs.

    Returns (total_processed, total_updated).
    """
    print("\n🔁 Full-Scan: Trust-Recompute für ALLE Beliefs...")
    beliefs = scroll_all("nexus_beliefs", limit=200)
    print(f"  {len(beliefs)} Beliefs gefunden.\n")

    processed = 0
    updated = 0
    for bp in beliefs:
        result = recompute_belief(bp, dry_run=dry_run)
        processed += 1
        if result is not None:
            updated += 1

    return processed, updated


# ─── CLI ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Nexus Memory v2.7 — Trust-Recompute Service (Phase 3)"
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--belief",
        type=str,
        help="Belief-ID für Einzel-Recompute (z.B. bel-primary-provider)",
    )
    group.add_argument(
        "--all",
        action="store_true",
        help="Full-Scan: Trust für ALLE Beliefs neu berechnen",
    )
    group.add_argument(
        "--check-governance",
        action="store_true",
        help="Nur CONTESTED-Beliefs prüfen (Agent-Governance)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Nur anzeigen, nichts schreiben",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Status der Collections anzeigen und beenden",
    )

    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if args.belief:
        print(f"\n🎯 Einzel-Recompute: {args.belief}")
        bp = get_belief(args.belief)
        if not bp:
            print(f"  ❌ Belief '{args.belief}' nicht gefunden.")
            sys.exit(1)
        result = recompute_belief(bp, dry_run=args.dry_run)
        if result:
            print(f"  ✅ Belief '{args.belief}' aktualisiert.")
        return

    if args.all:
        processed, updated = recompute_all(dry_run=args.dry_run)
        mode = " (DRY RUN)" if args.dry_run else ""
        print(f"\n📊 Ergebnis{mode}: {processed} verarbeitet, {updated} aktualisiert.")
        return

    if args.check_governance:
        updated = check_governance(dry_run=args.dry_run)
        mode = " (DRY RUN)" if args.dry_run else ""
        print(f"\n📊 Governance-Check{mode}: {updated} Beliefs aktualisiert.")
        return

    # Default: show help
    parser.print_help()


def show_status():
    """Zeigt Status der Collections an."""
    print("\n📊 Nexus Memory v2.7 — Collection-Status")
    for coll in ["nexus_beliefs", "nexus_events"]:
        try:
            info = qdrant_get(coll, "")
            result = info.get("result", {})
            count = result.get("points_count", "?")
            status = result.get("status", "?")
            print(f"\n  {coll}: {count} Points, status={status}")
        except Exception as e:
            print(f"\n  {coll}: ❌ {e}")


if __name__ == "__main__":
    main()
