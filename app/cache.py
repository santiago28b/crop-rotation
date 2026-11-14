"""
Tiny on-disk JSON cache for external API calls.

Every upstream service we use (NASA POWER, CropScape, SoilGrids, SSURGO) is slow or flaky
at times. Caching by (service, rounded coordinates, params) means the demo loads instantly
the second time and a flaky service can't break a live demo.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.config import CACHE_DIR


def _key(service: str, params: dict[str, Any]) -> Path:
    blob = json.dumps(params, sort_keys=True, default=str)
    digest = hashlib.sha1(blob.encode()).hexdigest()[:16]
    return CACHE_DIR / service / f"{digest}.json"


def get(service: str, params: dict[str, Any]) -> Any | None:
    path = _key(service, params)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            path.unlink(missing_ok=True)
    return None


def put(service: str, params: dict[str, Any], value: Any) -> None:
    path = _key(service, params)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, default=str))
