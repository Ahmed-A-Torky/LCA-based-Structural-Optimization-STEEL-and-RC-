# -*- coding: utf-8 -*-
"""Steel-production-route study: re-optimize the RC beam, column and footing
under every route; writes route_study.json and the two-panel figure."""
import os as _os, sys as _sys, json
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
RUNS = _os.environ.get("STUDIO_RUNS", _os.path.join(ROOT, "studies", "out", "runs"))
FIGS = _os.environ.get("STUDIO_FIGS", _os.path.join(ROOT, "studies", "out", "figs"))
_os.makedirs(RUNS, exist_ok=True); _os.makedirs(FIGS, exist_ok=True)
import numpy as np
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import engine as E
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9})
NAVY="#16263f"; TEAL="#1a8fa0"; AMBER="#e08a1e"; GREEN="#2e9e63"; GREY="#8a93a3"
routes = ["bedec", "bof", "avg", "eaf", "green"]
labels = {"bedec": "BEDEC\n2.82", "bof": "BF-BOF\n1.99", "avg": "World avg\n1.85",
          "eaf": "EAF grid\n0.67", "green": "Green EAF\n0.36"}
study = {}
for key, pop, gen in [("rc_beam", 90, 90), ("rc_column", 90, 90), ("rc_footing", 70, 70)]:
    study[key] = []
    for rt in routes:
        best = None
        for seed in (1, 2):
            p = E.PROBLEMS[key](); p.set_steel_route(rt)
            r = E.run_ga(p, pop_size=pop, n_gen=gen, seed=seed); ev = p.evaluate(r["best_x"])
            if r["feasible"] and (best is None or ev["mass"] < best["mass"]): best = ev
        study[key].append({"route": rt, "co2": best["mass"],
                           "steel_kg": best["quantities"]["steel_kg"]})
        print(f"{key} {rt}: {best['mass']:.1f} kg CO2, steel {best['quantities']['steel_kg']:.0f} kg")
json.dump(study, open(_os.path.join(RUNS, "route_study.json"), "w"), indent=1)
fig, axes = plt.subplots(1, 2, figsize=(7.0, 2.6))
names = {"rc_beam": "RC beam", "rc_column": "RC column", "rc_footing": "RC footing"}
cols = {"rc_beam": TEAL, "rc_column": AMBER, "rc_footing": GREEN}
x = np.arange(len(routes)); w = 0.26
for i, (key, dat) in enumerate(study.items()):
    axes[0].bar(x+(i-1)*w, [d["co2"]/dat[0]["co2"]*100 for d in dat], w, color=cols[key], label=names[key])
    axes[1].plot(x, [d["steel_kg"]/dat[0]["steel_kg"] for d in dat], "o-", color=cols[key], lw=1.6, ms=4)
for ax, yl, tt in [(axes[0], "optimum CO$_2$ (% of default route)", "(a) optimal embodied CO$_2$ by steel route"),
                   (axes[1], "steel mass at optimum\n(x default-route optimum)", "(b) material substitution: steel usage")]:
    ax.set_xticks(x); ax.set_xticklabels([labels[r] for r in routes], fontsize=7)
    ax.set_ylabel(yl, fontsize=8); ax.tick_params(labelsize=7)
    ax.axhline(100 if ax is axes[0] else 1.0, color=GREY, lw=0.8, ls=":")
    ax.spines[["top", "right"]].set_visible(False); ax.set_title(tt, fontsize=8.5)
axes[0].legend(fontsize=7, frameon=False)
plt.tight_layout()
fig.savefig(_os.path.join(FIGS, "fig_routes.png"), dpi=200, bbox_inches="tight", facecolor="white")
print("fig_routes saved")
