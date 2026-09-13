# -*- coding: utf-8 -*-
"""Validation set 2: (S5) multi-seed GA statistics; (S6) frame-level closure."""
import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
RUNS = _os.environ.get("STUDIO_RUNS", _os.path.join(ROOT, "studies", "out", "runs"))
FIGS = _os.environ.get("STUDIO_FIGS", _os.path.join(ROOT, "studies", "out", "figs"))
_os.makedirs(RUNS, exist_ok=True); _os.makedirs(FIGS, exist_ok=True)
import sys, json, time
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import engine as E
plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix",
    "font.size": 9.5, "axes.linewidth": 0.8, "xtick.direction": "in",
    "ytick.direction": "in"})
OUT = FIGS
NAVY="#16263f"; TEAL="#1a8fa0"; AMBER="#c87f16"; GREEN="#2e9e63"; GREY="#6c7891"; RED="#8a1f1f"

def demands(p, x):
    bb, hb, At, Ab, bc, hc, rc = p._phys(x)
    wself = 24.0e-6*bb*hb
    combos = [(1.2*(p.wD+wself)+1.6*p.wL, False), (1.2*(p.wD+wself)+1.0*p.wL, True)]
    Mu = Vu = 0.0; L = p.BAY
    Pc = {e:0.0 for e in range(1,10)}; Mc = {e:0.0 for e in range(1,10)}
    for (w, lat) in combos:
        ok, endf, F = p._solve(bb, hb, bc, hc, w, lat)
        for (e,i,j,g,r) in p.elements:
            Ni, Mi, Nj, Mj = endf[e]
            if r == "beam":
                Mic = Mi+F; Mjc = Mj-F
                Mu = max(Mu, abs(Mic), abs(Mjc))
                Vu = max(Vu, w*L/2 + abs(Mic+Mjc)/L)
            else:
                Pc[e] = max(Pc[e], abs(Ni), abs(Nj)); Mc[e] = max(Mc[e], abs(Mi), abs(Mj))
    wu, wd = 0, None
    for e in range(1,10):
        Pu = Pc[e]; Mu2 = max(Mc[e], Pu*(15+0.03*hc))
        pp = E._rc_phiPn_at_e(bc, hc, rc*bc*hc/2, rc*bc*hc/2, p.fc, p.fy, Mu2/max(Pu,1))
        u = Pu/max(pp,1)
        if u > wu: wu, wd = u, (Pc[e], Mc[e])
    return dict(Mu_hog=Mu, Vu=Vu, Pu=wd[0], Mu_col=wd[1])

if sys.argv[1] == "seeds":
    plans = [("10bar", 80, 80, 8), ("rc_beam", 100, 100, 8),
             ("rc_column", 100, 100, 8), ("10bar_freq", 90, 90, 8),
             ("mrf3", 80, 80, 5)]
    res = {}
    for key, pop, gen, ns in plans:
        p0 = E.PROBLEMS[key]()
        dd = []
        for sd in range(1, ns+1):
            r = E.run_ga(p0, pop_size=pop, n_gen=gen, seed=sd)
            ev = p0.evaluate(r["best_x"])
            dd.append((ev["mass"]-p0.ref_mass)/p0.ref_mass*100 if r["feasible"] else np.nan)
        res[key] = dd
        print(key, [round(x,1) for x in dd])
    json.dump(res, open(RUNS + "/seed_study.json","w"))
    fig, ax = plt.subplots(figsize=(7.2, 3.2))
    keys = list(res); labs = {"10bar":"10-bar\ntruss","rc_beam":"RC beam",
        "rc_column":"RC column","10bar_freq":"10-bar\n(frequency)","mrf3":"steel MRF\n(discrete)"}
    for k, key in enumerate(keys):
        v = np.array(res[key])
        ax.plot(np.full_like(v, k) + np.random.default_rng(k).uniform(-.09,.09,len(v)),
                v, "o", ms=4.5, mfc=TEAL, mec=NAVY, mew=0.5, alpha=0.85)
        ax.plot([k-.2, k+.2], [np.nanmedian(v)]*2, color=NAVY, lw=2)
        ax.text(k, np.nanmax(v)+0.6, f"CoV {np.nanstd(v.clip(min=None)+100)/np.nanmean(v+100)*100:.1f}%",
                ha="center", fontsize=6.4, color=GREY)
    ax.axhline(0, color=RED, lw=1.1, ls="--")
    ax.text(len(keys)-0.5, 0.15, "reference", color=RED, fontsize=7, ha="right")
    ax.set_xticks(range(len(keys))); ax.set_xticklabels([labs[k] for k in keys], fontsize=8)
    ax.set_ylabel("(best-found \u2212 reference)/reference (%)")
    ax.set_title("Multi-seed GA statistics: independent seeded runs per benchmark "
                 "(median bars; reference at 0%)", fontsize=9.3)
    ax.grid(alpha=0.2, lw=0.4, axis="y")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_val_seeds.png", dpi=300, bbox_inches="tight", facecolor="white")
    print("S5 seeds figure saved")

