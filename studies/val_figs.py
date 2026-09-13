# -*- coding: utf-8 -*-
"""Validation set 1: (S1) mechanics verification vs closed forms; (S2) cost-CO2
Pareto fronts per route; (S3) price/emission ratio regime map; (S4) constraint
utilization audit at all six optima."""
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

plt.rcParams.update({"font.family": "STIXGeneral", "mathtext.fontset": "stix",
    "font.size": 9.5, "axes.linewidth": 0.8, "xtick.direction": "in",
    "ytick.direction": "in", "xtick.top": True, "ytick.right": True})
OUT = FIGS
D = json.load(open(RUNS + "/section_demands.json"))
T = json.load(open(RUNS + "/nl_study.json"))
fc, fy = 25.0, 420.0
EC, EF = 224.94, 2.24; CC, CS, CF = 90.0, 1.30, 25.0
NAVY="#16263f"; TEAL="#1a8fa0"; AMBER="#c87f16"; GREEN="#2e9e63"; GREY="#6c7891"; RED="#8a1f1f"

# =============================== S1: mechanics verification =================
fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.5))
# (a) beam flexure: engine doubly solver vs closed-form singly
ax = axes[0]
b, h = 250.0, 505.0; d = h - 60.0
As = np.linspace(200, 4200, 240)
a_cf = As*fy/(0.85*fc*b); c_cf = a_cf/E._beta1(fc)
eps_cf = 0.003*(d - c_cf)/c_cf
phi_cf = np.where(eps_cf >= 0.005, 0.90,
          np.where(eps_cf <= 0.002, 0.65, 0.65 + 0.25*(eps_cf-0.002)/0.003))
Mn_cf = As*fy*(d - a_cf/2.0)
eng0 = np.array([E._rc_flex_doubly(b, d, 60.0, a, 0.0, fc, fy)[1] for a in As])
eng226 = np.array([E._rc_flex_doubly(b, d, 60.0, a, 226.0, fc, fy)[1] for a in As])
valid = eps_cf >= fy/200000.0            # closed form assumes yielding steel
err = np.max(np.abs(eng0[valid] - (phi_cf*Mn_cf)[valid])/np.maximum((phi_cf*Mn_cf)[valid], 1))
ax.plot(As/1e3, phi_cf*Mn_cf/1e6, color="k", lw=2.6, alpha=0.35,
        label="closed form, singly ($A_s'$ = 0)")
ax.plot(As/1e3, eng0/1e6, color=NAVY, lw=1.1, ls="--",
        label="strain-compat. solver, $A_s'$ = 0")
ax.plot(As/1e3, eng226/1e6, color=TEAL, lw=1.5,
        label="strain-compat. solver, $A_s'$ = 226 mm$^2$")
iTC = np.argmin(np.abs(eps_cf - 0.005)); iCC = np.argmin(np.abs(eps_cf - 0.002))
for i, lab in [(iTC, "$\\varepsilon_t$ = 0.005"), (iCC, "$\\varepsilon_t$ = 0.002")]:
    ax.axvline(As[i]/1e3, color=GREY, lw=0.8, ls=":")
    ax.text(As[i]/1e3, ax.get_ylim()[0]+12, " "+lab, rotation=90, fontsize=6.4,
            color=GREY, va="bottom")
ax.set_xlabel("tension steel $A_s$ (10$^3$ mm$^2$)")
ax.set_ylabel("$\\phi M_n$ (kN\u00b7m)")
ax.set_title(f"(a) beam flexure verification (b\u00d7h = 250\u00d7505); "
             f"max dev. = {err*100:.1e}% for $\\varepsilon_t \\geq \\varepsilon_y$", fontsize=9.2)
iY = np.argmin(np.abs(eps_cf - fy/200000.0))
ax.axvspan(As[iY]/1e3, As[-1]/1e3, color="#8a1f1f", alpha=0.05)
ax.text((As[iY]+As[-1])/2e3, ax.get_ylim()[1]*0.30,
        "closed form invalid:\nsteel below yield\n(solver exact)",
        fontsize=6.4, color="#8a1f1f", ha="center", style="italic")
ax.legend(fontsize=6.8, frameon=False, loc="lower right"); ax.grid(alpha=0.2, lw=0.4)
# (b) column P-M diagram with hand anchors and demand ray
ax = axes[1]
bc, hc = 300.0, float(T["column"]["co2_bedec"]["h"])
Asf = float(T["column"]["co2_bedec"]["As"])/2.0
cs = np.linspace(0.02*hc, 6*hc, 400)
PM = np.array([E._rc_pm_section(bc, hc, Asf, Asf, fc, fy, c) for c in cs])
Po = 0.85*fc*(bc*hc - 2*Asf) + fy*2*Asf
Pn, Mn = PM[:,0], PM[:,1]
ax.plot(Mn/1e6, Pn/1e3, color=GREY, lw=1.0, ls="--", label="nominal $P_n$\u2013$M_n$")
Pdes = 0.65*np.minimum(Pn, 0.80*Po); Mdes = 0.65*Mn
ax.plot(Mdes/1e6, Pdes/1e3, color=NAVY, lw=1.9,
        label="design $\\phi P_n$\u2013$\\phi M_n$ ($\\phi$ = 0.65, cap 0.80$P_o$)")
