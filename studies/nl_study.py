# -*- coding: utf-8 -*-
"""Nonlinearity study on one beam and one column section of the RC frame:
cost-optimal vs carbon-optimal design, and sensitivity of the carbon optimum
to the rebar and concrete emission factors.  Publication-style figures."""
import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
RUNS = _os.environ.get("STUDIO_RUNS", _os.path.join(ROOT, "studies", "out", "runs"))
FIGS = _os.environ.get("STUDIO_FIGS", _os.path.join(ROOT, "studies", "out", "figs"))
_os.makedirs(RUNS, exist_ok=True); _os.makedirs(FIGS, exist_ok=True)
import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import engine as E

plt.rcParams.update({
    "font.family": "STIXGeneral", "mathtext.fontset": "stix",
    "font.size": 9.5, "axes.linewidth": 0.8,
    "xtick.direction": "in", "ytick.direction": "in",
    "xtick.top": True, "ytick.right": True,
})
OUT = FIGS
D = json.load(open(RUNS + "/section_demands.json"))
fc, fy = 25.0, 420.0
EC, EF = 224.94, 2.24                    # BEDEC concrete kg/m3, formwork kg/m2
CC, CS, CF = 90.0, 1.30, 25.0            # representative placed prices EUR/m3, EUR/kg, EUR/m2
ES_BEDEC, ES_GREEN = 2.82, 0.36
ROUTES = [("BEDEC", 2.82), ("BF-BOF", 1.99), ("world avg", 1.85),
          ("EAF grid", 0.67), ("green EAF", 0.36)]

# ============================================================ BEAM SECTION
b = D["bb"]                              # 250 mm, fixed
Mu, Vu = D["Mu_hog"], D["Vu"]
hs = np.linspace(400, 750, 141)
As_ = np.linspace(500, 4000, 176)
H, A = np.meshgrid(hs, As_)              # rows: As, cols: h

phiMn = np.zeros_like(H); epsT = np.zeros_like(H)
for i in range(A.shape[0]):
    for j in range(A.shape[1]):
        _, pm, et, _ = E._rc_flex_doubly(b, H[i, j]-60.0, 60.0, A[i, j], 226.0, fc, fy)
        phiMn[i, j] = pm; epsT[i, j] = et
d_ = H - 60.0
Vc = 0.17*np.sqrt(fc)*b*d_
phiVn = 0.75*(Vc + 0.66*np.sqrt(fc)*b*d_)
rho = A/(b*d_); rho_min = max(0.25*np.sqrt(fc), 1.4)/fy
feas_b = (phiMn >= Mu) & (phiVn >= Vu) & (epsT >= 0.004) & (rho >= rho_min) & (H <= 3*b)

# quantities per metre of beam
Vs_req = np.maximum(Vu/0.75 - Vc, 0.0)
Av = 2*78.5
s_st = np.minimum(d_/2.0, 600.0)
with np.errstate(divide="ignore"):
    s_cap = np.where(Vs_req > 1e-6, Av*fy*d_/np.maximum(Vs_req, 1e-9), 1e9)
s_st = np.maximum(80.0, np.minimum(s_st, s_cap))
st_len = 2*((b-80.0) + (H-80.0)) + 100.0
conc_b = b*H*1000.0*1e-9                                    # m3/m
steel_b = ((A + 226.0)*1000.0 + (1000.0/s_st)*st_len*78.5)*7850e-9   # kg/m
form_b = (b + 2*H)*1e-3                                     # m2/m
cost_b = CC*conc_b + CS*steel_b + CF*form_b
co2_b = lambda es: EC*conc_b + es*steel_b + EF*form_b

# ============================================================ COLUMN SECTION
bc = D["bc"]                             # 300 mm, fixed; symmetric cage As/2 per face
Pu, Mu_c = D["Pu"], D["Mu"]
lu = 3000.0
h_lo = lu/(0.3*22.0) + 1.0               # sway slenderness floor
hc_ = np.linspace(h_lo, 800, 140)
Ac_ = np.linspace(1200, 9800, 176)
Hc, Ax = np.meshgrid(hc_, Ac_)

