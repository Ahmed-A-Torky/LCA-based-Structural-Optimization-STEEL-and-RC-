# -*- coding: utf-8 -*-
"""Revised nonlinearity-study figures: every feasibility boundary segment is
labelled with its governing limit state; phi conventions stated; infeasible
domain hatched for print; cost-optimal references added to the sweeps."""
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
    "xtick.top": True, "ytick.right": True, "hatch.linewidth": 0.4,
})
OUT = FIGS
D = json.load(open(RUNS + "/section_demands.json"))
fc, fy = 25.0, 420.0
EC, EF = 224.94, 2.24
CC, CS, CF = 90.0, 1.30, 25.0
ES_BEDEC, ES_GREEN = 2.82, 0.36
ROUTES = [("BEDEC", 2.82), ("BF-BOF", 1.99), ("world avg", 1.85),
          ("EAF grid", 0.67), ("green EAF", 0.36)]

# ---------------------------------------------------------------- beam grids
b = D["bb"]; Mu, Vu = D["Mu_hog"], D["Vu"]
hs = np.linspace(400, 750, 141)
As_ = np.linspace(500, 4000, 176)
H, A = np.meshgrid(hs, As_)
phiMn = np.zeros_like(H); epsT = np.zeros_like(H)
for i in range(A.shape[0]):
    for j in range(A.shape[1]):
        _, pm, et, _ = E._rc_flex_doubly(b, H[i, j]-60.0, 60.0, A[i, j], 226.0, fc, fy)
        phiMn[i, j] = pm; epsT[i, j] = et
d_ = H - 60.0
Vc = 0.17*np.sqrt(fc)*b*d_
phiVn = 0.75*(Vc + 0.66*np.sqrt(fc)*b*d_)
rho = A/(b*d_); rho_min = max(0.25*np.sqrt(fc), 1.4)/fy
m_flex = phiMn >= Mu
m_duct = epsT >= 0.004
feas_b = m_flex & (phiVn >= Vu) & m_duct & (rho >= rho_min) & (H <= 3*b)
Vs_req = np.maximum(Vu/0.75 - Vc, 0.0)
s_st = np.minimum(d_/2.0, 600.0)
with np.errstate(divide="ignore"):
    s_cap = np.where(Vs_req > 1e-6, 2*78.5*fy*d_/np.maximum(Vs_req, 1e-9), 1e9)
s_st = np.maximum(80.0, np.minimum(s_st, s_cap))
st_len = 2*((b-80.0) + (H-80.0)) + 100.0
conc_b = b*H*1e-6
steel_b = ((A + 226.0)*1000.0 + (1000.0/s_st)*st_len*78.5)*7850e-9
form_b = (b + 2*H)*1e-3
cost_b = CC*conc_b + CS*steel_b + CF*form_b
co2_b = lambda es: EC*conc_b + es*steel_b + EF*form_b

# -------------------------------------------------------------- column grids
bc = D["bc"]; Pu, Mu_c = D["Pu"], D["Mu"]
lu = 3000.0; h_lo = lu/(0.3*22.0) + 1.0
hc_ = np.linspace(h_lo, 800, 140)
Ac_ = np.linspace(1200, 9800, 176)
Hc, Ax = np.meshgrid(hc_, Ac_)
phiPn = np.zeros_like(Hc)
for i in range(Ax.shape[0]):
    for j in range(Ax.shape[1]):
        e = max(Mu_c/Pu, 15.0 + 0.03*Hc[i, j])
        phiPn[i, j] = E._rc_phiPn_at_e(bc, Hc[i, j], Ax[i, j]/2, Ax[i, j]/2, fc, fy, e)
rho_c = Ax/(bc*Hc)
m_pm = phiPn >= Pu
feas_c = m_pm & (rho_c >= 0.01) & (rho_c <= 0.04)
s_tie = np.minimum(np.minimum(320.0, bc), Hc)
tie_len = 2*((bc-80.0) + (Hc-80.0)) + 150.0
conc_c = bc*Hc*1e-6
steel_c = (Ax*1000.0 + (1000.0/s_tie)*tie_len*50.3)*7850e-9
form_c = 2*(bc + Hc)*1e-3
cost_c = CC*conc_c + CS*steel_c + CF*form_c
co2_c = lambda es: EC*conc_c + es*steel_c + EF*form_c

def argmin_masked(Z, mask):
    Zm = np.where(mask, Z, np.inf)
    return np.unravel_index(np.argmin(Zm), Zm.shape)

