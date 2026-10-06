"""PNG charts of the comparison report (matplotlib).

Colour rules (dataviz method): categorical hues in a fixed order (blue, orange, aqua,
yellow, magenta, green, violet, red), at most eight series, a legend whenever there are two
or more series, value labels only while they stay readable, one value axis, quiet grid.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .report import DAYS, FORM, SEC, TYPE, WELL, _order, _prepare, section_label  # noqa: E402

SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SURFACE, INK, INK2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df"
OTHER = "#9a9993"


def _style(ax, title: str, ylabel: str, xlabel: str = "Hole Section") -> None:
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=13, color=INK, fontweight="bold", pad=26)
    ax.set_ylabel(ylabel, color=INK2)
    ax.set_xlabel(xlabel, color=INK2)
    ax.tick_params(colors=INK2, length=0)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)


def _grouped_bars(ax, cats, series: dict[str, list[float]], labels: bool) -> None:
    n = max(len(series), 1)
    width = 0.8 / n
    x = np.arange(len(cats))
    for i, (name, vals) in enumerate(series.items()):
        vals = np.array(vals, dtype=float)
        xs = x - 0.4 + width * (i + 0.5)
        bars = ax.bar(xs, vals, width * 0.9, label=name, color=SERIES[i % len(SERIES)], linewidth=0)
        if labels:
            for xx, v in zip(xs, vals):
                if not np.isnan(v):
                    ax.text(xx, v, f"{v:.2f}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x, cats)
    top = np.nanmax([np.nanmax(np.array(v, dtype=float)) for v in series.values()] or [1.0])
    ax.set_ylim(0, top * 1.15)
    if n >= 2:
        _legend(ax, n)


def _legend(ax, n: int) -> None:
    """Legend below the plot so it never covers bars or labels."""
    ax.legend(frameon=False, labelcolor=INK2, ncol=min(n, 5), loc="upper center", bbox_to_anchor=(0.5, -0.16))


def _save(fig, path: Path, rect=None) -> Path:
    fig.tight_layout(rect=rect)
    fig.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(fig)
    return path


def render_all(tables: dict[str, pd.DataFrame], t: dict[str, pd.DataFrame], out_dir: Path, p: dict) -> list[Path]:
    files: list[Path] = []
    max_series = int(p.get("max_series", 8))

    # ---- slide 6: Approach I - duration by well & hole section
    wide = tables["Approach I by Well"].set_index(SEC)
    wells = list(wide.columns)
    if len(wells) > max_series:  # keep the wells that completed most sections, then the fastest ones
        score = sorted(wells, key=lambda w: (-wide[w].notna().sum(), wide[w].sum(skipna=True)))
        wells = score[:max_series]
    fig, ax = plt.subplots(figsize=(11, 5.6))
    _grouped_bars(ax, list(wide.index), {w: wide[w].tolist() for w in wells}, labels=len(wells) * len(wide) <= 40)
    _style(ax, "Approach I - Duration by Well & Hole Section", "Duration (days)")
    files.append(_save(fig, out_dir / "slide06_approach1_by_well.png"))

    comp = tables["All Approaches"]
    cats = comp[SEC].tolist()

    # ---- slide 7: Approach I vs II
    fig, ax = plt.subplots(figsize=(10, 5.4))
    _grouped_bars(ax, cats, {"Approach I": comp["Approach I"].tolist(), "Approach II": comp["Approach II"].tolist()}, True)
    _style(ax, "Approach I vs. Approach II (Minimum Duration by Hole Section)", "Duration (days)")
    files.append(_save(fig, out_dir / "slide07_approach1_vs_2.png"))

    # ---- slide 9: all approaches
    fig, ax = plt.subplots(figsize=(10, 5.4))
    _grouped_bars(ax, cats, {c: comp[c].tolist() for c in ("Approach I", "Approach II", "Approach Combination")}, True)
    tot = tables["Comparison"].iloc[-1]
    ax.text(0.0, 1.015, f"Total:  I {tot['Approach I']:.2f}  |  II {tot['Approach II']:.2f}  |  "
            f"Combination {tot['Approach Combination']:.2f} days", transform=ax.transAxes, va="bottom", color=INK2, fontsize=9)
    _style(ax, "Duration by Hole Section - All Approaches", "Duration (days)")
    files.append(_save(fig, out_dir / "slide09_all_approaches.png"))

    # ---- extra: heat map of every well x hole section (all wells, no series cap)
    full = wide.copy()
    if len(full) and full.shape[1]:
        fig, ax = plt.subplots(figsize=(1.2 * len(full) + 3, 0.45 * len(full.columns) + 2.5))
        data = full.T.to_numpy(dtype=float)
        im = ax.imshow(data, cmap="Blues", aspect="auto")
        ax.set_xticks(range(len(full)), list(full.index), color=INK2)
        ax.set_yticks(range(len(full.columns)), list(full.columns), color=INK2)
        best = np.nanargmin(np.where(np.isnan(data), np.inf, data), axis=0)
        for r in range(data.shape[0]):
            for c in range(data.shape[1]):
                v = data[r, c]
                if not np.isnan(v):
                    dark = v > np.nanmax(data) * 0.55
                    ax.text(c, r, f"{v:.1f}", ha="center", va="center", fontsize=8, color="white" if dark else INK,
                            fontweight="bold" if best[c] == r else "normal")
        fig.suptitle("Duration by Well & Hole Section (days)", x=0.01, ha="left", fontsize=13, color=INK, fontweight="bold")
        ax.set_title("bold = Approach I minimum", loc="left", fontsize=9, color=INK2, pad=6)
        fig.colorbar(im, ax=ax, label="days", shrink=0.8)
        for sp in ax.spines.values():
            sp.set_visible(False)
        ax.tick_params(length=0)
        files.append(_save(fig, out_dir / "extra_heatmap_well_vs_section.png", rect=[0, 0, 1, 0.94]))

    # ---- extra: best (Approach I) well per section, stacked by formation
    s = _prepare(t["sections"], p)
    order = _order(s["code4"])
    winners = tables["Approach I winners"].set_index(SEC)["Best Well (Approach I)"]
    rows = []
    for code in order:
        w = winners.get(section_label(code))
        sub = s[(s["code4"] == code) & (s["wellname"] == w)].groupby("formname")["days"].sum()
        for fm, d in sub.items():
            rows.append((section_label(code), str(fm).title(), d))
    if rows:
        st = pd.DataFrame(rows, columns=[SEC, FORM, "d"]).pivot_table(index=SEC, columns=FORM, values="d", aggfunc="sum")
        st = st.reindex([section_label(c) for c in order])
        top = st.sum().sort_values(ascending=False)
        keep = list(top.index[: max_series - 1]) if len(top) > max_series else list(top.index)
        if len(top) > max_series:
            st["Other"] = st.drop(columns=keep).sum(axis=1)
            st = st[keep + ["Other"]]
        else:
            st = st[keep]
        fig, ax = plt.subplots(figsize=(10, 5.6))
        bottom = np.zeros(len(st))
        for i, col in enumerate(st.columns):
            vals = st[col].fillna(0).to_numpy()
            colr = OTHER if col == "Other" else SERIES[i % len(SERIES)]
            ax.bar(st.index, vals, 0.55, bottom=bottom, label=col, color=colr, edgecolor=SURFACE, linewidth=1.5)
            bottom += vals
        for x, (lab, tot_) in enumerate(zip(st.index, bottom)):
            ax.text(x, tot_, f"{winners.get(lab)}\n{tot_:.2f} d", ha="center", va="bottom", fontsize=8, color=INK2)
        _style(ax, "Approach I best well per hole section - duration by formation", "Duration (days)")
        ax.set_ylim(0, max(bottom.max() * 1.2, 1))
        _legend(ax, len(st.columns))
        files.append(_save(fig, out_dir / "extra_best_well_by_formation.png"))

    # ---- extra: JR vs SPH minimum per hole section
    per = s.groupby(["wellname", "code4", "category"], dropna=False)["days"].sum().reset_index()
    cat_min = per.groupby(["code4", "category"])["days"].min().unstack("category").reindex(order)
    if cat_min.shape[1] >= 1:
        fig, ax = plt.subplots(figsize=(10, 5.4))
        _grouped_bars(ax, [section_label(c) for c in cat_min.index],
                      {str(c): cat_min[c].tolist() for c in cat_min.columns}, True)
        _style(ax, "Minimum duration by hole section and well type", "Duration (days)")
        files.append(_save(fig, out_dir / "extra_min_by_well_type.png"))

    # ---- slide 14: example parameter sheet
    pr = tables["Drilling Parameters II"]
    if len(pr):
        ex = p.get("example", {}) or {}
        sel = pr
        for key, col in (("well", WELL), ("hole_section", SEC), ("formation", FORM)):
            if ex.get(key):
                sel = sel[sel[col].astype(str) == (section_label(ex[key]) if key == "hole_section" else str(ex[key]).title() if key == "formation" else str(ex[key]))]
        if ex.get("date"):
            sel = sel[sel["Date"].astype(str) == str(ex["date"])]
        if len(sel):
            first = sel.iloc[0]
            blk = sel[sel["Record"] == first["Record"]]
            items = [(r["Parameter"], r["Value"]) for _, r in blk.iterrows()]
            half = (len(items) + 1) // 2
            cells = []
            for i in range(half):
                left = items[i]
                right = items[i + half] if i + half < len(items) else ("", "")
                cells.append([left[0], str(left[1])[:60], right[0], str(right[1])[:60]])
            fig, ax = plt.subplots(figsize=(11, 0.4 * half + 1.1))
            ax.axis("off")
            tb = ax.table(cellText=cells, colLabels=["Parameter", "Value", "Parameter", "Value"], bbox=[0, 0, 1, 1], cellLoc="left")
            tb.auto_set_font_size(False)
            tb.set_fontsize(9)
            tb.scale(1, 1.4)
            for (r, c), cell in tb.get_celld().items():
                cell.set_edgecolor(GRID)
                if r == 0:
                    cell.set_facecolor("#2a78d6")
                    cell.set_text_props(color="white", fontweight="bold")
                else:
                    cell.set_facecolor(SURFACE)
            fig.suptitle(f"{first[WELL]} Drilling Parameters, {first[SEC]} Hole Section, {first['Date']}", x=0.01, ha="left",
                         fontsize=12, color=INK, fontweight="bold")
            files.append(_save(fig, out_dir / "slide14_drilling_parameters.png", rect=[0, 0, 1, 0.9]))
    return files
