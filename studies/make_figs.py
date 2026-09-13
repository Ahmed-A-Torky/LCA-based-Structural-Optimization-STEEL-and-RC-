# -*- coding: utf-8 -*-
"""Generate documentation figures for all 13 benchmarks (print theme)."""
import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
RUNS = _os.environ.get("STUDIO_RUNS", _os.path.join(ROOT, "studies", "out", "runs"))
FIGS = _os.environ.get("STUDIO_FIGS", _os.path.join(ROOT, "studies", "out", "figs"))
_os.makedirs(RUNS, exist_ok=True); _os.makedirs(FIGS, exist_ok=True)
import json, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyArrow, Polygon
import engine as E

OUT = FIGS; os.makedirs(OUT, exist_ok=True)
NAVY = "#16263f"; AMBER = "#e08a1e"; TEAL = "#1a8fa0"; GREEN = "#2e9e63"
GREY = "#8a93a3"; RED = "#c0584a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                     "axes.edgecolor": GREY, "axes.linewidth": 0.6})

def load(key):
    return json.load(open(RUNS + f"/{key}.json"))

def save(fig, name):
    fig.savefig(f"{OUT}/{name}.png", dpi=160, bbox_inches="tight",
                facecolor="white")
    plt.close(fig)

def project3d(c):
    ay, ax_ = np.radians(32), np.radians(22)
    x, y, z = c
    xr = x*np.cos(ay) + y*np.sin(ay)
    yr = -x*np.sin(ay) + y*np.cos(ay)
    return xr, z*np.cos(ax_) - yr*np.sin(ax_)

# ---------------------------------------------------------------- geometry
def geom_truss_or_frame(key, areas=None):
    p = E.PROBLEMS[key]()
    fig, ax = plt.subplots(figsize=(3.6, 2.7))
    is3d = p.ndm == 3
    pts = {}
    for nid, c in p.nodes.items():
        pts[nid] = project3d(c) if is3d else (c[0], c[1])
    elems = p.elements
    amax = max(areas) if areas is not None else 1.0
    for el in elems:
        if len(el) == 4: (e, i, j, g), r = el, None
        else: e, i, j, g, r = el
        A = areas[g] if areas is not None else 1.0
        lw = 0.6 + 2.6*np.sqrt(A/amax)
        col = TEAL
        if r == "beam": col = AMBER
        elif r == "brace": col = GREEN
        ax.plot([pts[i][0], pts[j][0]], [pts[i][1], pts[j][1]],
                color=col, lw=lw, solid_capstyle="round", zorder=2)
    for nid, c in pts.items():
        if nid in p.fixed:
            ax.plot(c[0], c[1], marker="s", ms=5, color=NAVY, zorder=3)
        else:
            ax.plot(c[0], c[1], marker="o", ms=2.5, color=GREY, zorder=3)
    mass_nodes = set(getattr(p, "mass_nodes", ()))
    for nid in mass_nodes:
        ax.plot(*pts[nid], marker="o", ms=8, mfc="none", mec=TEAL, mew=1.6, zorder=4)
        ax.plot(*pts[nid], marker="o", ms=4, color=TEAL, zorder=4)
    # load arrows (static problems with nodal loads)
    loads = getattr(p, "loads", None) or {}
    if key == "72bar": loads = p.load_cases[0]
    if key == "mrf3": loads = {n: (F, 0) for n, F in p.lateral.items()}
    if key == "rc_frame3": loads = {n: (F, 0) for n, F in p.Elat.items()}
    if loads:
        span = max(max(abs(v[0]) for v in pts.values()),
                   max(abs(v[1]) for v in pts.values()))
        Fm = max(np.linalg.norm(np.array(v[:p.ndm], float)) for v in loads.values()) or 1
        for nid, v in loads.items():
            f = np.array(v[:p.ndm], float)
            mag = np.linalg.norm(f)
            if mag < 1e-6: continue
            scale = (0.16*span*mag/Fm + 0.06*span)/mag
            coord = np.array(p.nodes[nid], float)
            tail3 = coord - f*scale
            tail = project3d(tail3) if is3d else (tail3[0], tail3[1])
            ax.annotate("", xy=pts[nid], xytext=tail,
                        arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.5))
    ax.set_aspect("equal"); ax.axis("off")
    return fig

