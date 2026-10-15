"""Matplotlib layered architecture diagram renderer (deterministic, greyscale-safe)."""

from __future__ import annotations

from io import BytesIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from app.documents.diagrams.sanitize import sanitize_label
from app.steps.schemas.srs import DiagramSpec

# A4 text width ~16 cm at 200 dpi
PNG_WIDTH_PX = 1260
DPI = 200


def _figsize_inches() -> tuple[float, float]:
    return PNG_WIDTH_PX / DPI, 6.0


def render_layered_png(spec: DiagramSpec) -> bytes:
    fig, ax = plt.subplots(figsize=_figsize_inches(), dpi=DPI)
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")
    lanes = sorted(spec.lanes, key=lambda lane: lane.order) if spec.lanes else []
    if not lanes:
        lanes = [type("L", (), {"name": "default", "order": 0})()]  # type: ignore[misc]
    lane_h = 8.0 / max(len(lanes), 1)
    lane_y: dict[str, float] = {}
    for index, lane in enumerate(lanes):
        y0 = 9 - (index + 1) * lane_h
        ax.add_patch(
            FancyBboxPatch(
                (0.2, y0),
                9.6,
                lane_h - 0.2,
                boxstyle="round,pad=0.02",
                linewidth=0.8,
                edgecolor="#666666",
                facecolor="#f0f0f0",
            )
        )
        ax.text(0.3, y0 + lane_h - 0.35, sanitize_label(lane.name, max_len=40), fontsize=8)
        lane_y[lane.name] = y0 + lane_h / 2

    nodes = spec.nodes or []
    for idx, node in enumerate(nodes):
        y = lane_y.get(node.lane, 5.0)
        x = 1.0 + (idx % 5) * 1.7
        if idx >= 5:
            y -= 0.8
        ax.add_patch(
            FancyBboxPatch(
                (x, y - 0.35),
                1.5,
                0.7,
                boxstyle="round,pad=0.02",
                linewidth=1.0,
                edgecolor="#333333",
                facecolor="#ffffff",
            )
        )
        ax.text(
            x + 0.05,
            y,
            sanitize_label(node.label, max_len=40),
            fontsize=7,
            va="center",
        )
        ax.text(x + 0.05, y - 0.25, sanitize_label(node.node_type, max_len=20), fontsize=5, color="#555555")

    pos = {n.id: (1.0 + (i % 5) * 1.7, lane_y.get(n.lane, 5.0)) for i, n in enumerate(nodes)}
    for edge in spec.edges:
        if edge.from_id in pos and edge.to_id in pos:
            x1, y1 = pos[edge.from_id]
            x2, y2 = pos[edge.to_id]
            ax.annotate(
                "",
                xy=(x2, y2),
                xytext=(x1 + 0.75, y1),
                arrowprops={"arrowstyle": "->", "color": "#444444", "lw": 0.8},
            )
            if edge.label:
                ax.text((x1 + x2) / 2, (y1 + y2) / 2, sanitize_label(edge.label, max_len=30), fontsize=6)

    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=DPI, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def render_layered_svg(spec: DiagramSpec) -> bytes:
    fig, ax = plt.subplots(figsize=_figsize_inches())
    ax.text(0.5, 0.5, sanitize_label(spec.title, max_len=120), ha="center", fontsize=10)
    ax.axis("off")
    buf = BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()