phiPn = np.zeros_like(Hc)
for i in range(Ax.shape[0]):
    for j in range(Ax.shape[1]):
        e = max(Mu_c/Pu, 15.0 + 0.03*Hc[i, j])
        phiPn[i, j] = E._rc_phiPn_at_e(bc, Hc[i, j], Ax[i, j]/2, Ax[i, j]/2, fc, fy, e)
rho_c = Ax/(bc*Hc)
feas_c = (phiPn >= Pu) & (rho_c >= 0.01) & (rho_c <= 0.04)

s_tie = np.minimum(np.minimum(320.0, bc), Hc)
tie_len = 2*((bc-80.0) + (Hc-80.0)) + 150.0
conc_c = bc*Hc*1000.0*1e-9
steel_c = (Ax*1000.0 + (1000.0/s_tie)*tie_len*50.3)*7850e-9
form_c = 2*(bc + Hc)*1e-3
cost_c = CC*conc_c + CS*steel_c + CF*form_c
co2_c = lambda es: EC*conc_c + es*steel_c + EF*form_c

# ============================================================ optima + tables
def argmin_masked(Z, mask):
    Zm = np.where(mask, Z, np.inf)
    i, j = np.unravel_index(np.argmin(Zm), Zm.shape)
    return i, j

def summarize(name, Hg, Ag, mask, cost, co2f, conc, steel):
    rows = {}
    for lab, Z in [("cost", cost), ("co2_bedec", co2f(ES_BEDEC)),
                   ("co2_green", co2f(ES_GREEN))]:
        i, j = argmin_masked(Z, mask)
        rows[lab] = dict(h=float(Hg[i, j]), As=float(Ag[i, j]),
                         conc=float(conc[i, j]), steel=float(steel[i, j]),
                         cost=float(cost[i, j]),
                         co2_bedec=float(co2f(ES_BEDEC)[i, j]),
                         co2_green=float(co2f(ES_GREEN)[i, j]), ij=(int(i), int(j)))
    return rows

tab_b = summarize("beam", H, A, feas_b, cost_b, co2_b, conc_b, steel_b)
tab_c = summarize("column", Hc, Ax, feas_c, cost_c, co2_c, conc_c, steel_c)
json.dump({"beam": tab_b, "column": tab_c,
           "prices": {"conc": CC, "steel": CS, "form": CF},
           "demands": D},
          open(RUNS + "/nl_study.json", "w"), indent=1)
for nm, t in [("BEAM", tab_b), ("COLUMN", tab_c)]:
    print(f"--- {nm} ---")
    for k, r in t.items():
        print(f"{k:10s} h={r['h']:5.0f} As={r['As']:6.0f} conc={r['conc']:.4f} m3/m "
              f"steel={r['steel']:5.1f} kg/m cost={r['cost']:6.2f} "
              f"CO2(2.82)={r['co2_bedec']:6.1f} CO2(0.36)={r['co2_green']:5.1f}")

# ============================================================ contour figures
def panel(ax, Hg, Ag, Z, mask, title, unit, marks, cmap):
    Zp = np.where(mask, Z, np.nan)
    lv = np.linspace(np.nanmin(Zp), np.nanpercentile(Zp, 97), 18)
    cf = ax.contourf(Hg, Ag/1000.0, Zp, levels=lv, cmap=cmap)
    cl = ax.contour(Hg, Ag/1000.0, Zp, levels=lv[::3], colors="k",
                    linewidths=0.35, alpha=0.55)
    ax.clabel(cl, fmt="%.0f", fontsize=6, inline=True)
    ax.contourf(Hg, Ag/1000.0, (~mask).astype(float), levels=[0.5, 1.5],
                colors=["#d9dde3"], alpha=0.9)
    ax.contour(Hg, Ag/1000.0, mask.astype(float), levels=[0.5],
               colors="#8a1f1f", linewidths=1.5)
    for (ij, mk, lab, col) in marks:
        i, j = ij
        ax.plot(Hg[i, j], Ag[i, j]/1000.0, mk, ms=9, mfc=col, mec="k",
                mew=0.9, zorder=6, label=lab)
    ax.set_title(title, fontsize=9.5)
    ax.set_xlabel("section depth $h$ (mm)")
    cb = plt.colorbar(cf, ax=ax, shrink=0.92, pad=0.02)
    cb.set_label(unit, fontsize=8); cb.ax.tick_params(labelsize=7)

