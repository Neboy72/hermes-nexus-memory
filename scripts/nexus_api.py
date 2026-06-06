#!/usr/bin/env python3
"""
Nexus Memory v2.7 — assertion_event-API + nexus_resolve Query-API (Phase 5+6)

Phase 5: assertion_event — strukturierte Events schreiben (override, contest, confirm, retract)
Phase 6: nexus_resolve — "warum glauben wir X?" mit voller Provenance-Chain

Usage:
  # Event schreiben (Phase 5)
  python3 nexus_api.py event create --belief bel-primary-provider --type contest --agent "Drift-Cron" --reason "Provider gewechselt"

  # Belief auflösen (Phase 6)
  python3 nexus_api.py resolve bel-primary-provider
  python3 nexus_api.py resolve bel-primary-provider --chain
"""

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

QDRANT_URL = "http://localhost:6333"

# ─── Status ──────────────────────────────────────────────────────────
STATUS_ACTIVE = "ACTIVE"
STATUS_CONTESTED = "CONTESTED"
STATUS_RETRACTED = "RETRACTED"
STATUS_SUPERSEDED = "SUPERSEDED"
STATUS_HISTORICAL = "HISTORICAL"

EVENT_TYPES = {"override", "confirm", "contest", "retract", "supersede"}
ACTOR_TYPES = {"user", "agent", "system", "cron"}


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


def qdrant_put(collection: str, action: str, body: dict) -> dict:
    """Qdrant PUT request (für Points-Upsert)."""
    url = f"{QDRANT_URL}/collections/{collection}/{action}?wait=true"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def next_point_id(collection: str) -> int:
    """Get a unique point ID by hashing current timestamp + random."""
    import hashlib, os
    raw = f"{datetime.now(timezone.utc).isoformat()}-{os.urandom(4).hex()}"
    return int(hashlib.sha256(raw.encode()).hexdigest()[:16], 16)


def get_belief(belief_id: str) -> Optional[dict]:
    result = qdrant_post(
        "nexus_beliefs", "points/scroll",
        {"limit": 1, "with_payload": True, "with_vector": False,
         "filter": {"must": [{"key": "belief_id", "match": {"value": belief_id}}]}},
    )
    points = result.get("result", {}).get("points", [])
    return points[0] if points else None


def get_events_for_belief(belief_id: str) -> list[dict]:
    result = qdrant_post(
        "nexus_events", "points/scroll",
        {"limit": 5000, "with_payload": True, "with_vector": False,
         "filter": {"must": [{"key": "target_belief", "match": {"value": belief_id}}]}},
    )
    points = result.get("result", {}).get("points", [])
    points.sort(key=lambda p: p.get("payload", {}).get("temporal", {}).get("event_time", ""))
    return points


