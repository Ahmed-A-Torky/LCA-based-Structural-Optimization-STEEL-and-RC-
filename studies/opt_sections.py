# -*- coding: utf-8 -*-
"""Scaled cross-section drawings + practical bar schedules for the six optima."""
import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
RUNS = _os.environ.get("STUDIO_RUNS", _os.path.join(ROOT, "studies", "out", "runs"))
FIGS = _os.environ.get("STUDIO_FIGS", _os.path.join(ROOT, "studies", "out", "figs"))
_os.makedirs(RUNS, exist_ok=True); _os.makedirs(FIGS, exist_ok=True)
import json, itertools
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, FancyBboxPatch
import engine as E
plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix",
    "font.size": 9, "axes.linewidth": 0.8})
T = json.load(open(RUNS + "/nl_study.json"))
D = json.load(open(RUNS + "/section_demands.json"))
fc, fy = 25.0, 420.0
NAVY="#16263f"; RED="#b23b3b"; GREY="#6c7891"; CONC="#eef1f5"

DIAMS = [16, 20, 22, 25]
def area(d): return np.pi*d*d/4
def fits(n_d, width):
    inner = width - 2*(40+10)
    need = sum(nd*d for nd, d in n_d) + (sum(nd for nd,_ in n_d)-1)*25
    return need <= inner