# anchors
d_c = hc - 60.0
cb = 0.003/(0.003 + fy/200000.0)*d_c
Pb, Mb = E._rc_pm_section(bc, hc, Asf, Asf, fc, fy, cb)
Mn0, _, _, _ = E._rc_flex_doubly(bc, d_c, 60.0, Asf, Asf, fc, fy)
# pure-bending point from the PM curve (Pn = 0 crossing)
i0 = np.argmin(np.abs(Pn)); dev_pb = abs(Mn[i0]-Mn0)/Mn0*100
ax.plot(0.65*0.80*Po*0/1e6 + Mdes[np.argmax(Pdes)]/1e6, 0.65*0.80*Po/1e3, "s",
        ms=6, mfc="white", mec="k", label="axial cap 0.80$\\phi P_o$ (formula)")
ax.plot(0.65*Mb/1e6, 0.65*Pb/1e3, "D", ms=6, mfc=AMBER, mec="k",
        label="balanced point ($c_b$ = %d mm)" % cb)
ax.plot(0.65*Mn0/1e6, 0, "o", ms=7, mfc=GREEN, mec="k",
        label="pure bending via flexural solver (dev. %.2f%%)" % dev_pb)
Tn = -fy*2*Asf
ax.plot(0, 0.65*Tn/1e3, "v", ms=6, mfc="white", mec="k",
        label="pure tension $-\\phi f_y A_{s,tot}$")
# demand ray e = 1114 mm and located capacity
e = D["Mu"]/D["Pu"]
phiPn_e = E._rc_phiPn_at_e(bc, hc, Asf, Asf, fc, fy, e)
Mm = np.linspace(0, max(Mdes)/1e6, 50)
ax.plot(Mm, Mm*1e6/e/1e3, color=RED, lw=1.0, ls=":")
ax.plot(phiPn_e*e/1e6, phiPn_e/1e3, "*", ms=13, mfc=RED, mec="k",
        label="$\\phi P_n(e)$ by bisection")
ax.plot(D["Mu"]/1e6, D["Pu"]/1e3, "P", ms=8, mfc="white", mec=RED,
        label="demand ($P_u$, $M_u$)")
ax.text(Mm[-12], Mm[-12]*1e6/e/1e3+55, "$e$ = 1114 mm", fontsize=6.6,
        color=RED, rotation=13)
ax.axhline(0, color="k", lw=0.5)
ax.set_xlabel("$M$ (kN\u00b7m)"); ax.set_ylabel("$P$ (kN)")
ax.set_title("(b) column interaction verification (300\u00d7%d, $\\rho$ = %.1f%%)"
             % (hc, 2*Asf/(bc*hc)*100), fontsize=9.2)
ax.legend(fontsize=6.0, frameon=False, loc="upper right")
ax.grid(alpha=0.2, lw=0.4)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_val_mech.png", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)
print(f"S1 mech: singly-vs-solver max dev {err*100:.2e}% | pure-bending PM-vs-flex dev {dev_pb:.3f}%")

# ============ recompute the section grids (as in the study) =================
Mu, Vu = D["Mu_hog"], D["Vu"]
hs = np.linspace(400, 750, 141); As_ = np.linspace(500, 4000, 176)
H, A = np.meshgrid(hs, As_)
phiMn = np.zeros_like(H); epsT = np.zeros_like(H)
for i in range(A.shape[0]):
    for j in range(A.shape[1]):
        _, pm, et, _ = E._rc_flex_doubly(250.0, H[i,j]-60.0, 60.0, A[i,j], 226.0, fc, fy)
        phiMn[i,j] = pm; epsT[i,j] = et
d_ = H - 60.0
Vc = 0.17*np.sqrt(fc)*250*d_
phiVn = 0.75*(Vc + 0.66*np.sqrt(fc)*250*d_)
rho = A/(250*d_); rmin = max(0.25*np.sqrt(fc), 1.4)/fy
feas_b = (phiMn >= Mu) & (phiVn >= Vu) & (epsT >= 0.004) & (rho >= rmin) & (H <= 750)
Vs = np.maximum(Vu/0.75 - Vc, 0.0)
s_st = np.maximum(80.0, np.minimum(np.minimum(d_/2, 600.0),
        np.where(Vs > 1e-6, 2*78.5*fy*d_/np.maximum(Vs, 1e-9), 1e9)))