def geom_rc_beam():
    p = E.PROBLEMS["rc_beam"]()
    fig, ax = plt.subplots(figsize=(3.6, 2.0))
    L = 8.0
    ax.add_patch(Rectangle((0, 0), L, 0.55, fill=False, ec=NAVY, lw=1.4))
    ax.plot([0.5, 0.7, 0.3, 0.5], [0, -0.35, -0.35, 0], color=NAVY, lw=1.2)
    ax.add_patch(Circle((L-0.5, -0.18), 0.14, fill=False, ec=NAVY, lw=1.2))
    ax.plot([L-0.9, L-0.1], [-0.36, -0.36], color=NAVY, lw=1.2)
    for k in range(11):
        x = 0.3 + k*(L-0.6)/10
        ax.annotate("", xy=(x, 0.6), xytext=(x, 1.15),
                    arrowprops=dict(arrowstyle="-|>", color=RED, lw=1.2))
    ax.plot([0.3, L-0.3], [1.15, 1.15], color=RED, lw=1.2)
    ax.text(L/2, 1.3, "wD = 15 kN/m  +  wL = 12 kN/m", ha="center", fontsize=8.5, color=NAVY)
    ax.plot([0, 0], [-0.7, -0.95], color=GREY, lw=0.7); ax.plot([L, L], [-0.7, -0.95], color=GREY, lw=0.7)
    ax.annotate("", xy=(L, -0.85), xytext=(0, -0.85), arrowprops=dict(arrowstyle="<->", color=GREY, lw=0.8))
    ax.text(L/2, -1.12, "L = 8.0 m (simply supported)", ha="center", fontsize=8.5, color=GREY)
    ax.set_xlim(-0.6, L+0.6); ax.set_ylim(-1.4, 1.7); ax.set_aspect("equal"); ax.axis("off")
    return fig

def geom_rc_column():
    fig, ax = plt.subplots(figsize=(2.6, 2.7))
    ax.add_patch(Rectangle((-0.25, 0), 0.5, 3.0, fill=False, ec=NAVY, lw=1.4))
    ax.plot([-0.8, 0.8], [0, 0], color=NAVY, lw=2)
    for k in range(7):
        x = -0.75 + k*0.25
        ax.plot([x, x-0.14], [0, -0.16], color=GREY, lw=0.7)
    ax.annotate("", xy=(0, 3.05), xytext=(0, 3.75),
                arrowprops=dict(arrowstyle="-|>", color=RED, lw=2))
    ax.text(0.12, 3.45, "Pu = 1200 kN", fontsize=8.5, color=NAVY)
    th = np.linspace(-0.4*np.pi, 0.7*np.pi, 40)
    ax.plot(0.55*np.cos(th), 3.1+0.35*np.sin(th), color=RED, lw=1.4)
    ax.text(0.7, 2.78, "Mu = 100 kN-m", fontsize=8.5, color=NAVY)
    ax.annotate("", xy=(-0.72, 3.0), xytext=(-0.72, 0), arrowprops=dict(arrowstyle="<->", color=GREY, lw=0.8))
    ax.text(-0.9, 1.5, "lu = 3.0 m", rotation=90, va="center", fontsize=8.5, color=GREY)
    ax.set_xlim(-1.3, 1.5); ax.set_ylim(-0.45, 4.1); ax.set_aspect("equal"); ax.axis("off")
    return fig

def geom_rc_footing():
    fig, ax = plt.subplots(figsize=(3.6, 2.4))
    ax.plot([-2.6, 2.6], [1.5, 1.5], color=GREY, lw=1.1)
    for k in range(13):
        x = -2.5 + k*0.42
        ax.plot([x, x-0.18], [1.5, 1.68], color=GREY, lw=0.6)
    ax.add_patch(Rectangle((-0.2, 0.46), 0.4, 1.04, fill=False, ec=NAVY, lw=1.3))
    ax.add_patch(Rectangle((-1.35, 0), 2.7, 0.46, fill=False, ec=NAVY, lw=1.5))
    ax.plot([-1.25, 1.25], [0.09, 0.09], color=RED, lw=1.8)
    for k in range(9):
        ax.plot(-1.15+k*0.29, 0.14, marker="o", ms=2.6, color=RED)
    for k in range(7):
        x = -1.2 + k*0.4
        ax.annotate("", xy=(x, -0.06), xytext=(x, -0.42),
                    arrowprops=dict(arrowstyle="-|>", color=GREEN, lw=1.1))
    ax.annotate("", xy=(0, 2.3), xytext=(0, 1.62), arrowprops=dict(arrowstyle="<|-", color=RED, lw=1.8))
    ax.text(0.1, 2.05, "PD = 750 kN, PL = 400 kN", fontsize=8.2, color=NAVY)
    ax.annotate("", xy=(-1.35, -0.75), xytext=(1.35, -0.75), arrowprops=dict(arrowstyle="<->", color=GREY, lw=0.8))
    ax.text(0, -0.98, "B x L plan, embedded Df = 1.5 m, qa = 200 kPa", ha="center", fontsize=8, color=GREY)
    ax.set_xlim(-2.8, 2.8); ax.set_ylim(-1.25, 2.6); ax.set_aspect("equal"); ax.axis("off")
    return fig