def pick_bars(req, width, max_layers=2, nmax=8):
    best = None
    for d in DIAMS:
        for n in range(2, nmax+1):
            a = n*area(d)
            if a < req: continue
            if fits([(n, d)], width): layers = 1
            elif n <= 8 and fits([((n+1)//2, d)], width): layers = 2
            else: continue
            if layers > max_layers: continue
            if best is None or a < best[0]:
                best = (a, f"{n}\u00d8{d}", [(d, n)], layers)
    return best

def stirrup_s(h):
    d_ = h-60.0
    Vc = 0.17*np.sqrt(fc)*250*d_
    Vs = max(D["Vu"]/0.75 - Vc, 0.0)
    s = min(d_/2, 600.0)
    if Vs > 1e-6: s = min(s, 2*78.5*fy*d_/Vs)
    return 5*int(max(80.0, s)/5)

def draw_beam(ax, h, req, tag, met):
    prov = pick_bars(req, 250)
    a_p, call, sets, layers = prov
    ax.add_patch(Rectangle((0,0), 250, h, fc=CONC, ec=NAVY, lw=1.6))
    ax.add_patch(FancyBboxPatch((40,40), 170, h-80, boxstyle="round,pad=0,rounding_size=8",
                 fill=False, ec=RED, lw=1.1))
    bars = [d for d,n in sets for _ in range(n)]
    bars.sort(reverse=True)
    per_layer = int(np.ceil(len(bars)/layers))
    y0 = 50 + max(bars)/2
    k = 0
    for L in range(layers):
        row = bars[k:k+per_layer]; k += per_layer
        xs = np.linspace(50+max(row)/2, 200-max(row)/2, len(row)) if len(row)>1 else [125]
        for x, db in zip(xs, row):
            ax.add_patch(Circle((x, y0 + L*(25+max(bars))), db/2, color=NAVY))
    for x in (58, 192):
        ax.add_patch(Circle((x, h-56), 6, color=GREY))
    ax.annotate("", xy=(250,-28), xytext=(0,-28), arrowprops=dict(arrowstyle="<->", lw=0.7, color=GREY))
    ax.text(125, -52, "b = 250", ha="center", fontsize=7, color=GREY)
    ax.annotate("", xy=(-30,h), xytext=(-30,0), arrowprops=dict(arrowstyle="<->", lw=0.7, color=GREY))
    ax.text(-56, h/2, f"h = {h:.0f}", rotation=90, va="center", fontsize=7, color=GREY)
    ax.text(125, h-14, "2\u00d812 top bars", ha="center", fontsize=6.2,
            color=NAVY, style="italic")
    ax.text(125, 78, "tension face \u2014 midspan", ha="center", fontsize=6.2,
            color=GREY, style="italic")
    ax.set_title(f"{tag}\n250\u00d7{h:.0f} \u2014 {call} bottom ({a_p:.0f} mm$^2$, req. {req:.0f})",
                 fontsize=8)
    ax.text(125, h+34, met, ha="center", fontsize=6.6, color=GREY)
    s = stirrup_s(h)
    ax.text(125, -84, f"\u00d810@{s} links", ha="center",
            fontsize=6.6, color=RED)
    ax.set_xlim(-95, 320); ax.set_ylim(-105, 700); ax.set_aspect("equal"); ax.axis("off")
    return call, a_p, s

def draw_col(ax, h, req_tot, tag, met):
    reqf = req_tot/2
    prov = pick_bars(reqf, 300, max_layers=1, nmax=4)
    a_p, call, sets, layers = prov
    ax.add_patch(Rectangle((0,0), 300, h, fc=CONC, ec=NAVY, lw=1.6))
    ax.add_patch(FancyBboxPatch((40,40), 220, h-80, boxstyle="round,pad=0,rounding_size=8",
                 fill=False, ec=RED, lw=1.1))
    bars = [d for d,n in sets for _ in range(n)]
    m = 2*len(bars); db = bars[0]
    pts = [(60, 60), (240, 60), (240, h-60), (60, h-60)]          # corners
    if m == 6:
        pts += [(60, h/2), (240, h/2)]                             # mid tall faces
    elif m == 8:
        pts += [(150, 60), (150, h-60), (60, h/2), (240, h/2)]     # mid all faces
    else:
        for k in range(m-4):
            pts.append((60 if k % 2 == 0 else 240, 60+(k//2+1)*(h-120)/((m-4)//2+1)))
    for x, yy in pts[:m]:
        ax.add_patch(Circle((x, yy), db/2, color=NAVY))
    ax.annotate("", xy=(300,-28), xytext=(0,-28), arrowprops=dict(arrowstyle="<->", lw=0.7, color=GREY))
    ax.text(150, -52, "b = 300", ha="center", fontsize=7, color=GREY)
    ax.annotate("", xy=(-30,h), xytext=(-30,0), arrowprops=dict(arrowstyle="<->", lw=0.7, color=GREY))
    ax.text(-56, h/2, f"h = {h:.0f}", rotation=90, va="center", fontsize=7, color=GREY)
    ax.text(150, h-16, "", ha="center", fontsize=6.2,
            color=NAVY, style="italic")
    ax.text(150, 84, "perimeter cage \u2014 $A_{s,tot}$ total", ha="center", fontsize=6.2,
            color=NAVY, style="italic")
    ax.set_title(f"{tag}\n300\u00d7{h:.0f} \u2014 2\u00d7{call} on perimeter ({2*a_p:.0f} mm$^2$ tot., req. {req_tot:.0f})",
                 fontsize=8)
    ax.text(150, h+34, met, ha="center", fontsize=6.6, color=GREY)
    ax.text(150, -84, "\u00d88@300 ties", ha="center", fontsize=6.6, color=RED)
    ax.set_xlim(-95, 370); ax.set_ylim(-105, 700); ax.set_aspect("equal"); ax.axis("off")
    return call, 2*a_p

LAB = {"cost": "(a) cost-optimal", "co2_bedec": "(b) CO$_2$-optimal, BEDEC rebar",
       "co2_green": "(c) CO$_2$-optimal, green-EAF rebar"}
fig, axes = plt.subplots(2, 3, figsize=(9.8, 7.6))
out = {"beam": {}, "column": {}}
for j, k in enumerate(["cost", "co2_bedec", "co2_green"]):
    r = T["beam"][k]
    met = (f"{r['cost']:.1f} \u20ac/m \u00b7 {r['co2_bedec']:.1f} kg CO$_2$/m (BEDEC) \u00b7 "
           f"{r['co2_green']:.1f} kg (green)")
    call, ap, s = draw_beam(axes[0, j], r["h"], r["As"], LAB[k], met)
    _, pm, et, _ = E._rc_flex_doubly(250, r["h"]-60, 60, r["As"], 226, fc, fy)
    out["beam"][k] = dict(call=call, prov=round(ap), s=s, eps=round(et,4),
                          util=round(D["Mu_hog"]/pm*100))
    r = T["column"][k]
    met = (f"{r['cost']:.1f} \u20ac/m \u00b7 {r['co2_bedec']:.1f} kg CO$_2$/m (BEDEC) \u00b7 "
           f"{r['co2_green']:.1f} kg (green)")
    call, ap = draw_col(axes[1, j], r["h"], r["As"], LAB[k], met)
    pp = E._rc_phiPn_at_e(300, r["h"], r["As"]/2, r["As"]/2, fc, fy,
                          max(D["Mu"]/D["Pu"], 15+0.03*r["h"]))
    out["column"][k] = dict(call=call, prov=round(ap),
                            rho=round(r["As"]/(300*r["h"])*100,2),
                            util=round(D["Pu"]/pp*100))
fig.suptitle("Optimal sections drawn to a common scale \u2014 frame beam midspan section, tension face at bottom (top row) "
             "and frame column, evenly distributed perimeter cage (bottom row);\nrequired steel from the optimization, provided bars "
             "selected for \u226525 mm clear spacing, \u22642 layers", fontsize=9.6, y=0.995)
fig.tight_layout()
fig.savefig(FIGS + "/fig_opt_sections.png", dpi=300,
            bbox_inches="tight", facecolor="white")
print(json.dumps(out, indent=0))