stl = 2*((250-80.0)+(H-80.0))+100.0
conc_b = 250*H*1e-6
steel_b = ((A+226.0)*1000.0 + (1000.0/s_st)*stl*78.5)*7850e-9
form_b = (250+2*H)*1e-3
cost_b = CC*conc_b + CS*steel_b + CF*form_b

Pu, Mu_c = D["Pu"], D["Mu"]
h_lo = 3000.0/(0.3*22.0) + 1.0
hc_ = np.linspace(h_lo, 800, 140); Ac_ = np.linspace(1200, 9800, 176)
Hc, Ax = np.meshgrid(hc_, Ac_)
phiPn = np.zeros_like(Hc)
for i in range(Ax.shape[0]):
    for j in range(Ax.shape[1]):
        ee = max(Mu_c/Pu, 15.0 + 0.03*Hc[i,j])
        phiPn[i,j] = E._rc_phiPn_at_e(300.0, Hc[i,j], Ax[i,j]/2, Ax[i,j]/2, fc, fy, ee)
rho_c = Ax/(300*Hc)
feas_c = (phiPn >= Pu) & (rho_c >= 0.01) & (rho_c <= 0.04)
tie = 2*((300-80.0)+(Hc-80.0))+150.0
s_tie = np.minimum(np.minimum(320.0, 300.0), Hc)
conc_c = 300*Hc*1e-6
steel_c = (Ax*1000.0 + (1000.0/s_tie)*tie*50.3)*7850e-9
form_c = 2*(300+Hc)*1e-3
cost_c = CC*conc_c + CS*steel_c + CF*form_c

# ============================== S2: Pareto fronts ===========================
def front(cost, co2, mask):
    c = cost[mask].ravel(); z = co2[mask].ravel()
    o = np.argsort(c); c, z = c[o], z[o]
    zmin = np.minimum.accumulate(z)
    keep = z <= zmin + 1e-12
    return c[keep], z[keep]

ROUTES = [("BEDEC 2.82", 2.82, "#c87f16"), ("BF-BOF 1.99", 1.99, "#8a5a12"),
          ("world avg 1.85", 1.85, "#6c7891"), ("EAF 0.67", 0.67, "#1a8fa0"),
          ("green 0.36", 0.36, "#2e9e63")]
fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.5))
slopes = {}
for ax, cost, conc, steel, form, mask, tt, nm in [
        (axes[0], cost_b, conc_b, steel_b, form_b, feas_b, "(a) beam section", "beam"),
        (axes[1], cost_c, conc_c, steel_c, form_c, feas_c, "(b) column section", "column")]:
    idx = np.random.default_rng(0).choice(np.flatnonzero(mask.ravel()),
                                          size=2500, replace=False)
    for lab, es, col in ROUTES:
        co2 = EC*conc + es*steel + EF*form
        ax.plot(cost.ravel()[idx], co2.ravel()[idx], ".", ms=1.2,
                color=col, alpha=0.05)
        fc_, fz = front(cost, co2, mask)
        ax.plot(fc_, fz, color=col, lw=1.8, label=lab)
        ax.plot(fc_[0], fz[0], "o", ms=4.5, mfc="white", mec=col, mew=1.2)
        ax.plot(fc_[-1], fz[-1], "*", ms=8, mfc=col, mec="k", mew=0.5)
        if es == 2.82:
            k = min(12, len(fc_)-1)
            sl = ((fz[0]-fz[k])/fz[0]) / ((fc_[k]-fc_[0])/fc_[0] + 1e-12)
            slopes[nm] = sl
    ax.set_xlabel("cost (\u20ac/m)"); ax.set_ylabel("embodied CO$_2$ (kg/m)")
    ax.set_title(tt + " \u2014 cost\u2013CO$_2$ Pareto fronts by steel route", fontsize=9.2)
    ax.grid(alpha=0.2, lw=0.4)
axes[0].legend(fontsize=6.6, frameon=False, title="rebar route (kg CO$_2$/kg)",
               title_fontsize=6.8)
axes[1].text(0.03, 0.05, "\u2605 CO$_2$-optimum   \u25cb cost-optimum",
             transform=axes[1].transAxes, fontsize=7)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_val_pareto.png", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("S2 pareto: %CO2 saved per %cost near cost-opt @BEDEC:",
      {k: round(v,2) for k,v in slopes.items()})

# ============================== S3: regime map ==============================
rr = np.linspace(0.001, 0.032, 260)
def hstar(conc, steel, form, mask, Hg, kform):
    out = np.empty_like(rr)
    for k, r in enumerate(rr):
        Z = np.where(mask, conc + r*steel + kform*form, np.inf)
        out[k] = Hg.ravel()[np.argmin(Z)]
    return out