tab = json.load(open(RUNS + "/nl_study.json"))

# ------------------------------------------------------- boundary label tool
def edge(mask, hgrid, agrid, h_target, side):
    j = int(np.argmin(np.abs(hgrid - h_target)))
    idx = np.where(mask[:, j])[0]
    if len(idx) == 0: return None
    i = idx[0] if side == "lo" else idx[-1]
    return hgrid[j], agrid[i]/1000.0

def seg_label(ax, mask, hgrid, agrid, h1, h2, side, text, off, color="#8a1f1f"):
    p1 = edge(mask, hgrid, agrid, h1, side); p2 = edge(mask, hgrid, agrid, h2, side)
    if p1 is None or p2 is None: return
    t1 = ax.transData.transform(p1); t2 = ax.transData.transform(p2)
    ang = np.degrees(np.arctan2(t2[1]-t1[1], t2[0]-t1[0]))
    mid = ((p1[0]+p2[0])/2, (p1[1]+p2[1])/2 + off)
    ax.text(*mid, text, rotation=ang, rotation_mode="anchor",
            ha="center", va="center", fontsize=6.6, color=color, style="italic")

def panel(ax, Hg, Ag, Z, mask, title, unit, marks, cmap):
    Zp = np.where(mask, Z, np.nan)
    lv = np.linspace(np.nanmin(Zp), np.nanpercentile(Zp, 97), 18)
    cf = ax.contourf(Hg, Ag/1000.0, Zp, levels=lv, cmap=cmap)
    cl = ax.contour(Hg, Ag/1000.0, Zp, levels=lv[::3], colors="k",
                    linewidths=0.35, alpha=0.5)
    ax.clabel(cl, fmt="%.0f", fontsize=6, inline=True)
    ax.contourf(Hg, Ag/1000.0, (~mask).astype(float), levels=[0.5, 1.5],
                colors=["#e4e7ec"], hatches=["////"])
    ax.contour(Hg, Ag/1000.0, mask.astype(float), levels=[0.5],
               colors="#8a1f1f", linewidths=1.5)
    for (ij, mk, lab, col, ms) in marks:
        i, j = ij
        ax.plot(Hg[i, j], Ag[i, j]/1000.0, mk, ms=ms, mfc=col, mec="k",
                mew=1.0, zorder=6, label=lab)
    ax.set_title(title, fontsize=9.3)
    ax.set_xlabel("section depth $h$ (mm)")
    cb = plt.colorbar(cf, ax=ax, shrink=0.92, pad=0.02)
    cb.set_label(unit, fontsize=8); cb.ax.tick_params(labelsize=7)

def marks_of(t):
    return [(tuple(t["cost"]["ij"]), "*", "cost optimum", "black", 12),
            (tuple(t["co2_bedec"]["ij"]), "o", "CO$_2$ opt. (BEDEC, 2.82)", "white", 8),
            (tuple(t["co2_green"]["ij"]), "^", "CO$_2$ opt. (green EAF, 0.36)", "#2e9e63", 8)]

# ------------------------------------------------------------- beam figure
fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.5), sharey=True)
mb = marks_of(tab["beam"])
panel(axes[0], H, A, cost_b, feas_b, "(a) cost  $C(h, A_s)$", "Cost (\u20ac/m)", mb, "Blues")
panel(axes[1], H, A, co2_b(ES_BEDEC), feas_b,
      "(b) CO$_2$ \u2014 BEDEC rebar, $e_s$ = 2.82 kg/kg", "CO$_2$ (kg/m)", mb, "YlOrBr")
panel(axes[2], H, A, co2_b(ES_GREEN), feas_b,
      "(c) CO$_2$ \u2014 green-EAF rebar, $e_s$ = 0.36 kg/kg", "CO$_2$ (kg/m)", mb, "YlGn")
for ax in axes:
    seg_label(ax, feas_b, hs, As_, 560, 700, "lo",
              "flexure  $\\phi M_n = M_u$", -0.16)
    seg_label(ax, feas_b, hs, As_, 470, 620, "hi",
              "ductility  $\\varepsilon_t = 0.004$", 0.22)
    ax.text(742, 0.72, "$h = 3b$", rotation=90, fontsize=6.6,
            color="#8a1f1f", style="italic", va="bottom", ha="center")
axes[0].text(660, 1.45, "feasible domain", fontsize=6.8, color="#3a4658",
             ha="center", style="italic")