def contour_fig(Hg, Ag, mask, cost, co2f, tab, fname, member, ylab):
    fig, axes = plt.subplots(1, 3, figsize=(10.6, 3.35), sharey=True)
    marks = [ (tab["cost"]["ij"], "*", "cost optimum", "black"),
              (tab["co2_bedec"]["ij"], "o", "CO$_2$ opt. (BEDEC 2.82)", "white"),
              (tab["co2_green"]["ij"], "^", "CO$_2$ opt. (green 0.36)", "#2e9e63") ]
    panel(axes[0], Hg, Ag, cost, mask, "(a) cost", "EUR per m", marks, "Blues")
    panel(axes[1], Hg, Ag, co2f(ES_BEDEC), mask,
          "(b) embodied CO$_2$ — BEDEC rebar (2.82 kg/kg)", "kg CO$_2$ per m",
          marks, "YlOrBr")
    panel(axes[2], Hg, Ag, co2f(ES_GREEN), mask,
          "(c) embodied CO$_2$ — green-EAF rebar (0.36 kg/kg)", "kg CO$_2$ per m",
          marks, "YlGn")
    axes[0].set_ylabel(ylab)
    axes[0].legend(loc="upper right", fontsize=6.6, frameon=True, framealpha=0.95)
    fig.suptitle(member, fontsize=10.5, y=1.02)
    fig.tight_layout()
    fig.savefig(fname, dpi=300, bbox_inches="tight", facecolor="white")
    plt.close(fig)

contour_fig(H, A, feas_b, cost_b, co2_b, tab_b, f"{OUT}/fig_nl_beam.png",
    "Frame beam hogging section (b = 250 mm; $M_u$ = 178.9 kN·m, $V_u$ = 141.7 kN)",
    "tension steel $A_s$ (10$^3$ mm$^2$)")
contour_fig(Hc, Ax, feas_c, cost_c, co2_c, tab_c, f"{OUT}/fig_nl_column.png",
    "Frame column section (b = 300 mm, symmetric cage; $P_u$ = 134.5 kN, $M_u$ = 149.9 kN·m)",
    "total steel $A_{s,tot}$ (10$^3$ mm$^2$)")

# ============================================================ factor sweeps
es_sw = np.linspace(0.30, 3.00, 109)
def sweep_es(Hg, Ag, mask, co2f, steel, conc):
    hh, aa, ss, zz, cc_ = [], [], [], [], []
    for es in es_sw:
        i, j = argmin_masked(co2f(es), mask)
        hh.append(Hg[i, j]); aa.append(Ag[i, j]); ss.append(steel[i, j])
        zz.append(co2f(es)[i, j]); cc_.append(conc[i, j])
    return map(np.array, (hh, aa, ss, zz, cc_))
bh, ba, bs, bz, bcn = sweep_es(H, A, feas_b, co2_b, steel_b, conc_b)
ch, ca, cs_, cz, ccn = sweep_es(Hc, Ax, feas_c, co2_c, steel_c, conc_c)
# CO2 of the FIXED cost-optimal design as es varies (straight lines)
ib, jb = tab_b["cost"]["ij"]; ic, jc = tab_c["cost"]["ij"]
bz_cost = EC*conc_b[ib, jb] + es_sw*steel_b[ib, jb] + EF*form_b[ib, jb]
cz_cost = EC*conc_c[ic, jc] + es_sw*steel_c[ic, jc] + EF*form_c[ic, jc]

ec_sw = np.linspace(140, 300, 66)
def sweep_ec(Hg, Ag, mask, conc, steel, form, es):
    hh, zz = [], []
    for ec in ec_sw:
        Z = ec*conc + es*steel + EF*form
        i, j = argmin_masked(Z, mask)
        hh.append(Hg[i, j]); zz.append(Z[i, j])
    return np.array(hh), np.array(zz)
