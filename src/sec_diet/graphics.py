"""Typography and vector export for the study's scientific figures."""

from pathlib import Path

import matplotlib.pyplot as plt


def configure() -> None:
    plt.rcParams.update({
        "font.family": "serif", "font.serif": ["STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix", "font.size": 16, "axes.labelsize": 16,
        "xtick.labelsize": 16, "ytick.labelsize": 16, "legend.fontsize": 16,
        "pdf.fonttype": 42, "svg.fonttype": "none", "savefig.dpi": 300,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.linewidth": 0.8, "figure.facecolor": "white", "axes.facecolor": "white",
    })


def export(figure, path: Path, *, bbox_inches="tight") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for suffix in (".pdf", ".svg"):
        figure.savefig(path.with_suffix(suffix), bbox_inches=bbox_inches, facecolor="white")
    svg = path.with_suffix(".svg")
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines()) + "\n", encoding="utf-8")
