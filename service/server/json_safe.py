"""NaN/Inf scrubbing for anything that becomes a JSON response body.

Python's json module accepts NaN/Infinity on both ends by default: json.dumps
writes the bare literal `NaN` and json.loads reads it straight back as a float.
Starlette's JSONResponse renders with allow_nan=False, so one NaN anywhere in a
payload raises ValueError and the endpoint 500s — and when the NaN has already
been persisted that is a permanent 500, not a blip.

null is the correct wire value for a number that could not be computed.
"""

from __future__ import annotations

import math
from typing import Any


def json_safe(obj: Any) -> Any:
    """Recursively replace non-finite floats with None."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_safe(v) for v in obj]
    return obj