axes[0].set_ylabel("tension steel $A_s$ (10$^3$ mm$^2$)")
axes[0].legend(loc="upper left", fontsize=6.4, frameon=True, framealpha=0.95)
fig.suptitle("Frame beam hogging section \u2014 $b$ = 250 mm; $M_u$ = 178.9 kN\u00b7m, "
             "$V_u$ = 141.7 kN;  $A_s'$ = 226 mm$^2$ hangers; $\\phi$ per ACI 318 transition",
             fontsize=9.8, y=1.03)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_nl_beam.png", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)

# ------------------------------------------------------------ column figure
fig, axes = plt.subplots(1, 3, figsize=(10.8, 3.5), sharey=True)
mc = marks_of(tab["column"])
panel(axes[0], Hc, Ax, cost_c, feas_c, "(a) cost  $C(h, A_{s,tot})$", "Cost (\u20ac/m)", mc, "Blues")
panel(axes[1], Hc, Ax, co2_c(ES_BEDEC), feas_c,
      "(b) CO$_2$ \u2014 BEDEC rebar, $e_s$ = 2.82 kg/kg", "CO$_2$ (kg/m)", mc, "YlOrBr")
panel(axes[2], Hc, Ax, co2_c(ES_GREEN), feas_c,
      "(c) CO$_2$ \u2014 green-EAF rebar, $e_s$ = 0.36 kg/kg", "CO$_2$ (kg/m)", mc, "YlGn")
for ax in axes:
    seg_label(ax, feas_c, hc_, Ac_, 470, 540, "lo",
              "interaction  $\\phi P_n(e) = P_u$", -0.42)
    seg_label(ax, feas_c, hc_, Ac_, 660, 780, "lo",
              "$\\rho = 1\\%$", -0.40)
    seg_label(ax, feas_c, hc_, Ac_, 520, 700, "hi",
              "$\\rho = 4\\%$", 0.48)
    ax.text(h_lo + 9, 6.4, "sway slenderness  $k\\ell_u/r = 22$", rotation=90,
            fontsize=6.4, color="#8a1f1f", style="italic", va="center")
axes[0].text(650, 3.4, "feasible domain", fontsize=6.8, color="#3a4658",
             ha="center", style="italic")
axes[0].set_ylabel("total steel $A_{s,tot}$ (10$^3$ mm$^2$)")
axes[0].legend(loc="upper left", fontsize=6.4, frameon=True, framealpha=0.95)
fig.suptitle("Frame column section \u2014 $b$ = 300 mm, symmetric cage ($A_{s,tot}/2$ per face); "
             "$P_u$ = 134.5 kN, $M_u$ = 149.9 kN\u00b7m ($e$ = 1114 mm);  $\\phi$ = 0.65 uniform (conservative)",
             fontsize=9.8, y=1.03)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_nl_column.png", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)

# ------------------------------------------------------------- sweeps figure
es_sw = np.linspace(0.30, 3.00, 109)
def sweep_es(Hg, Ag, mask, co2f, steel):
    hh, ss, zz = [], [], []
    for es in es_sw:
        i, j = argmin_masked(co2f(es), mask)
        hh.append(Hg[i, j]); ss.append(steel[i, j]); zz.append(co2f(es)[i, j])
    return map(np.array, (hh, ss, zz))
bh, bs, bz = sweep_es(H, A, feas_b, co2_b, steel_b)
ch, cs_, cz = sweep_es(Hc, Ax, feas_c, co2_c, steel_c)
ib, jb = tab["beam"]["cost"]["ij"]; ic, jc = tab["column"]["cost"]["ij"]
bz_cost = EC*conc_b[ib, jb] + es_sw*steel_b[ib, jb] + EF*form_b[ib, jb]
cz_cost = EC*conc_c[ic, jc] + es_sw*steel_c[ic, jc] + EF*form_c[ic, jc]
ec_sw = np.linspace(140, 300, 66)
def sweep_ec(Hg, Ag, mask, conc, steel, form, es):
    hh = []
    for ec in ec_sw:
        i, j = argmin_masked(ec*conc + es*steel + EF*form, mask)
        hh.append(Hg[i, j])
    return np.array(hh)
bh28 = sweep_ec(H, A, feas_b, conc_b, steel_b, form_b, ES_BEDEC)
bh04 = sweep_ec(H, A, feas_b, conc_b, steel_b, form_b, ES_GREEN)
ch28 = sweep_ec(Hc, Ax, feas_c, conc_c, steel_c, form_c, ES_BEDEC)
ch04 = sweep_ec(Hc, Ax, feas_c, conc_c, steel_c, form_c, ES_GREEN)