bh28, _ = sweep_ec(H, A, feas_b, conc_b, steel_b, form_b, ES_BEDEC)
bh04, _ = sweep_ec(H, A, feas_b, conc_b, steel_b, form_b, ES_GREEN)
ch28, _ = sweep_ec(Hc, Ax, feas_c, conc_c, steel_c, form_c, ES_BEDEC)
ch04, _ = sweep_ec(Hc, Ax, feas_c, conc_c, steel_c, form_c, ES_GREEN)

NAVY="#16263f"; TEAL="#1a8fa0"; AMBER="#c87f16"; GREEN="#2e9e63"; GREY="#6c7891"
fig, axes = plt.subplots(2, 2, figsize=(9.4, 6.0))
ax = axes[0,0]
ax.plot(es_sw, bh, color=NAVY, lw=1.7, label="depth $h^{*}$")
ax2 = ax.twinx()
ax2.plot(es_sw, bs, color=AMBER, lw=1.7, ls="--", label="steel $m_s^{*}$")
ax.set_xlabel("rebar emission factor $e_s$ (kg CO$_2$/kg)")
ax.set_ylabel("optimal depth $h^{*}$ (mm)", color=NAVY)
ax2.set_ylabel("optimal steel (kg/m)", color=AMBER)
ax.set_title("(a) beam: carbon-optimal design vs $e_s$", fontsize=9.5)
ax = axes[0,1]
ax.plot(es_sw, ch, color=NAVY, lw=1.7)
ax2 = ax.twinx()
ax2.plot(es_sw, cs_, color=AMBER, lw=1.7, ls="--")
ax.set_xlabel("rebar emission factor $e_s$ (kg CO$_2$/kg)")
ax.set_ylabel("optimal depth $h^{*}$ (mm)", color=NAVY)
ax2.set_ylabel("optimal steel (kg/m)", color=AMBER)
ax.set_title("(b) column: carbon-optimal design vs $e_s$", fontsize=9.5)
ax = axes[1,0]
ax.plot(es_sw, bz, color=TEAL, lw=1.8, label="beam: CO$_2$-optimal design")
ax.plot(es_sw, bz_cost, color=TEAL, lw=1.3, ls=":", label="beam: cost-optimal design")
ax.plot(es_sw, cz, color=NAVY, lw=1.8, label="column: CO$_2$-optimal design")
ax.plot(es_sw, cz_cost, color=NAVY, lw=1.3, ls=":", label="column: cost-optimal design")
for lab, es in ROUTES:
    ax.axvline(es, color=GREY, lw=0.6, alpha=0.55)
    ax.text(es, ax.get_ylim()[1]*0.99, " "+lab, rotation=90, va="top",
            fontsize=6.0, color=GREY)
ax.set_xlabel("rebar emission factor $e_s$ (kg CO$_2$/kg)")
ax.set_ylabel("embodied CO$_2$ at optimum (kg/m)")
ax.legend(fontsize=6.8, frameon=False, loc="center right")
ax.set_title("(c) carbon penalty of designing for cost", fontsize=9.5)
ax = axes[1,1]
ax.plot(ec_sw, bh28, color=TEAL, lw=1.7, label="beam, $e_s$=2.82")
ax.plot(ec_sw, bh04, color=TEAL, lw=1.7, ls="--", label="beam, $e_s$=0.36")
ax.plot(ec_sw, ch28, color=NAVY, lw=1.7, label="column, $e_s$=2.82")
ax.plot(ec_sw, ch04, color=NAVY, lw=1.7, ls="--", label="column, $e_s$=0.36")
ax.axvline(EC, color=GREY, lw=0.7, alpha=0.6)
ax.text(EC, ax.get_ylim()[0]+8, " BEDEC 224.94", rotation=90, fontsize=6.0,
        color=GREY, va="bottom")
ax.set_xlabel("concrete emission factor $e_c$ (kg CO$_2$/m$^3$)")
ax.set_ylabel("optimal depth $h^{*}$ (mm)")
ax.legend(fontsize=6.8, frameon=False)
ax.set_title("(d) concrete-factor variability: optimal depth", fontsize=9.5)
for a in axes.flat:
    a.grid(alpha=0.22, lw=0.4)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_nl_sweeps.png", dpi=300, bbox_inches="tight", facecolor="white")
print("figures saved")
