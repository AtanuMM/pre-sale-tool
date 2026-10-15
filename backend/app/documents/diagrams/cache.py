"""In-process LRU cache for rendered diagrams."""

from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Literal

from app.documents.diagrams.layered import render_layered_png, render_layered_svg
from app.steps.schemas.srs import DiagramSpec

Format = Literal["png", "svg"]
_MAX = 64
_cache: OrderedDict[tuple[str, str, Format], bytes] = OrderedDict()


def render_diagram(
    version_id: uuid.UUID,
    diagram_key: str,
    spec: DiagramSpec,
    fmt: Format,
) -> bytes:
    key = (str(version_id), diagram_key, fmt)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    if spec.kind == "er":
        from app.documents.diagrams.er import render_er_png, render_er_svg

        data = render_er_png(spec) if fmt == "png" else render_er_svg(spec)
    else:
        data = render_layered_png(spec) if fmt == "png" else render_layered_svg(spec)
    _cache[key] = data
    _cache.move_to_end(key)
    while len(_cache) > _MAX:
        _cache.popitem(last=False)
    return data
