"""Nexus Memory — central configuration.

Collects constants that would otherwise be scattered as magic strings
across multiple modules.
"""

import os
from typing import Optional

DEFAULT_COLLECTION: Optional[str] = None
"""Fallback collection name when no explicit value is passed.
None forces the caller to provide one (ValueError if neither param nor ENV).
"""


def get_collection(override: Optional[str] = None) -> str:
    """Resolve the effective collection name.

    Priority:
    1. override parameter (explicit caller value)
    2. $NEXUS_COLLECTION environment variable
    3. DEFAULT_COLLECTION (config value, currently None)
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
        "No collection name specified. "
        "Pass collection_name=<name> or set $NEXUS_COLLECTION."
    )