# ------------------------------------------------------------- cross-sections
def xsec_groups(key):
    d = load(key); p = E.PROBLEMS[key]()
    areas = np.array(d["best_x"])
    labels = p.group_labels
    fig, ax = plt.subplots(figsize=(3.6, 0.32*len(areas)+0.7))
    y = np.arange(len(areas))[::-1]
    ax.barh(y, areas/100.0, color=TEAL, height=0.62, alpha=0.85)
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=7.2)
    ax.set_xlabel("optimized area  (cm$^2$)", fontsize=8)
    for yy, a in zip(y, areas/100.0):
        ax.text(a + ax.get_xlim()[1]*0.01, yy, f"{a:.1f}", va="center", fontsize=6.8, color=NAVY)
    ax.spines[["top", "right"]].set_visible(False)
    return fig

def draw_rc_section(ax, b, h, bars_bot=0, bars_top=0, As_bot=0, As_top=0, tie=True, title=""):
    sc = 1.0/max(b, h)
    B, H = b*sc, h*sc
    ax.add_patch(Rectangle((0, 0), B, H, fill=False, ec=NAVY, lw=1.6))
    if tie:
        c = 40*sc
        ax.add_patch(Rectangle((c, c), B-2*c, H-2*c, fill=False, ec=GREEN, lw=1.0))
    def put(n, As, yy):
        if n <= 0: return
        r = np.sqrt((As/n)/np.pi)*sc
        for k in range(n):
            x = 55*sc + k*(B-110*sc)/max(n-1, 1) if n > 1 else B/2
            ax.add_patch(Circle((x, yy), max(r, 0.018), color=RED))
    put(bars_bot, As_bot, 55*sc)
    put(bars_top, As_top, H-55*sc)
    ax.annotate("", xy=(B, -0.09), xytext=(0, -0.09), arrowprops=dict(arrowstyle="<->", color=GREY, lw=0.7))
    ax.text(B/2, -0.2, f"b = {b:.0f} mm", ha="center", fontsize=7.6, color=GREY)
    ax.annotate("", xy=(-0.09, H), xytext=(-0.09, 0), arrowprops=dict(arrowstyle="<->", color=GREY, lw=0.7))
    ax.text(-0.2, H/2, f"h = {h:.0f}", rotation=90, va="center", fontsize=7.6, color=GREY)
    ax.set_title(title, fontsize=8.6, color=NAVY)
    ax.set_xlim(-0.42, B+0.25); ax.set_ylim(-0.34, H+0.18)
    ax.set_aspect("equal"); ax.axis("off")

def xsec_rc_beam():
    d = load("rc_beam"); v = {x["name"]: x["value"] for x in d["eval"]["variables"]}
    b, h = v["Width b"], v["Depth h"]
    Ab, At = v["Bottom steel As,bot"], v["Top steel As,top"]
    nb = int(np.clip(round(Ab/314), 2, 8)); nt = int(np.clip(round(At/113), 2, 6))
    fig, ax = plt.subplots(figsize=(2.5, 2.9))
    draw_rc_section(ax, b, h, bars_bot=nb, As_bot=Ab, bars_top=nt, As_top=At,
                    title=(f"optimized section\nAs,bot = {Ab:.0f} mm$^2$ ({nb} bars) - "
                           f"As,top = {At:.0f} mm$^2$"))
    return fig

def xsec_rc_column():
    d = load("rc_column"); v = {x["name"]: x["value"] for x in d["eval"]["variables"]}
    b, h = v["Width b"], v["Depth h"]
    Ast, Asc = v["Tension-face steel As,t"], v["Compression-face steel As,c"]
    nt = int(np.clip(round(Ast/314), 2, 6)); nc = int(np.clip(round(Asc/314), 2, 6))
    fig, ax = plt.subplots(figsize=(2.5, 2.7))
    # drawing convention: bottom of the sketch = tension face, top = compression
    draw_rc_section(ax, h, b, bars_bot=nt, bars_top=nc, As_bot=Ast, As_top=Asc,
                    title=(f"asymmetric cage\nAs,t = {Ast:.0f} (tension) - "
                           f"As,c = {Asc:.0f} mm$^2$ (compression)"))
    return fig

