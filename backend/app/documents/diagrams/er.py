"""ER diagram renderer (matplotlib)."""

from __future__ import annotations

from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from app.documents.diagrams.layered import DPI, PNG_WIDTH_PX, _figsize_inches
from app.documents.diagrams.sanitize import sanitize_label
from app.steps.schemas.srs import DiagramSpec


def render_er_png(spec: DiagramSpec) -> bytes:
    fig, ax = plt.subplots(figsize=_figsize_inches(), dpi=DPI)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    entities = spec.entities or []
    for idx, ent in enumerate(entities):
        x = 0.5 + (idx % 3) * 3.0
        y = 8.0 - (idx // 3) * 2.5
        lines = [sanitize_label(ent.name, max_len=60)]
        for attr in ent.attributes[:12]:
            mark = " *" if attr.startswith(ent.primary_key) or ent.primary_key in attr else ""
            lines.append(sanitize_label(attr, max_len=40) + mark)
        height = 0.35 + len(lines) * 0.25
        ax.add_patch(
            FancyBboxPatch(
                (x, y - height),
                2.5,
                height,
                boxstyle="round,pad=0.02",
                linewidth=0.8,
                edgecolor="#333333",
                facecolor="#ffffff",
            )
        )
        for li, line in enumerate(lines):
            ax.text(x + 0.1, y - 0.2 - li * 0.25, line, fontsize=6)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def render_er_svg(spec: DiagramSpec) -> bytes:
    fig, ax = plt.subplots(figsize=(PNG_WIDTH_PX / DPI, 4))
    ax.text(0.5, 0.5, sanitize_label(spec.title, max_len=120), ha="center")
    ax.axis("off")
    buf = BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
