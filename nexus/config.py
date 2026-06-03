"""Nexus Memory — zentrale Konfiguration.

Sammelt Konstanten, die sonst als Magic Strings in vielen Modulen verteilt wären.
"""

import os
from typing import Optional

DEFAULT_COLLECTION: Optional[str] = None
"""Fallback-Collection-Name wenn kein expliziter Wert übergeben wird.
None = zwingt Aufrufer zur Angabe (ValueError wenn weder Parameter noch ENV).
"""


def get_collection(override: Optional[str] = None) -> str:
    """Ermittelt den effektiven Collection-Namen.

    Priorität:
    1. override-Parameter (explizit vom Aufrufer)
    2. $NEXUS_COLLECTION Umgebungsvariable
    3. DEFAULT_COLLECTION (Config-Wert, aktuell None)
    4. → ValueError
    """
    if override:
        return override

    env_collection = os.environ.get("NEXUS_COLLECTION")
    if env_collection:
        return env_collection

    if DEFAULT_COLLECTION is not None:
        return DEFAULT_COLLECTION

    raise ValueError(
        "Kein Collection-Name angegeben. "
        "Übergib collection_name=<name> oder setze $NEXUS_COLLECTION."
    )