if sys.argv[1] == "closure":
    ref = json.load(open(RUNS + "/rc_frame3.json"))
    base = E.PROBLEMS["rc_frame3"]()
    designs = {"CO2-opt (BEDEC)": (base, ref["best_x"])}
    Cls = type(base)
    class FrameCost(Cls):
        def evaluate(self, x):
            r = Cls.evaluate(self, x)
            if r.get("ok") and "quantities" in r:
                q = r["quantities"]
                r["co2_bedec"] = r["mass"]
                r["mass"] = 90.0*q["concrete_m3"] + 1.30*q["steel_kg"] + 25.0*q["formwork_m2"]
            return r
    pc = FrameCost()
    t0 = time.time(); rc_ = E.run_ga(pc, pop_size=60, n_gen=60, seed=5)
    print(f"cost-opt frame: {rc_['best_obj']:.1f} EUR, t={time.time()-t0:.0f}s")
    designs["cost-opt"] = (base, rc_["best_x"])
    pg = E.PROBLEMS["rc_frame3"](); pg.set_steel_route("green")
    t0 = time.time(); rg = E.run_ga(pg, pop_size=60, n_gen=60, seed=5)
    print(f"green-CO2-opt frame: {rg['best_obj']:.1f} kg, t={time.time()-t0:.0f}s")
    designs["CO2-opt (green)"] = (pg, rg["best_x"])
    # cross-evaluate every design under cost / CO2-bedec / CO2-green + demands
    rows = {}
    d0 = demands(base, ref["best_x"])
    for nm, (pp, x) in designs.items():
        ev = E.PROBLEMS["rc_frame3"]().evaluate(x)
        q = ev["quantities"]
        cost = 90.0*q["concrete_m3"] + 1.30*q["steel_kg"] + 25.0*q["formwork_m2"]
        co2b = ev["mass"]
        pgr = E.PROBLEMS["rc_frame3"](); pgr.set_steel_route("green")
        co2g = pgr.evaluate(x)["mass"]
        dm = demands(base, x)
        rows[nm] = dict(cost=cost, co2b=co2b, co2g=co2g, feas=ev["feasible"],
                        shift={k: (dm[k]-d0[k])/d0[k]*100 for k in d0})
        print(nm, {k: round(v,1) for k,v in rows[nm]["shift"].items()},
              "| cost %.0f co2b %.0f co2g %.0f feas %s" % (cost, co2b, co2g, ev["feasible"]))
    json.dump(rows, open(RUNS + "/frame_closure.json","w"))
    # figure
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.3))
    ax = axes[0]
    names = list(rows); x = np.arange(len(names)); w = 0.26
    mets = [("cost", "cost (\u20ac)", NAVY), ("co2b", "CO$_2$, BEDEC (kg)", AMBER),
            ("co2g", "CO$_2$, green (kg)", GREEN)]
    for k, (mk, lab, col) in enumerate(mets):
        v = np.array([rows[n][mk] for n in names])
        ax.bar(x+(k-1)*w, v/v.min()*100, w, color=col, alpha=0.9, label=lab)
        for xi, vi in zip(x+(k-1)*w, v/v.min()*100):
            ax.text(xi, vi+1, f"{vi:.0f}", ha="center", fontsize=6.2)
    ax.axhline(100, color=GREY, lw=0.8, ls=":")
    ax.set_xticks(x); ax.set_xticklabels(names, fontsize=7.6)
    ax.set_ylabel("metric, % of best design"); ax.set_ylim(95, None)
    ax.legend(fontsize=6.6, frameon=False); ax.set_title(
        "(a) whole-frame optima cross-evaluated (GA, seed 5)", fontsize=9.2)
    ax = axes[1]
    ks = ["Mu_hog", "Vu", "Pu", "Mu_col"]
    kl = ["beam $M_u$", "beam $V_u$", "col. $P_u$", "col. $M_u$"]
    y = np.arange(len(ks))[::-1]
    for k, nm in enumerate(["cost-opt", "CO2-opt (green)"]):
        v = [rows[nm]["shift"][kk] for kk in ks]
        ax.barh(y+(0.5-k)*0.32, v, 0.3, color=[NAVY, GREEN][k], alpha=0.9, label=nm)
    ax.axvline(0, color="k", lw=0.7)
    ax.set_yticks(y); ax.set_yticklabels(kl, fontsize=8)
    ax.set_xlabel("governing-demand shift vs reference frame (%)")
    ax.legend(fontsize=6.8, frameon=False)
    ax.set_title("(b) closure of the frozen-demand assumption", fontsize=9.2)
    for a in axes: a.grid(alpha=0.2, lw=0.4, axis="x" if a is axes[1] else "y")
    fig.tight_layout()
    fig.savefig(f"{OUT}/fig_val_frame.png", dpi=300, bbox_inches="tight", facecolor="white")
    print("S6 closure figure saved")