KM, KE = CF/CC, EF/EC
fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.6))
for ax, conc, steel, form, mask, Hg, tt in [
        (axes[0], conc_b, steel_b, form_b, feas_b, H, "(a) beam"),
        (axes[1], conc_c, steel_c, form_c, feas_c, Hc, "(b) column")]:
    hm = hstar(conc, steel, form, mask, Hg, KM)   # cost path vs r_c
    he = hstar(conc, steel, form, mask, Hg, KE)   # carbon path vs r_e
    DH = np.abs(hm[None, :] - he[:, None])        # rows r_e, cols r_c
    pm = ax.pcolormesh(rr*1e3, rr*1e3, DH, cmap="magma_r", shading="auto")
    cb = plt.colorbar(pm, ax=ax, shrink=0.92, pad=0.02)
    cb.set_label("|$h^*_{cost} - h^*_{CO_2}$| (mm)", fontsize=7.5)
    cb.ax.tick_params(labelsize=7)
    ax.plot(rr*1e3, rr*1e3, color="w", lw=1.2, ls="--")
    ax.text(24, 21.2, "coincidence locus $r_e = r_c$", fontsize=6.6, color="w",
            rotation=38, ha="center")
    rc0 = CS/CC*1e3
    for es, lab, mk in [(2.82, "BEDEC", "o"), (1.85, "world avg", "s"),
                        (0.67, "EAF", "D"), (0.36, "green", "^")]:
        ax.plot(rc0, es/EC*1e3, mk, ms=6, mfc="white", mec="k")
        ax.text(rc0+0.7, es/EC*1e3, lab, fontsize=6.2, va="center")
    ax.set_xlabel("price ratio  $r_c = c_s/c_c$  (10$^{-3}$ m$^3$/kg)")
    ax.set_ylabel("emission ratio  $r_e = e_s/e_c$  (10$^{-3}$ m$^3$/kg)")
    ax.set_title(tt + " \u2014 design divergence across ratio space", fontsize=9.2)
fig.tight_layout()
fig.savefig(f"{OUT}/fig_val_regime.png", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("S3 regime map done")

# ============================== S4: utilization audit =======================
def beam_utils(h, As):
    dd = h-60.0
    _, pm, et, _ = E._rc_flex_doubly(250.0, dd, 60.0, As, 226.0, fc, fy)
    vc = 0.17*np.sqrt(fc)*250*dd
    pv = 0.75*(vc + 0.66*np.sqrt(fc)*250*dd)
    return [("flexure", Mu/pm), ("shear", Vu/pv), ("ductility", 0.004/et),
            ("\u03c1 \u2265 \u03c1min", rmin/(As/(250*dd))), ("h \u2264 3b", h/750.0)]
def col_utils(h, As):
    ee = max(Mu_c/Pu, 15.0+0.03*h)
    pp = E._rc_phiPn_at_e(300.0, h, As/2, As/2, fc, fy, ee)
    r = As/(300*h)
    return [("P\u2013M interaction", Pu/pp), ("\u03c1 \u2265 1%", 0.01/r),
            ("\u03c1 \u2264 4%", r/0.04), ("slenderness", (3000.0/(0.3*h))/22.0)]
fig, axes = plt.subplots(1, 2, figsize=(9.8, 3.4), sharex=True)
cols3 = {"cost": "k", "co2_bedec": AMBER, "co2_green": GREEN}
labs3 = {"cost": "cost-opt", "co2_bedec": "CO$_2$-opt (BEDEC)",
         "co2_green": "CO$_2$-opt (green)"}
for ax, tt, ufun, tkey in [(axes[0], "(a) beam optima", beam_utils, "beam"),
                            (axes[1], "(b) column optima", col_utils, "column")]:
    names = [n for n, _ in ufun(T[tkey]["cost"]["h"], T[tkey]["cost"]["As"])]
    y = np.arange(len(names))[::-1]
    for k, (dk, dv) in enumerate(T[tkey].items()):
        u = [x*100 for _, x in ufun(dv["h"], dv["As"])]
        ax.barh(y + (1-k)*0.26, u, 0.24, color=cols3[dk], alpha=0.88,
                label=labs3[dk] if tkey == "beam" else None)
    ax.axvline(100, color=RED, lw=1.3, ls="--")
    ax.text(100, len(names)-0.35, " limit", color=RED, fontsize=6.8)
    ax.set_yticks(y); ax.set_yticklabels(names, fontsize=7.6)
    ax.set_xlabel("utilization, demand/capacity (%)"); ax.set_xlim(0, 118)
    ax.set_title(tt, fontsize=9.2); ax.grid(alpha=0.2, lw=0.4, axis="x")
axes[0].legend(fontsize=6.8, frameon=False, loc="lower right")
fig.tight_layout()
fig.savefig(f"{OUT}/fig_val_util.png", dpi=300, bbox_inches="tight", facecolor="white")
plt.close(fig)
print("S4 utilization audit done")