NAVY="#16263f"; TEAL="#1a8fa0"; AMBER="#c87f16"; GREY="#6c7891"
fig, axes = plt.subplots(2, 2, figsize=(9.6, 6.2))
for ax, hh, ss, hstar, ttl in [
        (axes[0,0], bh, bs, tab["beam"]["cost"]["h"],
         "(a) beam: carbon-optimal design vs rebar factor $e_s$"),
        (axes[0,1], ch, cs_, tab["column"]["cost"]["h"],
         "(b) column: carbon-optimal design vs rebar factor $e_s$")]:
    l1, = ax.plot(es_sw, hh, color=NAVY, lw=1.8, label="optimal depth $h^{*}$")
    l3 = ax.axhline(hstar, color=GREY, lw=1.1, ls="--")
    ax.text(2.96, hstar, "cost-optimal $h^{*}$ ", ha="right", va="bottom",
            fontsize=6.6, color=GREY)
    ax2 = ax.twinx()
    l2, = ax2.plot(es_sw, ss, color=AMBER, lw=1.8, ls="-.",
                   label="optimal steel $m_s^{*}$")
    for _, es in ROUTES:
        ax.axvline(es, color=GREY, lw=0.5, alpha=0.4)
    ax.set_xlabel("rebar emission factor $e_s$ (kg CO$_2$/kg)")
    ax.set_ylabel("optimal depth $h^{*}$ (mm)", color=NAVY)
    ax2.set_ylabel("optimal steel (kg/m)", color=AMBER)
    ax2.tick_params(axis="y", colors=AMBER); ax.tick_params(axis="y", colors=NAVY)
    ax.legend(handles=[l1, l2], fontsize=6.8, frameon=False, loc="center right")
    ax.set_title(ttl, fontsize=9.4)
ax = axes[1,0]
ax.plot(es_sw, bz, color=TEAL, lw=1.9, label="beam \u2014 re-optimized for CO$_2$")
ax.plot(es_sw, bz_cost, color=TEAL, lw=1.2, ls=":",
        label="beam \u2014 cost-optimal design (frozen)")
ax.plot(es_sw, cz, color=NAVY, lw=1.9, label="column \u2014 re-optimized for CO$_2$")
ax.plot(es_sw, cz_cost, color=NAVY, lw=1.2, ls=":",
        label="column \u2014 cost-optimal design (frozen)")
for lab, es in ROUTES:
    ax.axvline(es, color=GREY, lw=0.55, alpha=0.5)
    ax.text(es, 27, " "+lab, rotation=90, va="bottom", fontsize=5.8, color=GREY)
ax.set_xlabel("rebar emission factor $e_s$ (kg CO$_2$/kg)")
ax.set_ylabel("embodied CO$_2$ (kg/m)")
ax.legend(fontsize=6.6, frameon=False, loc="upper left")
ax.set_title("(c) carbon cost of designing for cost: frozen vs re-optimized",
             fontsize=9.4)
ax = axes[1,1]
ax.plot(ec_sw, bh28, color=TEAL, lw=1.8, label="beam, $e_s$ = 2.82")
ax.plot(ec_sw, bh04, color=TEAL, lw=1.8, ls="--", label="beam, $e_s$ = 0.36")
ax.plot(ec_sw, ch28, color=NAVY, lw=1.8, label="column, $e_s$ = 2.82")
ax.plot(ec_sw, ch04, color=NAVY, lw=1.8, ls="--", label="column, $e_s$ = 0.36")
ax.axvline(EC, color=GREY, lw=0.8, alpha=0.7)
ax.text(EC+2, 462, "BEDEC 224.94", rotation=90, fontsize=6.0, color=GREY, va="bottom")
ax.annotate("low-clinker\nblends", xy=(152, 447), fontsize=6.2, color=GREY,
            ha="center", style="italic")
ax.annotate("high-clinker\nmixes", xy=(288, 447), fontsize=6.2, color=GREY,
            ha="center", style="italic")
ax.set_xlabel("concrete emission factor $e_c$ (kg CO$_2$/m$^3$)")
ax.set_ylabel("optimal depth $h^{*}$ (mm)")
ax.legend(fontsize=6.8, frameon=False, loc="center right")
ax.set_title("(d) concrete-factor variability: optimal depth", fontsize=9.4)
for a in axes.flat:
    a.grid(alpha=0.2, lw=0.4)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_nl_sweeps.png", dpi=300, bbox_inches="tight", facecolor="white")
print("revised figures saved")