# ═══════════════════════════════════════════════════════════════════════
# Phase 5: assertion_event-API
# ═══════════════════════════════════════════════════════════════════════
def create_event(
    belief_id: str,
    event_type: str,
    assertion: str,
    actor_type: str,
    actor_name: str,
    reason: str = "",
    trust_level: float = 0.0,
    evidence_refs: Optional[list] = None,
    replaces: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """
    Create a new assertion event in nexus_events.
    Returns the event payload.
    """
    now = datetime.now(timezone.utc).isoformat()

    # Auto-trust-level wenn nicht gesetzt
    if trust_level == 0.0:
        trust_map = {"user": 1.0, "agent": 0.5, "system": 0.8, "cron": 0.7}
        trust_level = trust_map.get(actor_type, 0.5)

    event_id = f"aev-{next_point_id('nexus_events'):016x}"

    payload = {
        "event_id": event_id,
        "event_type": event_type,
        "target_belief": belief_id,
        "assertion": assertion,
        "trust_level": trust_level,
        "actor": {
            "type": actor_type,
            "name": actor_name,
            "channel": "system" if actor_type in ("system", "cron") else "api",
        },
        "temporal": {
            "event_time": now,
            "ingested_at": now,
        },
        "reason": reason or f"{actor_type}:{actor_name} — {assertion} on {belief_id}",
        "context": {
            "session_id": None,
            "source": f"api:{actor_type}",
            "message_id": None,
        },
        "evidence_refs": evidence_refs or [],
        "replaces": replaces,
    }

    if dry_run:
        print(f"  📋 DRY RUN — Event würde geschrieben werden:")
        print(f"     event_id: {event_id}")
        print(f"     belief:   {belief_id}")
        print(f"     type:     {event_type}/{assertion}")
        print(f"     actor:    {actor_type}:{actor_name}")
        print(f"     trust:    {trust_level}")
        return payload

    point_id = next_point_id("nexus_events")
    response = qdrant_put(
        "nexus_events", "points",
        {"points": [{"id": point_id, "vector": {}, "payload": payload}]},
    )
    status = response.get("status", "error")
    if status == "ok":
        print(f"  ✅ Event {event_id} geschrieben (point_id={point_id})")
    else:
        print(f"  ❌ Fehler: {response}")

    return payload


def apply_event_to_belief(event: dict, dry_run: bool = False) -> Optional[dict]:
    """
    Apply an event's assertion to the target belief.
    - 'contest' by agent → set CONTESTED
    - 'confirm' by user → set ACTIVE
    - 'override' by user → set ACTIVE + trust=1.0
    - 'retract' → set RETRACTED
    """
    payload = event
    if isinstance(event, dict) and "payload" in event:
        payload = event["payload"]

    belief_id = payload.get("target_belief")
    assertion = payload.get("assertion")
    actor_type = payload.get("actor", {}).get("type")

    bp = get_belief(belief_id)
    if not bp:
        print(f"  ⚠ Belief '{belief_id}' nicht gefunden.")
        return None

    bpayload = bp.get("payload", {})
    point_id = bp.get("id")
    new_payload = dict(bpayload)

    if assertion == "contest" and actor_type == "agent":
        new_payload["status"] = STATUS_CONTESTED
        new_payload["trust"] = 0.3  # contested = niedrig
        print(f"  → {belief_id}: CONTESTED (Agent-Widerspruch)")

    elif assertion == "confirm" and actor_type == "user":
        new_payload["status"] = STATUS_ACTIVE
        new_payload["trust"] = 1.0  # User confirm = volles Vertrauen
        print(f"  → {belief_id}: ACTIVE (User bestätigt)")

    elif assertion == "override" and actor_type == "user":
        new_payload["status"] = STATUS_ACTIVE
        new_payload["trust"] = 1.0
        print(f"  → {belief_id}: ACTIVE (User-Override)")

    elif assertion == "retract":
        new_payload["status"] = STATUS_RETRACTED
        new_payload["trust"] = 0.0
        print(f"  → {belief_id}: RETRACTED")

    else:
        print(f"  ~ {belief_id}: keine Status-Änderung (assertion={assertion}, actor={actor_type})")
        return None

    new_payload["temporal"] = dict(bpayload.get("temporal", {}))
    new_payload["temporal"]["last_modified"] = datetime.now(timezone.utc).isoformat()

    if dry_run:
        print(f"     (DRY RUN — würde Belief updaten)")
        return None

    response = qdrant_post(
        "nexus_beliefs", "points/payload",
        {"payload": new_payload, "points": [point_id]},
    )
    if response.get("status") == "ok":
        print(f"     Belief updated ✅")
    else:
        print(f"     Fehler: {response}")
    return response


# ═══════════════════════════════════════════════════════════════════════
# Phase 6: nexus_resolve Query-API
# ═══════════════════════════════════════════════════════════════════════
def resolve_belief(belief_id: str, show_chain: bool = False) -> dict:
    """
    Löse ein Belief auf: zeige den aktuellen Stand + Provenance-Chain.

    Returns ein Dict mit:
      - belief: aktueller Zustand
      - events: alle zugehörigen Events
      - chain: formatierte Chain für CLI-Output
    """
    bp = get_belief(belief_id)
    if not bp:
        return {"error": f"Belief '{belief_id}' nicht gefunden."}

    bpayload = bp.get("payload", {})
    events = get_events_for_belief(belief_id)

    result = {
        "belief_id": belief_id,
        "status": bpayload.get("status"),
        "trust": bpayload.get("trust"),
        "content": bpayload.get("content", "")[:200],
        "rationale": bpayload.get("rationale", ""),
        "temporal": bpayload.get("temporal", {}),
        "event_count": len(events),
    }

    # Chain formatieren
    lines = []
    lines.append(f"📌 {belief_id}")
    lines.append(f"   Status: {result['status']} | Trust: {result['trust']}")
    lines.append(f"   Inhalt: {result['content']}")
    if result['rationale']:
        lines.append(f"   Rationale: {result['rationale']}")
    lines.append(f"   Temporal: {json.dumps(result['temporal'], default=str)}")
    lines.append(f"   Events: {result['event_count']}")

    if show_chain and events:
        lines.append(f"\n   📜 Provenance-Chain ({len(events)} Events):")
        for i, evt in enumerate(events):
            ep = evt.get("payload", {})
            lines.append(
                f"   [{i+1}] {ep.get('event_type')}/{ep.get('assertion')} "
                f"| actor={ep.get('actor',{}).get('type')}:{ep.get('actor',{}).get('name')} "
                f"| trust={ep.get('trust_level')} "
                f"| {ep.get('reason','')[:80]}"
            )

    result["chain_output"] = "\n".join(lines)
    return result


# ═══════════════════════════════════════════════════════════════════════
# Phase 2: Ingestion Pipeline
# ═══════════════════════════════════════════════════════════════════════
def slugify(text: str) -> str:
    """Erzeuge einen URL-sicheren Slug aus Text."""
    import re
    s = text.lower().strip()
    s = re.sub(r'[^a-z0-9\s-]', '', s)
    s = re.sub(r'[\s-]+', '-', s)
    return s[:60]


def ingest_fact(
    content: str,
    source_type: str = "chat",
    source_name: str = "Kiosha",
    rationale: str = "",
    trust_override: Optional[float] = None,
    belief_id: Optional[str] = None,
    evidence_refs: Optional[list] = None,
    write_wiki: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Ingestion Pipeline (Phase 2):
    Nimmt einen Fakt auf, legt Belief + Event an, triggert Trust-Recompute.

    1. Belief-ID generieren oder existierende prüfen
    2. Belief in nexus_beliefs anlegen/updaten (content, trust, rationale, temporal)
    3. Assertion-Event in nexus_events schreiben
    4. Trust wird über max(events.trust_level) gesteuert

    Returns: {"belief_id": str, "event_id": str, "status": str}
    """
    now = datetime.now(timezone.utc).isoformat()

    # Belief-ID bestimmen
    bid = belief_id or f"bel-{slugify(content[:80])}"
    if not bid.startswith("bel-"):
        bid = f"bel-{bid}"

    # Trust bestimmen
    trust_map = {"chat": 1.0, "cron": 0.8, "web": 0.7, "manual": 0.9,
                 "config": 0.8, "system": 0.8, "ingest": 0.9, "legacy": 0.3}
    trust = trust_override if trust_override is not None else trust_map.get(source_type, 0.5)

    # Prüfen ob Belief existiert
    existing = get_belief(bid)

    if existing:
        # Bestehendes Belief updaten
        ep = existing.get("payload", {})
        ep_id = existing.get("id")
        evidence = ep.get("evidences", [])
        evidence.append({
            "source_id": f"src-{source_type}-{next_point_id('nexus_beliefs'):016x}",
            "source_type": source_type,
            "captured_at": now,
            "trust_contribution": trust,
        })
        # Trust = max aller evidence.trust_contribution
        max_trust = max(e.get("trust_contribution", 0.0) for e in evidence)

        new_payload = dict(ep)
        new_payload["content"] = content
        new_payload["trust"] = max_trust
        new_payload["evidences"] = evidence
        new_payload["rationale"] = rationale or ep.get("rationale", "")
        new_payload["temporal"]["last_modified"] = now
        new_payload["provenance_trail"] = ep.get("provenance_trail", [])
        new_payload["provenance_trail"].append({
            "event": "updated",
            "by": source_name,
            "at": now,
            "source": source_type,
        })

        if not dry_run:
            response = qdrant_post(
                "nexus_beliefs", "points/payload",
                {"payload": new_payload, "points": [ep_id]},
            )
            if response.get("status") != "ok":
                return {"error": f"Belief-Update fehlgeschlagen: {response}"}
            print(f"  🔄 Belief existiert — trust={max_trust}")
    else:
        # Neues Belief anlegen
        belief_point_id = next_point_id("nexus_beliefs")
        belief_payload = {
            "belief_id": bid,
            "content": content,
            "status": STATUS_ACTIVE,
            "trust": trust,
            "evidences": [{
                "source_id": f"src-{source_type}-{belief_point_id:016x}",
                "source_type": source_type,
                "captured_at": now,
                "trust_contribution": trust,
            }],
            "temporal": {
                "event_time": now,
                "ingested_at": now,
                "valid_until": None,
                "is_open": True,
            },
            "rationale": rationale or f"via {source_name} ({source_type})",
            "provenance_trail": [{
                "event": "created",
                "by": source_name,
                "at": now,
                "source": source_type,
            }],
        }

        if not dry_run:
            response = qdrant_put(
                "nexus_beliefs", "points",
                {"points": [{"id": belief_point_id, "vector": {}, "payload": belief_payload}]},
            )
            if response.get("status") != "ok":
                return {"error": f"Belief-Erstellung fehlgeschlagen: {response}"}
            print(f"  ✅ Belief {bid} erstellt (trust={trust})")

    # Event schreiben
    event = create_event(
        belief_id=bid,
        event_type="assertion",
        assertion="confirm",
        actor_type="system" if source_type in ("system", "cron", "config") else source_type,
        actor_name=source_name,
        reason=rationale or f"Ingested via {source_name} ({source_type})",
        trust_level=trust,
        evidence_refs=evidence_refs or [],
        dry_run=dry_run,
    )

    # Write-Through ins Wiki
    if write_wiki and not dry_run:
        wiki_path = f"/Users/miosha/ObsidianVault/NexusVault/Kiosha/Wiki/beliefs/{bid}.md"
        import os
        os.makedirs(os.path.dirname(wiki_path), exist_ok=True)
        with open(wiki_path, "w") as f:
            f.write(f"---\nbelief_id: {bid}\ntrust: {trust}\nstatus: ACTIVE\nsource: {source_type}\ncreated: {now}\n---\n\n# {content}\n\n{rationale}\n\n## Provenance\n- **Ingested by:** {source_name}\n- **Source:** {source_type}\n- **Trust:** {trust}\n- **Time:** {now}\n")
        print(f"  📝 Wiki: beliefs/{bid}.md")

    return {
        "belief_id": bid,
        "event_id": event.get("event_id", "?"),
        "status": "created" if not existing else "updated",
        "trust": trust,
    }


# CLI
def main():
    parser = argparse.ArgumentParser(description="Nexus Memory v2.7 — API (Phase 5+6)")
    sub = parser.add_subparsers(dest="command")

    # ── event ────────────────────────────────────────────────────────
    evt = sub.add_parser("event", help="Phase 5: Events verwalten")
    evt_sub = evt.add_subparsers(dest="subcommand")

    evt_create = evt_sub.add_parser("create", help="Neues Assertion-Event erstellen")
    evt_create.add_argument("--belief", required=True, help="Belief-ID")
    evt_create.add_argument("--type", required=True, choices=EVENT_TYPES, help="Event-Typ")
    evt_create.add_argument("--assertion", default="confirm", help="Assertion (default: confirm)")
    evt_create.add_argument("--actor-type", default="agent", choices=ACTOR_TYPES, help="Actor-Typ")
    evt_create.add_argument("--actor-name", default="API", help="Actor-Name")
    evt_create.add_argument("--reason", default="", help="Begründung")
    evt_create.add_argument("--trust", type=float, default=0.0, help="Trust-Level (optional)")
    evt_create.add_argument("--dry-run", action="store_true", help="Nur anzeigen")
    evt_create.add_argument("--apply", action="store_true", help="Event sofort auf Belief anwenden")

    # ── resolve ──────────────────────────────────────────────────────
    res = sub.add_parser("resolve", help="Phase 6: Belief auflösen")
    res.add_argument("belief_id", help="Belief-ID")
    res.add_argument("--chain", action="store_true", help="Volle Provenance-Chain zeigen")
    res.add_argument("--json", action="store_true", help="Als JSON ausgeben")

    # ── ingest ───────────────────────────────────────────────────────
    ing = sub.add_parser("ingest", help="Phase 2: Fakt aufnehmen (Ingestion Pipeline)")
    ing.add_argument("--content", required=True, help="Fakt-Inhalt")
    ing.add_argument("--source-type", default="chat", choices=("chat","cron","web","manual","config","system","legacy"), help="Quell-Typ")
    ing.add_argument("--source-name", default="Kiosha", help="Quell-Name (z.B. Agent-Name)")
    ing.add_argument("--rationale", default="", help="Begründung")
    ing.add_argument("--trust", type=float, default=None, help="Trust-Level überschreiben")
    ing.add_argument("--belief-id", default=None, help="Belief-ID erzwingen")
    ing.add_argument("--wiki", action="store_true", help="Write-Through ins Wiki")
    ing.add_argument("--dry-run", action="store_true", help="Nur anzeigen")

    args = parser.parse_args()

    if args.command == "event":
        if args.subcommand == "create":
            event = create_event(
                belief_id=args.belief,
                event_type=args.type,
                assertion=args.assertion,
                actor_type=args.actor_type,
                actor_name=args.actor_name,
                reason=args.reason,
                trust_level=args.trust,
                dry_run=args.dry_run,
            )
            if args.apply and not args.dry_run and event:
                print("   → Wende Event auf Belief an...")
                apply_event_to_belief(event)
        else:
            print("Verfügbar: nexus_api.py event create --help")

    elif args.command == "ingest":
        result = ingest_fact(
            content=args.content,
            source_type=args.source_type,
            source_name=args.source_name,
            rationale=args.rationale,
            trust_override=args.trust,
            belief_id=args.belief_id,
            write_wiki=args.wiki,
            dry_run=args.dry_run,
        )
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        mode = " (DRY RUN)" if args.dry_run else ""
        print(f"\n📊 Ergebnis{mode}: {result['belief_id']} — {result['status']} (trust={result['trust']})")

    elif args.command == "resolve":
        result = resolve_belief(args.belief_id, show_chain=args.chain)
        if "error" in result:
            print(f"❌ {result['error']}")
            sys.exit(1)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            print(result["chain_output"])

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