def xsec_rc_footing():
    d = load("rc_footing"); v = {x["name"]: x["value"] for x in d["eval"]["variables"]}
    B, L, h = v["Footing width B"], v["Footing length L"], v["Thickness h"]
    AsB, AsL = v["Steel (B-dir) As\u1d2e"], v["Steel (L-dir) As\u1d38"]
    fig, ax = plt.subplots(figsize=(3.0, 2.9))
    sc = 1.0/max(B, L); Bs, Ls = B*sc, L*sc
    ax.add_patch(Rectangle((0, 0), Ls, Bs, fill=False, ec=NAVY, lw=1.6))
    ax.add_patch(Rectangle((Ls/2-0.07, Bs/2-0.07), 0.14, 0.14, fill=False, ec=NAVY, lw=1.2))
    nL = int(np.clip(round(AsL/314), 4, 12)); nB = int(np.clip(round(AsB/314), 4, 12))
    for k in range(nL):
        y = 0.06 + k*(Bs-0.12)/(nL-1)
        ax.plot([0.04, Ls-0.04], [y, y], color=RED, lw=1.0)
    for k in range(nB):
        x = 0.06 + k*(Ls-0.12)/(nB-1)
        ax.plot([x, x], [0.04, Bs-0.04], color=RED, lw=0.8, alpha=0.75)
    ax.text(Ls/2, -0.1, f"L = {L:.0f} mm   ({nL} bars AsL)", ha="center", fontsize=7.6, color=GREY)
    ax.text(-0.08, Bs/2, f"B = {B:.0f} mm   ({nB} bars AsB)", rotation=90, va="center", fontsize=7.6, color=GREY)
    ax.set_title(f"plan of reinforcement mats - h = {h:.0f} mm", fontsize=8.6, color=NAVY)
    ax.set_xlim(-0.25, Ls+0.1); ax.set_ylim(-0.22, Bs+0.12)
    ax.set_aspect("equal"); ax.axis("off")
    return fig

def xsec_rc_frame3():
    d = load("rc_frame3"); v = {x["name"]: x["value"] for x in d["eval"]["variables"]}
    bb, hb = v["Beam width b\u1d47"], v["Beam depth h\u1d47"]
    At, Ab = v["Beam top steel As,top"], v["Beam bottom steel As,bot"]
    bc, hc, rc = v["Column width b\u1d9c"], v["Column depth h\u1d9c"], v["Column steel ratio \u03c1\u1d9c"]
    Asc = rc*bc*hc
    fig, axes = plt.subplots(1, 2, figsize=(4.2, 2.6))
    draw_rc_section(axes[0], bb, hb, bars_bot=int(np.clip(round(Ab/314),2,5)), As_bot=Ab,
                    bars_top=int(np.clip(round(At/314),2,5)), As_top=At, title="beam (all 6)")
    nc = int(np.clip(2*round(Asc/491/2), 4, 8))
    draw_rc_section(axes[1], hc, bc, bars_bot=nc//2, bars_top=nc//2,
                    As_bot=Asc/2, As_top=Asc/2, title="column (all 9)")
    return fig

def draw_W(ax, name, A, Ix, Zx):
    d, bf, tf, tw = 1.0, 0.62, 0.075, 0.05
    for y0 in (0, d-tf):
        ax.add_patch(Rectangle(((1-bf)/2 if False else 0.19, y0), bf, tf, color=NAVY))
    ax.add_patch(Rectangle((0.5-tw/2, tf), tw, d-2*tf, color=NAVY))
    ax.text(0.5, -0.16, name, ha="center", fontsize=9.0, color=NAVY, weight="bold")
    ax.text(0.5, -0.31, f"A={A} in$^2$", ha="center", fontsize=6.4, color=GREY)
    ax.text(0.5, -0.44, f"Ix={Ix:.0f} in$^4$, Zx={Zx:.0f} in$^3$",
            ha="center", fontsize=6.4, color=GREY)
    ax.set_xlim(0, 1); ax.set_ylim(-0.55, 1.1); ax.set_aspect("equal"); ax.axis("off")

def xsec_mrf3():
    d = load("mrf3")
    bn = d["eval"]["sections"]["beams"]; cn = d["eval"]["sections"]["columns"]
    bdat = next(x for x in E.W_BEAMS if x[0] == bn)
    cdat = next(x for x in E.W10_COLUMNS if x[0] == cn)
    fig, axes = plt.subplots(1, 2, figsize=(3.8, 2.4))
    draw_W(axes[0], bn + "  (beams)", bdat[1], bdat[2], bdat[3])
    draw_W(axes[1], cn + "  (columns)", cdat[1], cdat[2], cdat[3])
    return fig

# --------------------------------------------------------------- convergence
def conv(key):
    d = load(key)
    if d.get("freq_history") and d.get("freq_target"):
        # frequency problems: the target IS the reference -> plot f1 vs target
        ft = d["freq_target"]
        fig, ax = plt.subplots(figsize=(3.5, 2.0))
        fh = [(i+1, v) for i, v in enumerate(d["freq_history"]) if v is not None]
        xs, ys = zip(*fh)
        lo_b, hi_b = ft["value"]*(1-ft["tol"]), ft["value"]*(1+ft["tol"])
        ax.axhspan(lo_b, hi_b, color=AMBER, alpha=0.13,
                   label=f"target band +/-{ft['tol']*100:.0f}%")
        ax.axhline(ft["value"], color=AMBER, lw=1.4, ls="--")
        ax.plot(xs, ys, color=TEAL, lw=1.8, label=f"best-design f{ft['mode']}")
        ax.plot(xs[-1], ys[-1], "o", color=TEAL, ms=4)
        ax.annotate(f"f{ft['mode']} = {ys[-1]:.2f} {ft['unit']}", (xs[-1], ys[-1]),
                    textcoords="offset points", xytext=(-4, 7), ha="right",
                    fontsize=7.2, color=NAVY)
        ax.text(xs[0], ft["value"], f"  target {ft['value']} {ft['unit']}",
                fontsize=7, color="#a06410", va="bottom")
        ax.set_xlabel("generation", fontsize=8)
        ax.set_ylabel(f"f{ft['mode']}  ({ft['unit']})", fontsize=8)
        # secondary axis: best feasible mass, for context
        hist = [(i+1, v) for i, v in enumerate(d["history"]) if v is not None]
        if hist:
            ax2 = ax.twinx()
            xs2, ys2 = zip(*hist)
            ax2.plot(xs2, ys2, color=GREY, lw=1.0, ls=":", alpha=0.85)
            ax2.set_ylabel("best feasible mass (kg)", fontsize=7, color=GREY)
            ax2.tick_params(labelsize=6.4, colors=GREY)
            ax2.spines[["top"]].set_visible(False)
        ax.tick_params(labelsize=7); ax.grid(alpha=0.2, lw=0.4)
        ax.spines[["top"]].set_visible(False)
        return fig
    fig, ax = plt.subplots(figsize=(3.5, 1.9))
    hist = [(i+1, v) for i, v in enumerate(d["history"]) if v is not None]
    if hist:
        xs, ys = zip(*hist)
        ax.plot(xs, ys, color=TEAL, lw=1.8)
        ax.fill_between(xs, ys, min(ys), color=TEAL, alpha=0.12)
    if d["ref"]:
        ax.axhline(d["ref"], color=AMBER, lw=1.2, ls="--")
    ax.set_xlabel("generation", fontsize=8); ax.set_ylabel("best objective", fontsize=8)
    ax.tick_params(labelsize=7); ax.grid(alpha=0.25, lw=0.4)
    ax.spines[["top", "right"]].set_visible(False)
    return fig

# ------------------------------------------------------------------- build all
KEYS = ["10bar","25bar","72bar","10frame","25frame","mrf3",
        "10bar_freq","72bar_freq","6frame_freq",
        "rc_beam","rc_column","rc_footing","rc_frame3"]
for key in KEYS:
    d = load(key)
    # geometry
    if key == "rc_beam": fig = geom_rc_beam()
    elif key == "rc_column": fig = geom_rc_column()
    elif key == "rc_footing": fig = geom_rc_footing()
    else:
        areas = None
        p = E.PROBLEMS[key]()
        if key == "mrf3":
            ib, ic = p._indices(d["best_x"])
            Ab = E.W_BEAMS[ib][1]*E.IN2; Ac = E.W10_COLUMNS[ic][1]*E.IN2
            areas = [Ac]*9 + [Ab]*6
        elif key == "rc_frame3":
            bb, hb, At, Abot, bc, hc, rc = p._phys(d["best_x"])
            areas = [bc*hc]*9 + [bb*hb]*6
        else:
            areas = list(np.atleast_1d(d["best_x"]))
        fig = geom_truss_or_frame(key, areas)
    save(fig, f"{key}_geom")
    # cross-section
    if key == "rc_beam": fig = xsec_rc_beam()
    elif key == "rc_column": fig = xsec_rc_column()
    elif key == "rc_footing": fig = xsec_rc_footing()
    elif key == "rc_frame3": fig = xsec_rc_frame3()
    elif key == "mrf3": fig = xsec_mrf3()
    else: fig = xsec_groups(key)
    save(fig, f"{key}_xsec")
    save(conv(key), f"{key}_conv")
    print(key, "figures done")
print("ALL FIGURES DONE")
