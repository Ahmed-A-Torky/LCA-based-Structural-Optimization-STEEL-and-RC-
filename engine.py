# -*- coding: utf-8 -*-
"""
engine.py
=========

Unified structural-optimization engine for the eight Sedaghati (2005)
benchmark problems, built for the Flask GUI.

This module re-implements the verified mechanics from the standalone
scripts as a clean, dependency-light library:

  * a 2D/3D direct-stiffness TRUSS solver (static + modal),
  * a 2D frame (Euler-Bernoulli beam-column) solver (static + modal),
  * the AISC pipe-compression model for the 25-bar truss,
  * the Eq.(37)/Eq.(38) section relations for the frames,
  * a self-contained real-coded genetic algorithm with a progress
    callback so the web layer can stream live progress.

Only numpy and scipy are required (no OpenSeesPy / geneticalgorithm),
which keeps the server light and fully under our control.

Every problem is exposed through a `Problem` object with a common API:
    p.n_vars, p.bounds, p.evaluate(x) -> dict, p.model_3d(x) -> dict
so the GA and the front-end treat all eight uniformly.
"""

__version__ = "2.0.0"

import numpy as np
from scipy.linalg import eigh

# -----------------------------------------------------------------------------
# Units (consistent mm, N, MPa, kg)
# -----------------------------------------------------------------------------
mm = 1.0
N = 1.0
MPa = 1.0
GPa = 1000.0 * MPa
inch = 25.4 * mm
m = 1000.0 * mm
kN = 1000.0 * N
kip = 4448.222 * N
lbf = 4.4482 * N
lbm = 0.45359237
ton = 1000.0 * lbm  # metric-ton-force placeholder used only for 10-bar loads

PENALTY = 1.0e10


# =============================================================================
# Cached truss geometry (geometry is constant during optimization; only the
# areas change, so we precompute element direction cosines, dof maps and the
# free-dof list once per problem instance and reuse them every evaluation).
# =============================================================================
def precompute_truss(nodes, elements, fixed, ndm):
    nlist = sorted(nodes)
    nidx = {n: k for k, n in enumerate(nlist)}
    ndof = ndm * len(nlist)
    elems = []
    for (eid, i, j, gi) in elements:
        ci = np.asarray(nodes[i], float); cj = np.asarray(nodes[j], float)
        d = cj - ci
        L = float(np.linalg.norm(d))
        cs = d / L
        T = np.concatenate([cs, -cs])
        dofs = [ndm * nidx[i] + k for k in range(ndm)] + \
               [ndm * nidx[j] + k for k in range(ndm)]
        elems.append((eid, gi, L, cs, T, np.array(dofs)))
    constrained = set()
    for nid in fixed:
        base = ndm * nidx[nid]
        for k in range(ndm):
            constrained.add(base + k)
    free = np.array([d for d in range(ndof) if d not in constrained])
    return {"nlist": nlist, "nidx": nidx, "ndof": ndof, "ndm": ndm,
            "elems": elems, "free": free}


def truss_static_cached(cache, areas, E, load_cases):
    """Solve one or more load cases on a truss using cached geometry.

    load_cases: list of {nid:(Fx,Fy[,Fz])}.
    Returns (ok, results) where results is a list of (disp, force) per case.
    K is assembled and factorized once; every load case is solved against it.
    """
    ndm = cache["ndm"]; ndof = cache["ndof"]; nidx = cache["nidx"]
    free = cache["free"]; nlist = cache["nlist"]
    K = np.zeros((ndof, ndof))
    for (eid, gi, L, cs, T, dofs) in cache["elems"]:
        kfac = E * float(areas[gi]) / L
        ke = kfac * np.outer(T, T)
        K[np.ix_(dofs, dofs)] += ke
    Kff = K[np.ix_(free, free)]
    # Build all RHS vectors, solve together.
    nrhs = len(load_cases)
    Ff = np.zeros((len(free), nrhs))
    free_pos = {d: p for p, d in enumerate(free)}
    for c, loads in enumerate(load_cases):
        for nid, vec in loads.items():
            base = ndm * nidx[nid]
            for k in range(ndm):
                d = base + k
                if d in free_pos:
                    Ff[free_pos[d], c] += vec[k]
    try:
        Uf = np.linalg.solve(Kff, Ff)
    except np.linalg.LinAlgError:
        return False, []
    results = []
    for c in range(nrhs):
        U = np.zeros(ndof); U[free] = Uf[:, c]
        disp = {}
        for nid in nlist:
            base = ndm * nidx[nid]
            disp[nid] = tuple(U[base + k] for k in range(ndm))
        force = {}
        for (eid, gi, L, cs, T, dofs) in cache["elems"]:
            uvec = U[dofs]
            # elongation = (u_j - u_i) . cs ; T = [cs, -cs] so -(uvec.T) gives it
            elong = -float(np.dot(uvec, T))
            force[eid] = E * float(areas[gi]) * elong / L
        results.append((disp, force))
    return True, results


# =============================================================================
# Low-level solvers
# =============================================================================
def truss_static(nodes, elements, areas, E, fixed, loads, ndm):
    """Linear static analysis of a pin-jointed truss.

    nodes:    {nid: (x,y[,z])}
    elements: list of (eid, i, j, area_index)
    areas:    array of areas indexed by area_index
    fixed:    set of nids fully pinned
    loads:    {nid: (Fx,Fy[,Fz])}
    Returns (ok, disp {nid:vec}, force {eid: axial N})
    """
    nlist = sorted(nodes)
    nidx = {n: k for k, n in enumerate(nlist)}
    ndof = ndm * len(nlist)
    K = np.zeros((ndof, ndof))
    for (eid, i, j, gi) in elements:
        A = float(areas[gi])
        ci = nodes[i]; cj = nodes[j]
        d = np.array(cj) - np.array(ci)
        L = float(np.linalg.norm(d))
        cs = d / L
        T = np.concatenate([cs, -cs])
        ke = (E * A / L) * np.outer(T, T)
        dofs = []
        for nd in (i, j):
            base = ndm * nidx[nd]
            dofs += [base + k for k in range(ndm)]
        for a, A_ in enumerate(dofs):
            for b, B_ in enumerate(dofs):
                K[A_, B_] += ke[a, b]
    F = np.zeros(ndof)
    for nid, vec in loads.items():
        base = ndm * nidx[nid]
        for k in range(ndm):
            F[base + k] += vec[k]
    constrained = set()
    for nid in fixed:
        base = ndm * nidx[nid]
        for k in range(ndm):
            constrained.add(base + k)
    free = [d for d in range(ndof) if d not in constrained]
    try:
        uf = np.linalg.solve(K[np.ix_(free, free)], F[free])
    except np.linalg.LinAlgError:
        return False, {}, {}
    U = np.zeros(ndof); U[free] = uf
    disp = {}
    for nid in nlist:
        base = ndm * nidx[nid]
        disp[nid] = tuple(U[base + k] for k in range(ndm))
    force = {}
    for (eid, i, j, gi) in elements:
        A = float(areas[gi])
        ci = nodes[i]; cj = nodes[j]
        d = np.array(cj) - np.array(ci)
        L = float(np.linalg.norm(d))
        cs = d / L
        du = np.array(disp[j]) - np.array(disp[i])
        elong = float(np.dot(du, cs))
        force[eid] = E * A * elong / L      # +tension
    return True, disp, force


def truss_modal(nodes, elements, areas, E, rho, fixed, lumped, ndm,
                nmodes, unit_corr=1000.0):
    """Modal analysis of a truss with consistent structural mass + lumped mass.

    lumped: {nid: mass_kg} applied to every translational DOF of that node.
    Returns (ok, freqs_Hz list).
    """
    nlist = sorted(nodes)
    nidx = {n: k for k, n in enumerate(nlist)}
    ndof = ndm * len(nlist)
    K = np.zeros((ndof, ndof))
    M = np.zeros((ndof, ndof))
    for (eid, i, j, gi) in elements:
        A = float(areas[gi])
        ci = nodes[i]; cj = nodes[j]
        d = np.array(cj) - np.array(ci)
        L = float(np.linalg.norm(d))
        cs = d / L
        T = np.concatenate([cs, -cs])
        ke = (E * A / L) * np.outer(T, T)
        # consistent mass for a uniform bar (axial + transverse), m=rho*A*L
        mtot = rho * A * L
        Mloc = np.zeros((2 * ndm, 2 * ndm))
        # 2-node bar consistent mass in any dimension:
        # [[2I, I],[I, 2I]] * m/6  where I is ndm x ndm identity
        I_ = np.eye(ndm)
        Mloc[:ndm, :ndm] = 2 * I_
        Mloc[:ndm, ndm:] = I_
        Mloc[ndm:, :ndm] = I_
        Mloc[ndm:, ndm:] = 2 * I_
        Mloc *= mtot / 6.0
        dofs = []
        for nd in (i, j):
            base = ndm * nidx[nd]
            dofs += [base + k for k in range(ndm)]
        for a, A_ in enumerate(dofs):
            for b, B_ in enumerate(dofs):
                K[A_, B_] += ke[a, b]
                M[A_, B_] += Mloc[a, b]
    for nid, mval in lumped.items():
        base = ndm * nidx[nid]
        for k in range(ndm):
            M[base + k, base + k] += mval
    constrained = set()
    for nid in fixed:
        base = ndm * nidx[nid]
        for k in range(ndm):
            constrained.add(base + k)
    free = [d for d in range(ndof) if d not in constrained]
    Kff = K[np.ix_(free, free)]
    Mff = M[np.ix_(free, free)]
    try:
        lams = eigh(Kff, Mff, eigvals_only=True)
    except Exception:
        return False, []
    lams = np.sort(lams)
    freqs = []
    for lam in lams[:nmodes]:
        if lam < 0:
            return False, []
        omega = np.sqrt(lam * unit_corr)
        freqs.append(omega / (2.0 * np.pi))
    return True, freqs


def _frame_element_matrices(ci, cj, A, E, I, rho_L):
    """Return (Kglob 6x6, Mglob 6x6, T, L, c, s) for a 2D beam-column."""
    dx = cj[0] - ci[0]; dy = cj[1] - ci[1]
    L = float(np.hypot(dx, dy))
    c = dx / L; s = dy / L
    EA_L = E * A / L
    EI = E * I
    kloc = np.array([
        [ EA_L, 0, 0, -EA_L, 0, 0],
        [0, 12*EI/L**3, 6*EI/L**2, 0, -12*EI/L**3, 6*EI/L**2],
        [0, 6*EI/L**2, 4*EI/L, 0, -6*EI/L**2, 2*EI/L],
        [-EA_L, 0, 0, EA_L, 0, 0],
        [0, -12*EI/L**3, -6*EI/L**2, 0, 12*EI/L**3, -6*EI/L**2],
        [0, 6*EI/L**2, 2*EI/L, 0, -6*EI/L**2, 4*EI/L],
    ])
    T = np.array([
        [ c, s, 0, 0, 0, 0],
        [-s, c, 0, 0, 0, 0],
        [ 0, 0, 1, 0, 0, 0],
        [ 0, 0, 0, c, s, 0],
        [ 0, 0, 0,-s, c, 0],
        [ 0, 0, 0, 0, 0, 1],
    ])
    kg = T.T @ kloc @ T
    # consistent mass matrix (translation + rotation), rho_L = mass/length
    ml = rho_L * L
    mloc = ml * np.array([
        [1/3, 0, 0, 1/6, 0, 0],
        [0, 13/35, 11*L/210, 0, 9/70, -13*L/420],
        [0, 11*L/210, L*L/105, 0, 13*L/420, -L*L/140],
        [1/6, 0, 0, 1/3, 0, 0],
        [0, 9/70, 13*L/420, 0, 13/35, -11*L/210],
        [0, -13*L/420, -L*L/140, 0, -11*L/210, L*L/105],
    ])
    mg = T.T @ mloc @ T
    return kg, mg, T, kloc, L, c, s


def frame_static(nodes, elements, areas, E, sect_I, fixed, loads):
    """2D frame static analysis.

    elements: list of (eid, i, j, gi, role)
    sect_I:   callable area->I (mm^4)
    Returns (ok, disp {nid:(ux,uy,rz)}, endforces {eid:(Ni,Mi,Nj,Mj)}).
    """
    nlist = sorted(nodes)
    nidx = {n: k for k, n in enumerate(nlist)}
    ndof = 3 * len(nlist)
    K = np.zeros((ndof, ndof))
    cache = {}
    for (eid, i, j, gi, role) in elements:
        A = float(areas[gi]); I = sect_I(A)
        kg, mg, T, kloc, L, c, s = _frame_element_matrices(nodes[i], nodes[j], A, E, I, 0.0)
        cache[eid] = (T, kloc, L, i, j)
        dofs = [3*nidx[i], 3*nidx[i]+1, 3*nidx[i]+2,
                3*nidx[j], 3*nidx[j]+1, 3*nidx[j]+2]
        for a, A_ in enumerate(dofs):
            for b, B_ in enumerate(dofs):
                K[A_, B_] += kg[a, b]
    F = np.zeros(ndof)
    for nid, vec in loads.items():
        base = 3 * nidx[nid]
        for k in range(3):
            F[base + k] += vec[k]
    constrained = set()
    for nid in fixed:
        base = 3 * nidx[nid]
        for k in range(3):
            constrained.add(base + k)
    free = [d for d in range(ndof) if d not in constrained]
    try:
        uf = np.linalg.solve(K[np.ix_(free, free)], F[free])
    except np.linalg.LinAlgError:
        return False, {}, {}
    U = np.zeros(ndof); U[free] = uf
    disp = {}
    for nid in nlist:
        base = 3 * nidx[nid]
        disp[nid] = (U[base], U[base+1], U[base+2])
    endf = {}
    for (eid, i, j, gi, role) in elements:
        T, kloc, L, ii, jj = cache[eid]
        dg = np.array([*disp[ii], *disp[jj]])
        dl = T @ dg
        fl = kloc @ dl   # [Ni,Vi,Mi,Nj,Vj,Mj] local
        endf[eid] = (fl[0], fl[2], fl[3], fl[5])
    return True, disp, endf


def frame_modal(nodes, elements, areas, E, rho, sect_I, fixed,
                dist_mass_elems, dist_mass_per_mm, nmodes, unit_corr=1000.0):
    """2D frame modal analysis with consistent mass + distributed nonstructural mass."""
    nlist = sorted(nodes)
    nidx = {n: k for k, n in enumerate(nlist)}
    ndof = 3 * len(nlist)
    K = np.zeros((ndof, ndof))
    M = np.zeros((ndof, ndof))
    for (eid, i, j, gi, role) in elements:
        A = float(areas[gi]); I = sect_I(A)
        rho_L = rho * A
        if eid in dist_mass_elems:
            rho_L += dist_mass_per_mm
        kg, mg, T, kloc, L, c, s = _frame_element_matrices(nodes[i], nodes[j], A, E, I, rho_L)
        dofs = [3*nidx[i], 3*nidx[i]+1, 3*nidx[i]+2,
                3*nidx[j], 3*nidx[j]+1, 3*nidx[j]+2]
        for a, A_ in enumerate(dofs):
            for b, B_ in enumerate(dofs):
                K[A_, B_] += kg[a, b]
                M[A_, B_] += mg[a, b]
    constrained = set()
    for nid in fixed:
        base = 3 * nidx[nid]
        for k in range(3):
            constrained.add(base + k)
    free = [d for d in range(ndof) if d not in constrained]
    try:
        lams = eigh(K[np.ix_(free, free)], M[np.ix_(free, free)], eigvals_only=True)
    except Exception:
        return False, []
    lams = np.sort(lams)
    omegas = []
    for lam in lams[:nmodes]:
        if lam < 0:
            return False, []
        omegas.append(np.sqrt(lam * unit_corr))   # rad/s
    return True, omegas


# =============================================================================
# Section relations
# =============================================================================
def sect_props_eq37(A_mm2):
    """Return (I_mm4, S_mm3) per Sedaghati Eq.(37)."""
    A = A_mm2 / (inch**2)
    if A <= 15.0:
        S = 1.6634 * A**1.511
        I = 4.592 * A**2
    elif A <= 44.0:
        S = np.sqrt(281.077 * A**2 + 84100.0) - 290.0
        I = 4.638 * A**2
    else:
        S = 13.761 * A - 103.906
        I = 256.229 * A - 2300.0
    return I * inch**4, S * inch**3


def sect_I_eq37(A_mm2):
    return sect_props_eq37(A_mm2)[0]


def sect_I_eq38(A_mm2):
    A = A_mm2 / (inch**2)
    I = 4.6248 * A**2 if A <= 44.0 else 256.0 * A - 2300.0
    return I * inch**4


# =============================================================================
# Problem base
# =============================================================================
class Problem:
    key = ""
    name = ""
    family = "static"   # or "frequency"
    kind = "truss"      # or "frame"
    ndm = 2
    def __init__(self):
        self.n_vars = 0
        self.bounds = (0.0, 1.0)
        self.ref_mass = None
        self.group_labels = []
    def evaluate(self, x):
        """Return dict with keys: mass, feasible, n_viol, penalty_obj, details..."""
        raise NotImplementedError
    material = "steel"            # "steel" | "aluminium" | "rebar" (RC problems)
    _route = None
    @property
    def steel_route(self):
        return self._route or MATERIAL_DEFAULT[self.material]
    @steel_route.setter
    def steel_route(self, v):
        self._route = v
    @property
    def steel_co2(self):
        return routes_for(self.material)[self.steel_route]["co2"]
    def set_steel_route(self, route):
        if route in routes_for(self.material):
            self._route = route
    def _mass_by_role(self, ev, x):
        """Member masses grouped by structural role from geometry + areas."""
        bars = ev.get("bars") or []
        if not bars or not hasattr(self, "nodes"):
            return {"members": float(ev["mass"])}
        out = {}
        for el, bar in zip(self.elements, bars):
            i, j = el[1], el[2]
            role = (el[4] if len(el) > 4 else "members").split("-")[0]
            L = float(np.linalg.norm(np.asarray(self.nodes[j], float) -
                                     np.asarray(self.nodes[i], float)))
            out[role] = out.get(role, 0.0) + bar["area"]*L*getattr(self, "rho", 7850e-9)
        tot = sum(out.values()) or 1.0
        return {k: float(v*ev["mass"]/tot) for k, v in out.items()}
    def carbon_report(self, ev, x):
        """Attach an embodied-carbon total and breakdown to every evaluation."""
        if not ev.get("ok"):
            return ev
        if "breakdown" in ev:                      # RC: objective already CO2
            bd = dict(ev["breakdown"])
            ev["carbon"] = {"total": float(ev["mass"]), "breakdown": bd,
                            "material": "rebar", "route": self.steel_route,
                            "factor": float(self.steel_co2), "unit": "kg CO2"}
            return ev
        f = float(self.steel_co2)
        parts = self._mass_by_role(ev, x)
        bd = {k: float(v*f) for k, v in parts.items()}
        ev["carbon"] = {"total": float(sum(bd.values())), "breakdown": bd,
                        "material": self.material, "route": self.steel_route,
                        "factor": f, "unit": "kg CO2",
                        "mass_breakdown_kg": {k: float(v) for k, v in parts.items()}}
        return ev
    def evaluate_full(self, x):
        return self.carbon_report(self.evaluate(x), x)
    def objective(self, x):
        r = self.evaluate(x)
        if not r["ok"]:
            return PENALTY
        if r["n_viol"] > 0:
            if "freq_err" in r:
                # frequency problems: rank infeasible designs by how close the
                # frequency is to its target, so the search homes in on the
                # target rather than on a violation count
                return PENALTY + 1.0e6 * r["freq_err"] + r["mass"]
            return PENALTY + 1.0e4 * r["n_viol"] + r["mass"]
        return r["mass"]
    def model_3d(self, x):
        raise NotImplementedError


# -----------------------------------------------------------------------------
# helper to build mass for trusses
# -----------------------------------------------------------------------------
def _truss_mass(elements, lengths, areas, rho):
    tot = 0.0
    for (eid, i, j, gi) in elements:
        tot += rho * lengths[eid] * float(areas[gi])
    return tot


# =============================================================================
# P1: 10-bar planar truss (static)
# =============================================================================
class TenBar(Problem):
    material = "aluminium"
    key = "10bar"; name = "10-Bar Planar Truss"
    family = "static"; kind = "truss"; ndm = 2
    def __init__(self):
        super().__init__()
        BAY = 9.144 * m
        self.nodes = {1:(0,0),2:(0,BAY),3:(BAY,0),4:(BAY,BAY),5:(2*BAY,0),6:(2*BAY,BAY)}
        el = {1:(1,3),2:(3,5),3:(5,6),4:(6,4),5:(4,2),6:(3,4),7:(1,4),8:(2,3),9:(3,6),10:(5,4)}
        self.elements = [(e, i, j, e-1) for e,(i,j) in el.items()]
        self.fixed = {1, 2}
        self.E = 68.94757 * GPa
        self.rho = 2767.99e-9
        self.SIGMA = 172.37 * MPa
        self.DISP = 50.8 * mm
        self.loads = {3:(0,-444822.0), 5:(0,-444822.0)}   # 100 kip down each
        self.lengths = {e:self._len(i,j) for (e,i,j,_) in self.elements}
        self.n_vars = 10
        self.bounds = (64.52, 22580.0)
        self.ref_mass = 2299.65
        self.group_labels = [f"Bar {k}" for k in range(1, 11)]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def evaluate(self, x):
        areas = np.asarray(x, float)
        ok, disp, force = truss_static(self.nodes, self.elements, areas, self.E,
                                       self.fixed, self.loads, 2)
        mass = _truss_mass(self.elements, self.lengths, areas, self.rho)
        if not ok:
            return {"ok": False, "mass": mass, "n_viol": 99}
        nv = 0; bars = []
        for (e,i,j,gi) in self.elements:
            sig = force[e]/areas[gi]
            viol = abs(sig) > self.SIGMA
            if viol: nv += 1
            bars.append({"id":e,"area":float(areas[gi]),"sigma":float(sig),
                         "limit":self.SIGMA,"viol":bool(viol)})
        maxd = max(np.hypot(disp[n][0],disp[n][1]) for n in self.nodes)
        if maxd > self.DISP: nv += 1
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"max_disp":float(maxd),"disp_limit":self.DISP,
                "stress_limit":self.SIGMA}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        ok, disp, force = truss_static(self.nodes, self.elements, areas, self.E,
                                       self.fixed, self.loads, 2)
        return _truss_model_payload(self, areas, force if ok else None, ndm=2)


# =============================================================================
# P2: 25-bar space truss (static, AISC compression)
# =============================================================================
class TwentyFiveBar(Problem):
    key = "25bar"; name = "25-Bar Space Truss"
    family = "static"; kind = "truss"; ndm = 3
    def __init__(self):
        super().__init__()
        self.nodes = {
            1:(-37.5*inch,0,200*inch),2:(37.5*inch,0,200*inch),
            3:(-37.5*inch,37.5*inch,100*inch),4:(37.5*inch,37.5*inch,100*inch),
            5:(37.5*inch,-37.5*inch,100*inch),6:(-37.5*inch,-37.5*inch,100*inch),
            7:(-100*inch,100*inch,0),8:(100*inch,100*inch,0),
            9:(100*inch,-100*inch,0),10:(-100*inch,-100*inch,0)}
        eld = {1:(1,2,0),2:(1,4,1),3:(2,3,1),4:(1,5,1),5:(2,6,1),
               6:(2,5,2),7:(2,4,2),8:(1,3,2),9:(1,6,2),10:(3,6,3),11:(4,5,3),
               12:(3,4,4),13:(5,6,4),14:(3,10,5),15:(6,7,5),16:(4,9,5),17:(5,8,5),
               18:(3,8,6),19:(4,7,6),20:(6,9,6),21:(5,10,6),
               22:(3,7,7),23:(4,8,7),24:(5,9,7),25:(6,10,7)}
        self.elements = [(e,i,j,g) for e,(i,j,g) in eld.items()]
        self.fixed = {7,8,9,10}
        self.E = 207.0*GPa; self.rho = 7830e-9
        self.SIGMA_T = 240.0*MPa
        self.DISP = 10.0*mm
        self.loads = {1:(1000*lbf,10000*lbf,-5000*lbf),
                      2:(0,10000*lbf,-5000*lbf),
                      3:(500*lbf,0,0),6:(500*lbf,0,0)}
        self.lengths = {e:self._len(i,j) for (e,i,j,_) in self.elements}
        self.n_vars = 8
        self.bounds = (200.0, 5000.0)
        self.ref_mass = 649.7
        self.group_labels = ["A1 top chord","A2 long diag","A3 short diag",
                             "A4 mid long","A5 mid short","A6 base vert",
                             "A7 base diag","A8 base long"]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def _aisc(self, L, A):
        A_cm2 = A/100.0
        rG = 0.4993*A_cm2**0.6777*10.0
        SR = L/rG
        Cc = np.sqrt(2*np.pi**2*self.E/self.SIGMA_T)
        if SR > Cc: return np.pi**2*self.E/SR**2
        return self.SIGMA_T*(1-0.5*SR**2/Cc**2)
    def evaluate(self, x):
        areas = np.asarray(x, float)
        ok, disp, force = truss_static(self.nodes, self.elements, areas, self.E,
                                       self.fixed, self.loads, 3)
        mass = _truss_mass(self.elements, self.lengths, areas, self.rho)
        if not ok:
            return {"ok": False, "mass": mass, "n_viol": 99}
        nv = 0; bars = []
        for (e,i,j,gi) in self.elements:
            A = areas[gi]; F = force[e]; sig = F/A
            if F >= 0:
                lim = self.SIGMA_T; viol = sig > lim
            else:
                lim = self._aisc(self.lengths[e], A); viol = abs(sig) > lim
            if viol: nv += 1
            bars.append({"id":e,"group":gi+1,"area":float(A),"sigma":float(sig),
                         "limit":float(lim if F<0 else self.SIGMA_T),"viol":bool(viol)})
        for nid in (1,2):
            for comp in (0,1):
                if abs(disp[nid][comp]) > self.DISP: nv += 1
        maxd = max(max(abs(disp[n][0]),abs(disp[n][1])) for n in (1,2))
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"max_disp":float(maxd),"disp_limit":self.DISP}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        ok, disp, force = truss_static(self.nodes, self.elements, areas, self.E,
                                       self.fixed, self.loads, 3)
        return _truss_model_payload(self, areas, force if ok else None, ndm=3)


# =============================================================================
# P3: 72-bar space truss (static, 2 load cases)
# =============================================================================
def _build_72():
    HALF = 60.0*inch
    Z = [0,60*inch,120*inch,180*inch,240*inch]
    CXY = [(HALF,HALF),(-HALF,HALF),(-HALF,-HALF),(HALF,-HALF)]
    nodes = {}
    for lvl in range(5):
        for c in range(4):
            nid = 4*lvl+c+1
            nodes[nid] = (CXY[c][0], CXY[c][1], Z[lvl])
    elements = []; eid = 1
    for story in range(4):
        b = [4*story+1,4*story+2,4*story+3,4*story+4]
        t = [4*(story+1)+1,4*(story+1)+2,4*(story+1)+3,4*(story+1)+4]
        g = 4*story+0
        for (i,j) in [(b[0],t[0]),(b[1],t[1]),(b[2],t[2]),(b[3],t[3])]:
            elements.append((eid,i,j,g)); eid+=1
        g = 4*story+1
        for (i,j) in [(b[0],t[1]),(b[1],t[0]),(b[1],t[2]),(b[2],t[1]),
                      (b[2],t[3]),(b[3],t[2]),(b[3],t[0]),(b[0],t[3])]:
            elements.append((eid,i,j,g)); eid+=1
        g = 4*story+2
        for (i,j) in [(t[0],t[1]),(t[1],t[2]),(t[2],t[3]),(t[3],t[0])]:
            elements.append((eid,i,j,g)); eid+=1
        g = 4*story+3
        for (i,j) in [(t[0],t[2]),(t[1],t[3])]:
            elements.append((eid,i,j,g)); eid+=1
    return nodes, elements


class SeventyTwoBar(Problem):
    material = "aluminium"
    key = "72bar"; name = "72-Bar Space Truss"
    family = "static"; kind = "truss"; ndm = 3
    def __init__(self):
        super().__init__()
        self.nodes, self.elements = _build_72()
        self.fixed = {1,2,3,4}
        self.top = (17,18,19,20)
        self.E = 68947.0*MPa; self.rho = 2770e-9
        self.SIGMA = 172.37*MPa; self.DISP = 6.35*mm
        L5 = 5000.0*lbf
        self.load_cases = [{17:(L5,L5,-L5)},
                           {17:(0,0,-L5),18:(0,0,-L5),19:(0,0,-L5),20:(0,0,-L5)}]
        self.lengths = {e:self._len(i,j) for (e,i,j,_) in self.elements}
        self._cache = precompute_truss(self.nodes, self.elements, self.fixed, 3)
        self.n_vars = 16
        self.bounds = (64.52, 6452.0)
        self.ref_mass = 172.20
        typ = ["cols","face diag","top edges","top X-diag"]
        self.group_labels = [f"S{g//4+1} {typ[g%4]}" for g in range(16)]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def evaluate(self, x):
        areas = np.asarray(x, float)
        mass = _truss_mass(self.elements, self.lengths, areas, self.rho)
        ok, results = truss_static_cached(self._cache, areas, self.E, self.load_cases)
        if not ok:
            return {"ok":False,"mass":mass,"n_viol":99}
        nv = 0; worst_bar = {}; maxd_all = 0.0
        for (disp, force) in results:
            for nid in self.top:
                for comp in (0,1):
                    if abs(disp[nid][comp]) > self.DISP: nv += 1
                maxd_all = max(maxd_all, abs(disp[nid][0]), abs(disp[nid][1]))
            for (e,i,j,gi) in self.elements:
                sig = force[e]/areas[gi]
                if abs(sig) > self.SIGMA: nv += 1
                if e not in worst_bar or abs(sig) > abs(worst_bar[e]):
                    worst_bar[e] = sig
        bars = []
        for (e,i,j,gi) in self.elements:
            sig = worst_bar[e]
            bars.append({"id":e,"group":gi+1,"area":float(areas[gi]),
                         "sigma":float(sig),"limit":self.SIGMA,
                         "viol":bool(abs(sig)>self.SIGMA)})
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"max_disp":float(maxd_all),"disp_limit":self.DISP,
                "stress_limit":self.SIGMA}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        ok, results = truss_static_cached(self._cache, areas, self.E, [self.load_cases[1]])
        force = results[0][1] if ok else None
        return _truss_model_payload(self, areas, force, ndm=3)


# =============================================================================
# Frame problems
# =============================================================================
class TenMemberFrame(Problem):
    key = "10frame"; name = "10-Member Frame"
    family = "static"; kind = "frame"; ndm = 2
    def __init__(self):
        super().__init__()
        L = 100.0*inch
        self.nodes = {1:(0,0),2:(L,0),3:(2*L,0),4:(0,L),5:(L,L),6:(2*L,L),
                      7:(0,2*L),8:(L,2*L),9:(2*L,2*L)}
        eld = {1:(1,4,"col"),2:(2,5,"col"),3:(3,6,"col"),4:(4,5,"beam"),
               5:(5,6,"beam"),6:(4,7,"col"),7:(5,8,"col"),8:(6,9,"col"),
               9:(7,8,"beam"),10:(8,9,"beam")}
        self.elements = [(e,i,j,e-1,r) for e,(i,j,r) in eld.items()]
        self.fixed = {1,2,3}
        self.E = 207.0*GPa; self.rho = 7830e-9
        self.SIGMA = 165.47*MPa; self.DISP = 0.254*mm
        sc = 0.06   # load scale chosen so the tight disp limit is reachable
        self.loads = {7:(150*kip*sc,-100*kip*sc,1500*kip*inch*sc),
                      8:(0,-200*kip*sc,0),9:(0,0,-1500*kip*inch*sc),
                      4:(100*kip*sc,0,1500*kip*inch*sc),6:(0,0,-3000*kip*inch*sc)}
        self.free = (4,5,6,7,8,9)
        self.lengths = {e:self._len(i,j) for (e,i,j,_,_) in self.elements}
        self.n_vars = 10
        self.bounds = (3225.80, 64516.0)
        self.ref_mass = 3307.23
        self.group_labels = [f"{r} {e}" for (e,i,j,g,r) in self.elements]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def evaluate(self, x):
        areas = np.asarray(x, float)
        ok, disp, ef = frame_static(self.nodes, self.elements, areas, self.E,
                                    sect_I_eq37, self.fixed, self.loads)
        mass = sum(self.rho*self.lengths[e]*areas[g] for (e,i,j,g,r) in self.elements)
        if not ok:
            return {"ok":False,"mass":mass,"n_viol":99}
        nv = 0; bars = []
        for (e,i,j,g,r) in self.elements:
            A = areas[g]; I,S = sect_props_eq37(A)
            Ni,Mi,Nj,Mj = ef[e]
            sig = max(abs(Ni)/A+abs(Mi)/S, abs(Nj)/A+abs(Mj)/S)
            viol = sig > self.SIGMA
            if viol: nv += 1
            bars.append({"id":e,"role":r,"area":float(A),"sigma":float(sig),
                         "limit":self.SIGMA,"viol":bool(viol)})
        maxd = max(abs(disp[n][0]) for n in self.free)
        if maxd > self.DISP: nv += 1
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"max_disp":float(maxd),"disp_limit":self.DISP,
                "stress_limit":self.SIGMA}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        return _frame_model_payload(self, areas, sect_I_eq37)


class TwentyFiveMemberFrame(Problem):
    key = "25frame"; name = "25-Member Frame"
    family = "static"; kind = "frame"; ndm = 2
    def __init__(self):
        super().__init__()
        L = 100.0*inch
        self.nodes = {}
        for lvl in range(4):
            for col in range(4):
                self.nodes[4*lvl+col+1] = (col*L, lvl*L)
        elements = []; eid = 1
        for story in range(3):
            for col in range(4):
                i=4*story+col+1; j=4*(story+1)+col+1
                elements.append((eid,i,j,eid-1,"col")); eid+=1
        for floor in range(1,4):
            for bay in range(3):
                i=4*floor+bay+1; j=4*floor+bay+2
                elements.append((eid,i,j,eid-1,"beam")); eid+=1
        for bay in (0,2):
            bl=4*2+bay+1; br=4*2+bay+2; tl=4*3+bay+1; tr=4*3+bay+2
            elements.append((eid,bl,tr,eid-1,"brace")); eid+=1
            elements.append((eid,br,tl,eid-1,"brace")); eid+=1
        self.elements = elements
        self.fixed = {1,2,3,4}
        self.free = tuple(n for n in self.nodes if n not in self.fixed)
        self.E = 207.0*GPa; self.rho = 7830e-9
        self.SIGMA = 165.47*MPa; self.DISP = 0.127*mm
        sc = 0.03
        self.loads = {14:(0,-500*kip*sc,0),15:(0,-500*kip*sc,0),
                      16:(0,-500*kip*sc,0),5:(100*kip*sc,0,0),9:(100*kip*sc,0,0),
                      13:(100*kip*sc,-500*kip*sc,0)}
        self.lengths = {e:self._len(i,j) for (e,i,j,_,_) in self.elements}
        self.n_vars = 25
        self.bounds = (3225.80, 64516.0)
        self.ref_mass = 9508.32
        self.group_labels = [f"{r} {e}" for (e,i,j,g,r) in self.elements]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def evaluate(self, x):
        areas = np.asarray(x, float)
        ok, disp, ef = frame_static(self.nodes, self.elements, areas, self.E,
                                    sect_I_eq37, self.fixed, self.loads)
        mass = sum(self.rho*self.lengths[e]*areas[g] for (e,i,j,g,r) in self.elements)
        if not ok:
            return {"ok":False,"mass":mass,"n_viol":99}
        nv = 0; bars = []
        for (e,i,j,g,r) in self.elements:
            A = areas[g]; I,S = sect_props_eq37(A)
            Ni,Mi,Nj,Mj = ef[e]
            sig = max(abs(Ni)/A+abs(Mi)/S, abs(Nj)/A+abs(Mj)/S)
            viol = sig > self.SIGMA
            if viol: nv += 1
            bars.append({"id":e,"role":r,"area":float(A),"sigma":float(sig),
                         "limit":self.SIGMA,"viol":bool(viol)})
        maxd = max(abs(disp[n][0]) for n in self.free)
        if maxd > self.DISP: nv += 1
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"max_disp":float(maxd),"disp_limit":self.DISP,
                "stress_limit":self.SIGMA}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        return _frame_model_payload(self, areas, sect_I_eq37)


# =============================================================================
# Frequency problems
# =============================================================================
class TenBarFreq(Problem):
    material = "aluminium"
    key = "10bar_freq"; name = "10-Bar Truss (Frequency)"
    family = "frequency"; kind = "truss"; ndm = 2
    def __init__(self):
        super().__init__()
        L = 360.0*inch
        self.nodes = {1:(0,0),2:(0,L),3:(L,0),4:(L,L),5:(2*L,0),6:(2*L,L)}
        eld = {1:(1,3),2:(3,5),3:(5,6),4:(6,4),5:(4,2),6:(3,4),7:(1,4),8:(2,3),9:(3,6),10:(5,4)}
        self.elements = [(e,i,j,e-1) for e,(i,j) in eld.items()]
        self.fixed = {1,2}
        self.mass_nodes = (3,4,5,6)
        self.lumped = 454.0
        self.E = 68947.0*MPa; self.rho = 2770e-9
        self.lengths = {e:self._len(i,j) for (e,i,j,_) in self.elements}
        self.n_vars = 10
        self.bounds = (64.52, 35.0*inch*inch)
        self.ref_mass = 2637.85
        self.targets = [(1,14.0,"==")]    # subcase A: f1 = 14 Hz
        self.eqtol = 0.01   # +/-1%: tight band on the equality target
        self.group_labels = [f"Bar {k}" for k in range(1,11)]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def _freqs(self, areas, nmodes):
        lump = {n:self.lumped for n in self.mass_nodes}
        return truss_modal(self.nodes, self.elements, areas, self.E, self.rho,
                           self.fixed, lump, 2, nmodes)
    def evaluate(self, x):
        areas = np.asarray(x, float)
        mass = _truss_mass(self.elements, self.lengths, areas, self.rho)
        nmodes = max(t[0] for t in self.targets)+1
        ok, freqs = self._freqs(areas, nmodes)
        if not ok:
            return {"ok":False,"mass":mass,"n_viol":99}
        nv, fr, ferr = _check_freq(self.targets, freqs, self.eqtol)
        bars = [{"id":e,"area":float(areas[gi])} for (e,i,j,gi) in self.elements]
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"freqs":[float(f) for f in freqs],
                "targets":fr,"freq_err":float(ferr),"unit":"Hz"}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        return _truss_model_payload(self, areas, None, ndm=2,
                                    mass_nodes=self.mass_nodes)


class SeventyTwoBarFreq(Problem):
    material = "aluminium"
    key = "72bar_freq"; name = "72-Bar Truss (Frequency)"
    family = "frequency"; kind = "truss"; ndm = 3
    def __init__(self):
        super().__init__()
        self.nodes, self.elements = _build_72()
        self.fixed = {1,2,3,4}
        self.mass_nodes = (17,18,19,20)
        self.lumped = 2270.0
        self.E = 68947.0*MPa; self.rho = 2770e-9
        self.lengths = {e:self._len(i,j) for (e,i,j,_) in self.elements}
        self.n_vars = 16
        self.bounds = (64.52, 5000.0)
        self.ref_mass = 287.09
        self.targets = [(1,4.0,"==")]
        self.eqtol = 0.02
        typ = ["cols","face diag","top edges","top X-diag"]
        self.group_labels = [f"S{g//4+1} {typ[g%4]}" for g in range(16)]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def evaluate(self, x):
        areas = np.asarray(x, float)
        mass = _truss_mass(self.elements, self.lengths, areas, self.rho)
        lump = {n:self.lumped for n in self.mass_nodes}
        nmodes = max(t[0] for t in self.targets)+2
        ok, freqs = truss_modal(self.nodes, self.elements, areas, self.E, self.rho,
                                self.fixed, lump, 3, nmodes)
        if not ok:
            return {"ok":False,"mass":mass,"n_viol":99}
        nv, fr, ferr = _check_freq(self.targets, freqs, self.eqtol)
        bars = [{"id":e,"group":gi+1,"area":float(areas[gi])} for (e,i,j,gi) in self.elements]
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"freqs":[float(f) for f in freqs],
                "targets":fr,"freq_err":float(ferr),"unit":"Hz"}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        return _truss_model_payload(self, areas, None, ndm=3,
                                    mass_nodes=self.mass_nodes)


class SixMemberFrameFreq(Problem):
    key = "6frame_freq"; name = "6-Member Frame (Frequency)"
    family = "frequency"; kind = "frame"; ndm = 2
    def __init__(self):
        super().__init__()
        BAY=360*inch; HB=180*inch; HT=120*inch
        self.nodes = {1:(0,0),2:(BAY,0),3:(0,HB),4:(BAY,HB),5:(0,HB+HT),6:(BAY,HB+HT)}
        eld = {1:(3,5,"col-top-L"),2:(4,6,"col-top-R"),3:(1,3,"col-bot-L"),
               4:(2,4,"col-bot-R"),5:(5,6,"beam-top"),6:(3,4,"beam-mid")}
        self.elements = [(e,i,j,e-1,r) for e,(i,j,r) in eld.items()]
        self.fixed = {1,2}
        self.dist_elems = {5,6}
        self.dist_per_mm = 178.74/1000.0
        self.E = 207.0*GPa; self.rho = 7830e-9
        self.lengths = {e:self._len(i,j) for (e,i,j,_,_) in self.elements}
        self.n_vars = 6
        self.bounds = (5108.8, 56955.0)
        self.ref_mass = 4272.32
        self.targets = [(1,78.5,"==")]   # rad/s
        self.eqtol = 0.03
        self.group_labels = [r for (e,i,j,g,r) in self.elements]
    def _len(self,i,j):
        a=np.array(self.nodes[i]);b=np.array(self.nodes[j]);return float(np.linalg.norm(b-a))
    def evaluate(self, x):
        areas = np.asarray(x, float)
        mass = sum(self.rho*self.lengths[e]*areas[g] for (e,i,j,g,r) in self.elements)
        nmodes = max(t[0] for t in self.targets)+2
        ok, omegas = frame_modal(self.nodes, self.elements, areas, self.E, self.rho,
                                 sect_I_eq38, self.fixed, self.dist_elems,
                                 self.dist_per_mm, nmodes)
        if not ok:
            return {"ok":False,"mass":mass,"n_viol":99}
        nv, fr, ferr = _check_freq(self.targets, omegas, self.eqtol)
        bars = [{"id":e,"role":r,"area":float(areas[g])} for (e,i,j,g,r) in self.elements]
        return {"ok":True,"mass":float(mass),"n_viol":nv,"feasible":nv==0,
                "bars":bars,"freqs":[float(w) for w in omegas],
                "targets":fr,"freq_err":float(ferr),"unit":"rad/s"}
    def model_3d(self, x):
        areas = np.asarray(x, float)
        return _frame_model_payload(self, areas, sect_I_eq38,
                                    dist_elems=self.dist_elems)


# =============================================================================
# Shared helpers
# =============================================================================
def _check_freq(targets, freqs, eqtol):
    """Check frequency targets.  Returns (n_violated, report, freq_err) where
    freq_err is the summed relative deviation beyond the tolerance band -- the
    quantity the optimizer drives to zero, keeping the frequency target (not
    just a violation count) at the centre of the search."""
    nv = 0; rep = []; err = 0.0
    for (mi, tgt, sense) in targets:
        if mi > len(freqs):
            nv += 1; err += 1.0
            rep.append({"mode":mi,"value":None,"target":tgt,"sense":sense,"ok":False})
            continue
        f = freqs[mi-1]; ok = True
        rel = (f - tgt) / tgt
        if sense == "==":
            ok = abs(rel) <= eqtol
            if not ok: err += abs(rel) - eqtol
        elif sense == ">=":
            ok = rel >= -eqtol
            if not ok: err += (-rel) - eqtol
        elif sense == "<=":
            ok = rel <= eqtol
            if not ok: err += rel - eqtol
        if not ok: nv += 1
        rep.append({"mode":mi,"value":float(f),"target":tgt,"sense":sense,"ok":bool(ok)})
    return nv, rep, err


def _truss_model_payload(prob, areas, force, ndm, mass_nodes=()):
    """Build a JSON-serializable 3D model description for the front-end."""
    amin, amax = prob.bounds
    # node coordinates -> 3D (pad z=0 for 2D)
    nodes = []
    for nid in sorted(prob.nodes):
        c = prob.nodes[nid]
        x,y,z = (c[0],c[1],0.0) if ndm==2 else (c[0],c[1],c[2])
        nodes.append({"id":nid,"x":x,"y":y,"z":z,
                      "fixed":nid in prob.fixed,
                      "mass":nid in mass_nodes})
    # radius for extrusion from area: r = sqrt(A/pi); normalize for display
    members = []
    for (e,i,j,gi) in prob.elements:
        A = float(areas[gi])
        r = float(np.sqrt(A/np.pi))
        stress = None
        if force is not None and e in force:
            stress = float(force[e]/A)
        members.append({"id":e,"i":i,"j":j,"group":gi+1,"area":A,"radius":r,
                        "stress":stress})
    return {"type":"truss","ndm":ndm,"nodes":nodes,"members":members,
            "amin":amin,"amax":amax}


def _frame_model_payload(prob, areas, sect_I, dist_elems=()):
    nodes = []
    for nid in sorted(prob.nodes):
        c = prob.nodes[nid]
        nodes.append({"id":nid,"x":c[0],"y":c[1],"z":0.0,
                      "fixed":nid in prob.fixed,"mass":False})
    members = []
    for (e,i,j,g,r) in prob.elements:
        A = float(areas[g])
        side = float(np.sqrt(A))   # square-section visual side
        members.append({"id":e,"i":i,"j":j,"role":r,"area":A,"radius":side/2.0,
                        "dist":e in dist_elems})
    return {"type":"frame","ndm":2,"nodes":nodes,"members":members,
            "amin":prob.bounds[0],"amax":prob.bounds[1]}


# =============================================================================
# Genetic algorithm with progress callback
# =============================================================================
def run_ga(problem, pop_size, n_gen, *, mutation=0.15, elite_frac=0.04,
           crossover=0.7, seed=None, progress=None, should_stop=None):
    """Real-coded GA. Calls progress(gen, best_obj, best_feasible, best_f1)
    each generation (best_f1 is None for non-frequency problems).

    Returns dict: best_x, best_obj, history (best objective per gen),
                  history_feasible, freq_history (best design's target-mode
                  frequency per gen, frequency problems only), evaluations.
    """
    rng = np.random.default_rng(seed)
    lo, hi = problem.bounds
    n = problem.n_vars
    span = (hi - lo)
    pop = rng.uniform(lo, hi, size=(pop_size, n))
    # seed a few helpful starting points to speed feasibility:
    #   - all-max (usually feasible, gives an upper bound on mass)
    #   - mid-bounds, and a couple of lighter biased-low designs
    pop[0] = np.full(n, hi)
    if pop_size > 1:
        pop[1] = np.full(n, (lo + hi) / 2)
    if pop_size > 2:
        pop[2] = np.full(n, lo + 0.3 * span)
    if pop_size > 3:
        pop[3] = np.full(n, lo + 0.15 * span)

    def obj(x):
        return problem.objective(x)

    fitness = np.array([obj(ind) for ind in pop])
    evals = pop_size
    n_elite = max(2, int(elite_frac * pop_size))

    history = []; hist_feas = []
    best_idx = int(np.argmin(fitness))
    best_x = pop[best_idx].copy(); best_obj = float(fitness[best_idx])

    # Frequency problems: track the best design's target-mode frequency every
    # generation so the convergence toward the target itself is visible.
    track_freq = bool(getattr(problem, "targets", None)) and hasattr(problem, "eqtol")
    freq_hist = []
    def _best_f1():
        ev = problem.evaluate(best_x)
        fr = ev.get("freqs")
        if not fr:
            return None
        mode = problem.targets[0][0]
        return float(fr[mode - 1]) if mode <= len(fr) else None

    stall = 0
    for gen in range(n_gen):
        if should_stop and should_stop():
            break
        order = np.argsort(fitness)
        pop = pop[order]; fitness = fitness[order]

        # Decaying mutation scale: broad early exploration, fine late tuning.
        # A short burst of widening on stalls keeps the search from freezing.
        frac = gen / max(1, n_gen - 1)
        sigma = (0.18 * (1.0 - frac) + 0.012) * span
        if stall > 12:
            sigma *= 2.5

        # Elitism: carry the best individuals plus the global best-so-far.
        new_pop = [pop[k].copy() for k in range(n_elite)]
        new_pop[0] = best_x.copy()

        while len(new_pop) < pop_size:
            a = pop[_tournament(rng, fitness)]
            b = pop[_tournament(rng, fitness)]
            if rng.random() < crossover:
                alpha = rng.uniform(-0.25, 1.25, size=n)
                child = alpha * a + (1 - alpha) * b
            else:
                child = a.copy()
            mask = rng.random(n) < mutation
            if mask.any():
                child[mask] += rng.normal(0, sigma, size=int(mask.sum()))
            child = np.clip(child, lo, hi)
            new_pop.append(child)

        pop = np.array(new_pop[:pop_size])
        fitness = np.array([obj(ind) for ind in pop])
        evals += pop_size
        gi = int(np.argmin(fitness))
        if fitness[gi] < best_obj - 1e-9:
            best_obj = float(fitness[gi]); best_x = pop[gi].copy()
            stall = 0
        else:
            stall += 1
        feasible = best_obj < PENALTY
        history.append(best_obj if feasible else None)
        hist_feas.append(bool(feasible))
        f1 = None
        if track_freq:
            f1 = _best_f1(); evals += 1
            freq_hist.append(f1)
        if progress:
            progress(gen + 1, best_obj, feasible, f1)

    # Optional local polish: coordinate-wise shrink of the best design.
    best_x, best_obj, polish_evals = _local_polish(problem, best_x, best_obj, rng)
    evals += polish_evals
    if track_freq:
        freq_hist.append(_best_f1()); evals += 1   # frequency of the final design

    return {"best_x": best_x.tolist(), "best_obj": best_obj,
            "history": history, "history_feasible": hist_feas,
            "freq_history": freq_hist if track_freq else None,
            "evaluations": evals,
            "feasible": best_obj < PENALTY}


def _local_polish(problem, best_x, best_obj, rng, rounds=40):
    """Cheap coordinate-descent refinement after the GA.

    Tries to shrink (and nudge) each design variable and accepts any move
    that lowers the penalised objective. This cleans up the small amount
    of slack a stochastic search usually leaves behind.
    """
    if best_obj >= PENALTY:
        return best_x, best_obj, 0
    lo, hi = problem.bounds
    x = np.array(best_x, float)
    cur = best_obj
    evals = 0
    step = 0.08 * (hi - lo)
    for _ in range(rounds):
        improved = False
        for k in range(len(x)):
            for direction in (-1.0, 1.0):
                trial = x.copy()
                trial[k] = np.clip(trial[k] + direction * step, lo, hi)
                f = problem.objective(trial); evals += 1
                if f < cur - 1e-9:
                    x = trial; cur = f; improved = True
        if not improved:
            step *= 0.5
            if step < 1e-4 * (hi - lo):
                break
    return x, float(cur), evals


def _tournament(rng, fitness, k=3):
    idx = rng.integers(0, len(fitness), size=k)
    return idx[np.argmin(fitness[idx])]


# =============================================================================
# Two-bay three-storey steel MRF (discrete AISC W-sections)
# -----------------------------------------------------------------------------
# The canonical steel moment-frame benchmark of Pezeshk, Camp & Chen (2000),
# "Design of Nonlinear Framed Structures Using Genetic Optimization",
# J. Struct. Eng. 126(3):382-388, reused by Camp et al. (2005, ACO),
# Degertekin (harmony search), Togan (TLBO) and many others.
#
# Problem statement (per the original and its reproductions):
#   * 2 bays x 36 ft, 3 storeys x 10 ft; fixed bases; 12 nodes, 15 members.
#   * Single load case: uniform gravity w = 2.8 kip/ft on every beam plus
#     lateral point loads of 5 kips at levels 1 and 2 and 2.5 kips at the
#     roof, applied on the windward column line.
#   * A36 steel: E = 29,000 ksi, Fy = 36 ksi.
#   * Fabrication groups: ALL beams one section, ALL columns one section.
#     Beams from the AISC W-shape database (curated subset embedded here);
#     columns from W10 shapes only (all 18, as in the original).
#   * AISC-LRFD beam-column interaction (H1-1a/b); sway-frame Kx from the
#     storey stiffness ratios (Dumonteil closed form), Ky = 1.
#   * Best-known design: W24x62 beams + W10x60 columns = 18,792 lb.
#
# Modelling notes (stated honestly): analysis is linear elastic (Pezeshk
# reports P-Delta effects do not change the optimum significantly; Camp 2005
# used linear analysis); Mn = Mp = Fy*Zx (beams are braced at L/6, which puts
# Lb at/just above Lp for the optimal shapes, and Cb > 1 absorbs the small
# inelastic-LTB knockdown); shear is non-governing for this frame.
# Section properties are embedded AISC catalogue data (A, Ix, Zx, ry).
# =============================================================================
# (name, A in^2, Ix in^4, Zx in^3, ry in)  --  all 18 W10 column shapes
W10_COLUMNS = [
    ("W10x12",  3.54,  53.8, 12.6, 0.785), ("W10x15",  4.41,  68.9, 16.0, 0.810),
    ("W10x17",  4.99,  81.9, 18.7, 0.845), ("W10x19",  5.62,  96.3, 21.6, 0.874),
    ("W10x22",  6.49, 118.0, 26.0, 1.33),  ("W10x26",  7.61, 144.0, 31.3, 1.36),
    ("W10x30",  8.84, 170.0, 36.6, 1.37),  ("W10x33",  9.71, 171.0, 38.8, 1.94),
    ("W10x39", 11.5,  209.0, 46.8, 1.98),  ("W10x45", 13.3,  248.0, 54.9, 2.01),
    ("W10x49", 14.4,  272.0, 60.4, 2.54),  ("W10x54", 15.8,  303.0, 66.6, 2.56),
    ("W10x60", 17.6,  341.0, 74.6, 2.57),  ("W10x68", 20.0,  394.0, 85.3, 2.59),
    ("W10x77", 22.6,  455.0, 97.6, 2.60),  ("W10x88", 25.9,  534.0, 113.0, 2.63),
    ("W10x100",29.4,  623.0, 130.0, 2.65), ("W10x112",32.9,  716.0, 147.0, 2.68),
]
# (name, A in^2, Ix in^4, Zx in^3) -- curated economical beam shapes, by weight
W_BEAMS = [
    ("W12x26",  7.65,  204.0,  37.2), ("W14x26",  7.69,  245.0,  40.2),
    ("W16x26",  7.68,  301.0,  44.2), ("W16x31",  9.13,  375.0,  54.0),
    ("W18x35", 10.3,   510.0,  66.5), ("W16x40", 11.8,   518.0,  73.0),
    ("W18x40", 11.8,   612.0,  78.4), ("W21x44", 13.0,   843.0,  95.4),
    ("W18x46", 13.5,   712.0,  90.7), ("W18x50", 14.7,   800.0, 101.0),
    ("W21x50", 14.7,   984.0, 110.0), ("W18x55", 16.2,   890.0, 112.0),
    ("W24x55", 16.2,  1350.0, 134.0), ("W21x57", 16.7,  1170.0, 129.0),
    ("W18x60", 17.6,   984.0, 123.0), ("W21x62", 18.3,  1330.0, 144.0),
    ("W24x62", 18.2,  1550.0, 153.0), ("W21x68", 20.0,  1480.0, 160.0),
    ("W24x68", 20.1,  1830.0, 177.0), ("W18x71", 20.8,  1170.0, 146.0),
    ("W24x76", 22.4,  2100.0, 200.0), ("W21x83", 24.3,  1830.0, 196.0),
    ("W24x84", 24.7,  2370.0, 224.0), ("W27x84", 24.8,  2850.0, 244.0),
    ("W30x90", 26.4,  3620.0, 283.0), ("W24x94", 27.7,  2700.0, 254.0),
    ("W27x94", 27.7,  3270.0, 278.0), ("W30x99", 29.1,  3990.0, 312.0),
    ("W27x102",30.0,  3620.0, 305.0), ("W30x108",31.7,  4470.0, 346.0),
    ("W30x116",34.2,  4930.0, 378.0),
]
IN2, IN4, IN3 = inch**2, inch**4, inch**3


class SteelMRF3(Problem):
    key = "mrf3"; name = "3-Storey Steel MRF (discrete)"
    family = "static"; kind = "frame"; ndm = 2
    BAY = 36.0 * 12 * inch       # 36 ft in mm
    H = 10.0 * 12 * inch         # 10 ft in mm
    def __init__(self):
        super().__init__()
        B, H = self.BAY, self.H
        # 12 nodes: levels 0..3, column lines x = 0, B, 2B
        self.nodes = {}
        for lvl in range(4):
            for c in range(3):
                self.nodes[3 * lvl + c + 1] = (c * B, lvl * H)
        # 9 columns + 6 beams; gi = member index (0..14)
        elements = []; eid = 1
        for st in range(3):
            for c in range(3):
                i = 3 * st + c + 1; j = 3 * (st + 1) + c + 1
                elements.append((eid, i, j, eid - 1, "column")); eid += 1
        for lvl in range(1, 4):
            for bay in range(2):
                i = 3 * lvl + bay + 1; j = 3 * lvl + bay + 2
                elements.append((eid, i, j, eid - 1, "beam")); eid += 1
        self.elements = elements
        self.fixed = {1, 2, 3}
        self.E = 29000.0 * 6.894757          # MPa
        self.Fy = 36.0 * 6.894757            # MPa
        self.w = 2.8 * kip / (12 * inch)     # N/mm on every beam
        self.lateral = {10: 2.5 * kip, 7: 5.0 * kip, 4: 5.0 * kip}  # windward
        self.beam_ids = [e for (e, i, j, g, r) in elements if r == "beam"]
        self.col_ids = [e for (e, i, j, g, r) in elements if r == "column"]
        self.n_vars = 2
        self.bounds = (0.0, 1.0)             # genes -> discrete indices
        self.group_labels = ["Beam section (all 6 beams)",
                             "Column section (all 9 columns, W10)"]
        self.ref_mass = None                 # set after self-calibration below
        self.ref_mass = round(self._mass(16, 12), 1)  # W24x62 + W10x60 (published)
    # ---- discrete decoding -------------------------------------------------
    def _indices(self, x):
        x = np.clip(np.asarray(x, float), 0.0, 1.0)
        ib = int(round(x[0] * (len(W_BEAMS) - 1)))
        ic = int(round(x[1] * (len(W10_COLUMNS) - 1)))
        return ib, ic
    def _mass(self, ib, ic):
        Ab = W_BEAMS[ib][1] * IN2; Ac = W10_COLUMNS[ic][1] * IN2
        return 7850e-9 * (6 * Ab * self.BAY + 9 * Ac * self.H)
    # ---- LRFD machinery ----------------------------------------------------
    def _fcr(self, KL_over_r):
        lam = KL_over_r / np.pi * np.sqrt(self.Fy / self.E)
        if lam <= 1.5:
            return 0.658 ** (lam * lam) * self.Fy
        return 0.877 * self.Fy / (lam * lam)
    def _dumonteil_K(self, GA, GB):
        return np.sqrt((1.6 * GA * GB + 4.0 * (GA + GB) + 7.5)
                       / (GA + GB + 7.5))
    def evaluate(self, x):
        ib, ic = self._indices(x)
        bname, Ab_i, Ib_i, Zb_i = W_BEAMS[ib]
        cname, Ac_i, Ic_i, Zc_i, ry_i = W10_COLUMNS[ic]
        Ab = Ab_i * IN2 + 1e-3          # epsilon keeps area->I lookup unique
        Ac = Ac_i * IN2
        Ib = Ib_i * IN4; Ic = Ic_i * IN4
        Zb = Zb_i * IN3; Zc = Zc_i * IN3
        rx_c = np.sqrt(Ic / Ac); ry_c = ry_i * inch
        mass = self._mass(ib, ic)
        areas = np.array([Ac] * 9 + [Ab] * 6)
        sectI = lambda A: Ib if abs(A - Ab) < abs(A - Ac) else Ic
        # loads: lateral + equivalent nodal loads for the beam UDL
        w, L = self.w, self.BAY
        loads = {n: [0.0, 0.0, 0.0] for n in self.nodes}
        for n, F in self.lateral.items():
            loads[n][0] += F
        FEF_M = w * L * L / 12.0
        for (e, i, j, g, r) in self.elements:
            if r != "beam":
                continue
            loads[i][1] -= w * L / 2.0; loads[i][2] -= FEF_M
            loads[j][1] -= w * L / 2.0; loads[j][2] += FEF_M
        loads = {n: tuple(v) for n, v in loads.items()}
        # LRFD C1 first-order analyses: the frame and gravity load are
        # symmetric, so gravity-only is the no-translation (nt) case and
        # lateral-only is the lateral-translation (lt) case.
        loads_nt = {n: (0.0, v[1], v[2]) for n, v in loads.items()}
        loads_lt = {n: (v[0], 0.0, 0.0) for n, v in loads.items()}
        ok1, d_nt, endf_nt = frame_static(self.nodes, self.elements, areas,
                                          self.E, sectI, self.fixed, loads_nt)
        ok2, d_lt, endf_lt = frame_static(self.nodes, self.elements, areas,
                                          self.E, sectI, self.fixed, loads_lt)
        if not (ok1 and ok2):
            return {"ok": False, "mass": mass, "n_viol": 99}
        # sway-frame Kx per column from joint stiffness ratios (G = 1 at base)
        col_per_node = {}; beam_per_node = {}
        for (e, i, j, g, r) in self.elements:
            if r == "column":
                col_per_node.setdefault(i, 0.0); col_per_node[i] += Ic / self.H
                col_per_node.setdefault(j, 0.0); col_per_node[j] += Ic / self.H
            else:
                beam_per_node.setdefault(i, 0.0); beam_per_node[i] += Ib / L
                beam_per_node.setdefault(j, 0.0); beam_per_node[j] += Ib / L
        def G_at(n):
            if n in self.fixed:
                return 1.0
            return col_per_node.get(n, 0.0) / max(beam_per_node.get(n, 1e-12), 1e-12)
        phiPn_col = {}
        for (e, i, j, g, r) in self.elements:
            if r != "column":
                continue
            K = self._dumonteil_K(G_at(i), G_at(j))
            Fcr = min(self._fcr(K * self.H / rx_c),     # in-plane, sway K
                      self._fcr(1.0 * self.H / ry_c))   # out-of-plane, K=1
            phiPn_col[e] = 0.85 * Ac * Fcr
        phiMn_b = 0.9 * self.Fy * Zb
        phiMn_c = 0.9 * self.Fy * Zc
        phiPn_b = 0.85 * Ab * self.Fy   # beam axial is negligible (squash)
        # ---- B2 sway amplification per storey (LRFD C1-4 with sum Pe2) ----
        storey_cols = {st: [3 * st + c + 1 for c in range(3)] for st in range(3)}
        Pu_col = {}
        for (e, i, j, g, r) in self.elements:
            if r == "column":
                Ni = endf_nt[e][0] + endf_lt[e][0]
                Nj = endf_nt[e][2] + endf_lt[e][2]
                Pu_col[e] = max(abs(Ni), abs(Nj))
        B2 = {}
        for st in range(3):
            eids = storey_cols[st]
            sumPu = sum(Pu_col[e] for e in eids)
            sumPe2 = 0.0
            for e in eids:
                (ee, i, j, g, r) = self.elements[e - 1]
                K2 = self._dumonteil_K(G_at(i), G_at(j))
                sumPe2 += np.pi ** 2 * self.E * Ic / (K2 * self.H) ** 2
            den = 1.0 - sumPu / sumPe2
            B2[st] = 1.0 / den if den > 0.05 else 20.0
        Pe1_c = np.pi ** 2 * self.E * Ic / self.H ** 2        # K=1 in-plane
        # member checks: AISC-LRFD H1-1 with Mu = B1*Mnt + B2*Mlt
        nv = 0; bars = []
        for (e, i, j, g, r) in self.elements:
            Ni_nt, Mi_nt, Nj_nt, Mj_nt = endf_nt[e]
            Ni_lt, Mi_lt, Nj_lt, Mj_lt = endf_lt[e]
            Pu = max(abs(Ni_nt + Ni_lt), abs(Nj_nt + Nj_lt))
            if r == "beam":
                Mi_c = Mi_nt + FEF_M          # corrected true nt end moments
                Mj_c = Mj_nt - FEF_M
                Mmid = w * L * L / 8.0 - (Mi_c - Mj_c) / 2.0
                B2e = B2[(i - 1) // 3 - 1]    # storey below this floor level
                B1e = 1.0                     # transverse load, tiny axial
                Mu = max(abs(B1e * Mi_c + B2e * Mi_lt),
                         abs(B1e * Mj_c + B2e * Mj_lt),
                         abs(B1e * Mmid))
                phiPn, phiMn = phiPn_b, phiMn_b
                sec = bname
            else:
                st = (i - 1) // 3             # storey index from lower node
                # Cm from nt end moments (M1/M2 + for reverse curvature)
                Ma, Mb = abs(Mi_nt), abs(Mj_nt)
                if max(Ma, Mb) < 1e-9:
                    Cm = 0.6
                else:
                    ratio = (min(Ma, Mb) / max(Ma, Mb)) *                             (1.0 if Mi_nt * Mj_nt > 0 else -1.0)
                    Cm = 0.6 - 0.4 * ratio
                B1e = max(Cm / max(1.0 - Pu / Pe1_c, 0.05), 1.0)
                Mu = max(abs(B1e * Mi_nt + B2[st] * Mi_lt),
                         abs(B1e * Mj_nt + B2[st] * Mj_lt))
                phiPn, phiMn = phiPn_col[e], phiMn_c
                sec = cname
            pr = Pu / phiPn
            if pr >= 0.2:
                util = pr + (8.0 / 9.0) * Mu / phiMn
            else:
                util = pr / 2.0 + Mu / phiMn
            viol = util > 1.0
            if viol:
                nv += 1
            bars.append({"id": e, "role": f"{sec} {r}",
                         "area": float(Ab if r == 'beam' else Ac),
                         "sigma": float(util * 100.0), "limit": 100.0,
                         "unit": "%", "viol": bool(viol)})
        return {"ok": True, "mass": float(mass), "n_viol": nv,
                "feasible": nv == 0, "bars": bars,
                "sections": {"beams": bname, "columns": cname},
                "weight_lb": float(mass / 0.45359237)}
    def model_3d(self, x):
        ib, ic = self._indices(x)
        Ab = W_BEAMS[ib][1] * IN2; Ac = W10_COLUMNS[ic][1] * IN2
        areas = np.array([Ac] * 9 + [Ab] * 6)
        return _frame_model_payload(self, areas, sect_I_eq37)


# =============================================================================
# Reinforced-concrete problems with embodied-CO2 objective
# -----------------------------------------------------------------------------
# Formulations follow the published CO2-optimization benchmark literature:
#   * Beam   : flexural member family of Paya-Zaforteza, Yepes, Hospitaler &
#              Gonzalez-Vidosa (2009), Eng. Struct. 31:1501-1508, and
#              Camp & Huq (2013), Eng. Struct. 48:363-372 (ACI-style checks).
#   * Column : de Medeiros & Kripka (2014), Eng. Struct. 59:185-194 --
#              rectangular RC column under compression + uniaxial bending.
#   * Footing: Camp & Assadollahi (2013), Struct. Multidisc. Optim. 48:411-426
#              -- spread footing under a concentric column load with both
#              structural (ACI 318) and geotechnical limit states.
#
# Unit CO2 emissions follow the BEDEC PR/PCT ITeC database (Catalonia
# Institute of Construction Technology) as used throughout this literature:
# in-place structural concrete 224.94 kg CO2/m3 and placed reinforcing steel
# 2.82 kg CO2/kg.  Formwork and machine excavation are BEDEC-representative
# values; factors are database-dependent and easy to edit below.
# =============================================================================
EMISSION = {
    "concrete":   224.94,   # kg CO2 per m3  (in-place ~25 MPa, BEDEC PR/PCT)
    "steel":      2.82,     # kg CO2 per kg  (placed rebar, BEDEC PR/PCT) - default
    "formwork":   2.24,     # kg CO2 per m2  (timber formwork, BEDEC-repr.)
    "excavation": 13.16,    # kg CO2 per m3  (machine excavation, BEDEC-repr.)
}

# ---------------------------------------------------------------------------
# Selectable steel-production routes for the reinforcing steel.
# The rebar carbon factor depends strongly on how the steel was made; the
# user can pick a route and the optimizer prices the steel accordingly.
# Factors are cradle-type intensities per kg of rebar with sources noted:
#   * bedec : BEDEC PR/PCT ITeC "placed rebar" value used across the
#             CO2-optimization literature (Paya-Zaforteza et al. 2009
#             lineage) - cradle-to-site incl. fabrication.  DEFAULT, so
#             the studio reference values remain comparable.
#   * bof   : ore-based blast furnace + basic oxygen furnace primary
#             production, ~1.99 t CO2/t (New Steel Construction / Eurofer
#             system-expansion; IEEFA cites ~2.2 t/t).
#   * avg   : world-average crude-steel intensity, ~1.85 t CO2/t
#             (World Steel Association production-weighted average).
#   * eaf   : scrap-based electric-arc-furnace on a typical grid,
#             ~0.67 t CO2/t (Columbia CBS steel sector overview).
#   * green : scrap-EAF with high scrap share and low-carbon electricity,
#             ~0.36 t CO2/t (New Steel Construction secondary route).
# ---------------------------------------------------------------------------
STEEL_ROUTES = {
    "bedec": dict(label="BEDEC placed rebar (literature default)", co2=2.82,
                  note="BEDEC PR/PCT ITeC; cradle-to-site incl. fabrication"),
    "bof":   dict(label="BF-BOF primary (ore-based)", co2=1.99,
                  note="blast furnace + basic oxygen furnace, ~13% scrap"),
    "avg":   dict(label="World-average steel", co2=1.85,
                  note="worldsteel production-weighted average intensity"),
    "eaf":   dict(label="EAF scrap, grid electricity", co2=0.67,
                  note="secondary route, scrap-based electric arc furnace"),
    "green": dict(label="EAF scrap, low-carbon electricity", co2=0.36,
                  note="high scrap share + clean power ('green rebar')"),
}
DEFAULT_STEEL_ROUTE = "bedec"

# Indicative cradle-to-gate intensities for primary/secondary ALUMINIUM used by
# the classic aluminium truss benchmarks (kg CO2e per kg):
#   * world : ~16.7, International Aluminium Institute global average (2018)
#   * eu    : ~6.7,  European consumption mix (EAA / ICE database)
#   * recyc : ~0.6,  secondary (recycled) aluminium (ICE database)
ALU_ROUTES = {
    "world": dict(label="Primary aluminium, world average", co2=16.7,
                  note="IAI global average incl. smelting electricity"),
    "eu":    dict(label="Aluminium, European mix (default)", co2=6.7,
                  note="EAA / ICE consumption mix"),
    "recyc": dict(label="Recycled (secondary) aluminium", co2=0.6,
                  note="ICE database secondary route"),
}
MATERIAL_ROUTES = {"steel": STEEL_ROUTES, "aluminium": ALU_ROUTES, "rebar": STEEL_ROUTES}
MATERIAL_DEFAULT = {"steel": "avg", "aluminium": "eu", "rebar": "bedec"}


def routes_for(material):
    return MATERIAL_ROUTES.get(material, STEEL_ROUTES)
RHO_STEEL_KG = 7850.0e-9    # kg per mm3
MM3_TO_M3 = 1.0e-9
MM2_TO_M2 = 1.0e-6


def _beta1(fc):
    """ACI stress-block depth factor."""
    return max(0.65, min(0.85, 0.85 - 0.05 * (fc - 28.0) / 7.0))


def _rc_flex_doubly(b, d, dp, As_t, As_c, fc, fy):
    """Doubly-reinforced rectangular section in flexure (ACI 318 strain
    compatibility).  As_t = tension steel at depth d, As_c = compression
    steel at depth dp.  The neutral-axis depth c is solved by bisection on
    section equilibrium; the compression steel stress follows its strain
    (it is NOT assumed to yield).  Returns (Mn, phiMn, eps_t, c) with the
    ACI strength-reduction transition:
        eps_t >= 0.005            -> phi = 0.90   (tension-controlled)
        0.002 <  eps_t < 0.005    -> phi = 0.65 + 0.25(eps_t-0.002)/0.003
        eps_t <= 0.002            -> phi = 0.65   (compression-controlled)
    """
    b1 = _beta1(fc); Es = 200000.0
    def resid(c):
        a = min(b1 * c, d)
        fsc = np.clip(Es * 0.003 * (c - dp) / c, -fy, fy)
        # tension steel stress from its strain as well (no yield assumption)
        fst = np.clip(Es * 0.003 * (d - c) / c, -fy, fy)
        return 0.85 * fc * b * a + As_c * fsc - As_t * fst
    lo_c, hi_c = 1e-3 * d, 3.0 * d
    rlo = resid(lo_c)
    for _ in range(60):
        mid = 0.5 * (lo_c + hi_c)
        rm = resid(mid)
        if rlo * rm <= 0: hi_c = mid
        else: lo_c = mid; rlo = rm
    c = 0.5 * (lo_c + hi_c)
    a = min(b1 * c, d)
    fsc = np.clip(Es * 0.003 * (c - dp) / c, -fy, fy)
    Cc = 0.85 * fc * b * a
    Mn = Cc * (d - a / 2.0) + As_c * fsc * (d - dp)
    eps_t = 0.003 * (d - c) / c
    if eps_t >= 0.005: phi = 0.90
    elif eps_t <= 0.002: phi = 0.65
    else: phi = 0.65 + 0.25 * (eps_t - 0.002) / 0.003
    return float(Mn), float(phi * Mn), float(eps_t), float(c)


class _RCProblem(Problem):
    """Base for RC/CO2 problems: normalized genes in [0,1] map to physical
    variables through var_defs = [(name, lo, hi, unit), ...].  Every RC
    problem prices its reinforcing steel through a selectable production
    route (self.steel_route); the optimizer therefore responds to the
    chosen route -- e.g. cheap-carbon EAF rebar shifts optima toward more
    steel and less concrete."""
    family = "co2"
    kind = "rc"
    ndm = 3
    material = "rebar"
    def __init__(self):
        super().__init__()
        self.bounds = (0.0, 1.0)
    def _phys(self, x):
        x = np.clip(np.asarray(x, float), 0.0, 1.0)
        return [lo + xi * (hi - lo) for xi, (nm, lo, hi, un) in zip(x, self.var_defs)]
    def _variables(self, vals):
        return [{"name": nm, "value": float(v), "unit": un}
                for v, (nm, lo, hi, un) in zip(vals, self.var_defs)]


def _con(name, demand, capacity, unit=""):
    """Constraint record: utilisation = demand/capacity, ok if <= 1."""
    cap = max(float(capacity), 1e-12)
    util = float(demand) / cap
    return {"name": name, "demand": float(demand), "capacity": float(cap),
            "util": util, "ok": bool(util <= 1.0 + 1e-9), "unit": unit}


# -----------------------------------------------------------------------------
# P9: RC simply-supported beam, minimum embodied CO2
# -----------------------------------------------------------------------------
class RCBeamCO2(_RCProblem):
    key = "rc_beam"; name = "RC Beam (min CO\u2082)"
    def __init__(self):
        super().__init__()
        self.L = 8000.0          # mm span
        self.wD = 15.0           # N/mm superimposed dead load
        self.wL = 12.0           # N/mm live load
        self.fc = 25.0; self.fy = 420.0
        # Full flexural search space: both section dimensions AND both steel
        # layers.  Top steel (compression face at midspan) is a genuine
        # design variable: it raises phi-Mn and ductility at a carbon cost,
        # so the optimizer weighs steel against concrete for the chosen
        # steel-production route.  Lower bound 226 mm2 = 2 diam-12 hanger
        # bars, the constructive minimum for supporting the stirrup cage.
        self.var_defs = [("Width b", 250.0, 500.0, "mm"),
                         ("Depth h", 400.0, 1000.0, "mm"),
                         ("Bottom steel As,bot", 600.0, 6000.0, "mm\u00b2"),
                         ("Top steel As,top", 226.0, 3000.0, "mm\u00b2")]
        self.n_vars = 4
        self.ref_mass = 727.8    # studio reference: best of multi-seed GA runs
        self.group_labels = [v[0] for v in self.var_defs]
    def evaluate(self, x):
        b, h, As_b, As_t = self._phys(x)
        L, fc, fy = self.L, self.fc, self.fy
        d = h - 60.0; dp = 60.0
        wself = 24.0e-6 * b * h                       # N/mm
        wu = 1.2 * (self.wD + wself) + 1.6 * self.wL  # N/mm
        Mu = wu * L * L / 8.0                          # N*mm
        Vu = wu * (L / 2.0 - d)                        # N at d from support
        # doubly-reinforced flexure with ACI phi transition
        Mn, phiMn, eps_t, _c = _rc_flex_doubly(b, d, dp, As_b, As_t, fc, fy)
        rho = As_b / (b * d)
        rho_min = max(0.25 * np.sqrt(fc), 1.4) / fy
        # shear (with stirrups up to the ACI ceiling)
        Vc = 0.17 * np.sqrt(fc) * b * d
        Vs_max = 0.66 * np.sqrt(fc) * b * d
        phiVn = 0.75 * (Vc + Vs_max)
        # immediate live-load deflection on the ACI 318-19 effective inertia
        Ec = 4700.0 * np.sqrt(fc)
        Ma = (self.wD + wself + self.wL) * L * L / 8.0        # service moment
        Ie, Ig, Icr, Mcr = _rc_Ie(b, h, d, dp, As_b, As_t, fc, Ma)
        defl = 5.0 * self.wL * L ** 4 / (384.0 * Ec * Ie)
        cons = [
            _con("Flexure \u03c6Mn \u2265 Mu", Mu / 1e6, phiMn / 1e6, "kN\u00b7m"),
            _con("Shear \u03c6Vn \u2265 Vu", Vu / 1e3, phiVn / 1e3, "kN"),
            _con("\u03c1 \u2265 \u03c1min (bottom)", rho_min, rho, ""),
            _con("Ductility \u03b5t \u2265 0.004", 0.004, eps_t, ""),
            _con("LL deflection \u2264 L/360", defl, L / 360.0, "mm"),
            _con("h/b \u2264 3", h / b, 3.0, ""),
        ]
        nv = sum(0 if c["ok"] else 1 for c in cons)
        # stirrup demand -> spacing -> steel quantity
        Vs_req = max(Vu / 0.75 - Vc, 0.0)
        Av = 2.0 * 78.5                                # 2-leg diam-10
        s = min(d / 2.0, 600.0)                        # ACI 9.7.6.2.2
        if Vs_req > 0.33 * np.sqrt(fc) * b * d:
            s = min(d / 4.0, 300.0)
        if Vs_req > 1e-6:
            s = max(80.0, min(s, Av * fy * d / Vs_req))
        n_st = int(L / s) + 1
        st_len = 2.0 * ((b - 80.0) + (h - 80.0)) + 100.0
        steel_mm3 = (As_b + As_t) * L + n_st * st_len * 78.5
        conc_m3 = b * h * L * MM3_TO_M3
        steel_kg = steel_mm3 * RHO_STEEL_KG
        form_m2 = (b + 2.0 * h) * L * MM2_TO_M2
        co2_c = conc_m3 * EMISSION["concrete"]
        co2_s = steel_kg * self.steel_co2
        co2_f = form_m2 * EMISSION["formwork"]
        total = co2_c + co2_s + co2_f
        return {"ok": True, "mass": float(total), "n_viol": nv, "feasible": nv == 0,
                "variables": self._variables([b, h, As_b, As_t]),
                "constraints": cons,
                "steel_route": self.steel_route,
                "steel_co2_factor": self.steel_co2,
                "breakdown": {"concrete": float(co2_c), "steel": float(co2_s),
                              "formwork": float(co2_f)},
                "quantities": {"concrete_m3": float(conc_m3),
                               "steel_kg": float(steel_kg),
                               "formwork_m2": float(form_m2),
                               "stirrup_spacing_mm": float(s),
                               "eps_t": float(eps_t),
                               "Ie_over_Ig": float(Ie/Ig),
                               "Mcr_kNm": float(Mcr/1e6)}}
    def model_3d(self, x):
        b, h, As_b, As_t = self._phys(x)
        L = self.L
        boxes = [{"cx": 0, "cy": h / 2, "cz": 0, "dx": L, "dy": h, "dz": b,
                  "role": "concrete"}]
        rebars = []
        for (As_l, yy) in ((As_b, 50.0), (As_t, h - 50.0)):
            nb = int(np.clip(round(As_l / 314.0), 2, 10))
            rb = float(np.sqrt((As_l / nb) / np.pi))
            for k in range(nb):
                z = -b / 2 + 50.0 + k * (b - 100.0) / max(nb - 1, 1)
                rebars.append({"x1": -L / 2 + 30, "y1": yy, "z1": z,
                               "x2": L / 2 - 30, "y2": yy, "z2": z, "r": rb})
        n_loops = 9
        for k in range(n_loops):                     # stirrup loops (visual)
            xs = -L / 2 + 200.0 + k * (L - 400.0) / (n_loops - 1)
            y0, y1 = 42.0, h - 42.0; z0, z1 = -b / 2 + 42.0, b / 2 - 42.0
            for (p, q) in (((xs, y0, z0), (xs, y0, z1)), ((xs, y1, z0), (xs, y1, z1)),
                           ((xs, y0, z0), (xs, y1, z0)), ((xs, y0, z1), (xs, y1, z1))):
                rebars.append({"x1": p[0], "y1": p[1], "z1": p[2],
                               "x2": q[0], "y2": q[1], "z2": q[2], "r": 5.0})
        return {"type": "rc", "boxes": boxes, "rebars": rebars, "ext": L}


# -----------------------------------------------------------------------------
# P10: RC column under compression + uniaxial bending, minimum embodied CO2
# -----------------------------------------------------------------------------
class RCColumnCO2(_RCProblem):
    key = "rc_column"; name = "RC Column (min CO\u2082)"
    def __init__(self):
        super().__init__()
        self.lu = 3000.0
        self.Pu = 1200.0e3       # N factored axial
        self.Mu = 100.0e6        # N*mm factored moment (fixed sense)
        self.fc = 25.0; self.fy = 500.0
        # Full section search space: both dimensions AND the steel on each
        # face independently.  Because the design moment acts in one known
        # sense, asymmetric reinforcement (heavier tension face) is a
        # legitimate and often lighter-carbon layout than the conventional
        # symmetric cage; the strain-compatibility interaction analysis
        # handles either.  Total-steel limits follow ACI 318 10.6.1.1
        # (1% min) with a 4% practical cap for lap-splice congestion.
        self.var_defs = [("Width b", 250.0, 600.0, "mm"),
                         ("Depth h", 250.0, 800.0, "mm"),
                         ("Tension-face steel As,t", 300.0, 5000.0, "mm\u00b2"),
                         ("Compression-face steel As,c", 300.0, 5000.0, "mm\u00b2")]
        self.n_vars = 4
        self.ref_mass = 163.0    # studio reference: best of multi-seed GA runs
        self.group_labels = [v[0] for v in self.var_defs]
    def evaluate(self, x):
        b, h, As_t, As_c = self._phys(x)
        As = As_t + As_c
        rho = As / (b * h)
        e = max(self.Mu / self.Pu, 15.0 + 0.03 * h)
        phiPn = _rc_phiPn_at_e(b, h, As_c, As_t, self.fc, self.fy, e)
        Po = 0.85 * self.fc * (b * h - As) + self.fy * As
        cons = [
            _con("P-M interaction \u03c6Pn(e) \u2265 Pu", self.Pu / 1e3,
                 phiPn / 1e3, "kN"),
            _con("Axial cap Pu \u2264 0.80\u03c6Po", self.Pu / 1e3,
                 0.65 * 0.80 * Po / 1e3, "kN"),
            _con("Slenderness klu/r \u2264 34", self.lu / (0.3 * h), 34.0, ""),
            _con("h/b \u2264 3", h / b, 3.0, ""),
            _con("\u03c1 \u2265 1% (ACI 10.6.1.1)", 0.01, rho, ""),
            _con("\u03c1 \u2264 4% (practical)", rho, 0.04, ""),
        ]
        nv = sum(0 if c["ok"] else 1 for c in cons)
        s_tie = min(320.0, 384.0, min(b, h))
        n_tie = int(self.lu / s_tie) + 1
        tie_len = 2.0 * ((b - 80.0) + (h - 80.0)) + 150.0
        steel_mm3 = As * self.lu + n_tie * tie_len * 50.3      # diam-8 ties
        conc_m3 = b * h * self.lu * MM3_TO_M3
        steel_kg = steel_mm3 * RHO_STEEL_KG
        form_m2 = 2.0 * (b + h) * self.lu * MM2_TO_M2
        co2_c = conc_m3 * EMISSION["concrete"]
        co2_s = steel_kg * self.steel_co2
        co2_f = form_m2 * EMISSION["formwork"]
        total = co2_c + co2_s + co2_f
        return {"ok": True, "mass": float(total), "n_viol": nv, "feasible": nv == 0,
                "variables": self._variables([b, h, As_t, As_c]),
                "constraints": cons,
                "steel_route": self.steel_route,
                "steel_co2_factor": self.steel_co2,
                "breakdown": {"concrete": float(co2_c), "steel": float(co2_s),
                              "formwork": float(co2_f)},
                "quantities": {"concrete_m3": float(conc_m3),
                               "steel_kg": float(steel_kg),
                               "formwork_m2": float(form_m2),
                               "rho_total": float(rho),
                               "eccentricity_mm": float(e)}}
    def model_3d(self, x):
        b, h, As_t, As_c = self._phys(x)
        lu = self.lu
        boxes = [{"cx": 0, "cy": lu / 2, "cz": 0, "dx": h, "dy": lu, "dz": b,
                  "role": "concrete"}]
        rebars = []
        # tension face at +x (x = h/2 - 55), compression face at -x
        for (As_l, xx) in ((As_t, h / 2 - 55.0), (As_c, -h / 2 + 55.0)):
            nb = int(np.clip(round(As_l / 491.0), 2, 6))
            rb = float(np.sqrt((As_l / nb) / np.pi))
            for k in range(nb):
                zz = -b / 2 + 55.0 + k * (b - 110.0) / max(nb - 1, 1)
                rebars.append({"x1": xx, "y1": 30.0, "z1": zz,
                               "x2": xx, "y2": lu - 30.0, "z2": zz, "r": rb})
        s_tie = min(320.0, 384.0, min(b, h))
        n_loops = min(int(lu / s_tie) + 1, 12)
        for k in range(n_loops):
            yy = 60.0 + k * (lu - 120.0) / max(n_loops - 1, 1)
            x0, x1 = -h / 2 + 45.0, h / 2 - 45.0
            z0, z1 = -b / 2 + 45.0, b / 2 - 45.0
            for (p, q) in (((x0, yy, z0), (x1, yy, z0)), ((x0, yy, z1), (x1, yy, z1)),
                           ((x0, yy, z0), (x0, yy, z1)), ((x1, yy, z0), (x1, yy, z1))):
                rebars.append({"x1": p[0], "y1": p[1], "z1": p[2],
                               "x2": q[0], "y2": q[1], "z2": q[2], "r": 4.0})
        return {"type": "rc", "boxes": boxes, "rebars": rebars, "ext": lu}


# -----------------------------------------------------------------------------
# P11: RC spread footing under a concentric column load, minimum embodied CO2
# -----------------------------------------------------------------------------
class RCFootingCO2(_RCProblem):
    key = "rc_footing"; name = "RC Footing (min CO\u2082)"
    def __init__(self):
        super().__init__()
        self.c = 400.0                      # mm square column
        self.PD = 750.0e3; self.PL = 400.0e3  # N service loads
        self.qa = 0.20                      # MPa allowable gross bearing
        self.Df = 1500.0                    # mm embedment
        self.gam_s = 18.0e-6                # N/mm3 soil
        self.gam_c = 24.0e-6                # N/mm3 concrete
        self.fc = 25.0; self.fy = 420.0
        self.var_defs = [("Footing width B", 1800.0, 4000.0, "mm"),
                         ("Footing length L", 1800.0, 4000.0, "mm"),
                         ("Thickness h", 350.0, 1000.0, "mm"),
                         ("Steel (B-dir) As\u1d2e", 1500.0, 12000.0, "mm\u00b2"),
                         ("Steel (L-dir) As\u1d38", 1500.0, 12000.0, "mm\u00b2")]
        self.n_vars = 5
        self.ref_mass = 1155.8   # studio reference: best of long GA runs
        self.group_labels = [v[0] for v in self.var_defs]
    def evaluate(self, x):
        B, L, h, AsB, AsL = self._phys(x)
        fc, fy, c = self.fc, self.fy, self.c
        d = h - 95.0
        # service bearing (gross): column + footing weight + soil over footing
        q_srv = ((self.PD + self.PL) / (B * L)
                 + self.gam_c * h + self.gam_s * (self.Df - h))
        # factored net pressure
        qu = (1.2 * self.PD + 1.6 * self.PL) / (B * L)
        # two-way (punching) shear at d/2
        bo = 4.0 * (c + d)
        Vu_p = qu * (B * L - (c + d) ** 2)
        phiVc_p = 0.75 * 0.33 * np.sqrt(fc) * bo * d
        # one-way shear at d from the column face, each direction
        Vu_1L = qu * B * max((L - c) / 2.0 - d, 0.0)
        Vu_1B = qu * L * max((B - c) / 2.0 - d, 0.0)
        phiVc_1L = 0.75 * 0.17 * np.sqrt(fc) * B * d
        phiVc_1B = 0.75 * 0.17 * np.sqrt(fc) * L * d
        # flexure at the column face; AsL runs along L resisting the L-cantilever
        Mu_L = qu * B * ((L - c) / 2.0) ** 2 / 2.0
        Mu_B = qu * L * ((B - c) / 2.0) ** 2 / 2.0
        aL = AsL * fy / (0.85 * fc * B)
        aB = AsB * fy / (0.85 * fc * L)
        phiMn_L = 0.9 * AsL * fy * (d - aL / 2.0)
        phiMn_B = 0.9 * AsB * fy * (d - aB / 2.0)
        As_min_L = 0.0018 * B * h
        As_min_B = 0.0018 * L * h
        cons = [
            _con("Soil bearing q \u2264 qa", q_srv * 1e3, self.qa * 1e3, "kPa"),
            _con("Punching shear", Vu_p / 1e3, phiVc_p / 1e3, "kN"),
            _con("One-way shear (L)", Vu_1L / 1e3, phiVc_1L / 1e3, "kN"),
            _con("One-way shear (B)", Vu_1B / 1e3, phiVc_1B / 1e3, "kN"),
            _con("Flexure (L-dir)", Mu_L / 1e6, phiMn_L / 1e6, "kN\u00b7m"),
            _con("Flexure (B-dir)", Mu_B / 1e6, phiMn_B / 1e6, "kN\u00b7m"),
            _con("As\u1d38 \u2265 As,min", As_min_L, AsL, "mm\u00b2"),
            _con("As\u1d2e \u2265 As,min", As_min_B, AsB, "mm\u00b2"),
        ]
        nv = sum(0 if cn["ok"] else 1 for cn in cons)
        conc_m3 = B * L * h * MM3_TO_M3
        steel_mm3 = AsL * L + AsB * B          # bars run the full footprint
        steel_kg = steel_mm3 * RHO_STEEL_KG
        form_m2 = 2.0 * (B + L) * h * MM2_TO_M2
        exc_m3 = B * L * self.Df * MM3_TO_M3
        co2_c = conc_m3 * EMISSION["concrete"]
        co2_s = steel_kg * self.steel_co2
        co2_f = form_m2 * EMISSION["formwork"]
        co2_e = exc_m3 * EMISSION["excavation"]
        total = co2_c + co2_s + co2_f + co2_e
        return {"ok": True, "mass": float(total), "n_viol": nv, "feasible": nv == 0,
                "variables": self._variables([B, L, h, AsB, AsL]),
                "constraints": cons,
                "steel_route": self.steel_route,
                "steel_co2_factor": self.steel_co2,
                "breakdown": {"concrete": float(co2_c), "steel": float(co2_s),
                              "formwork": float(co2_f), "excavation": float(co2_e)},
                "quantities": {"concrete_m3": float(conc_m3),
                               "steel_kg": float(steel_kg),
                               "formwork_m2": float(form_m2),
                               "excavation_m3": float(exc_m3)}}
    def model_3d(self, x):
        B, L, h, AsB, AsL = self._phys(x)
        c = self.c
        boxes = [
            {"cx": 0, "cy": -self.Df - 200, "cz": 0, "dx": 1.8 * L,
             "dy": 400.0, "dz": 1.8 * B, "role": "soil"},
            {"cx": 0, "cy": h / 2, "cz": 0, "dx": L, "dy": h, "dz": B,
             "role": "concrete"},
            {"cx": 0, "cy": h + 500.0, "cz": 0, "dx": c, "dy": 1000.0, "dz": c,
             "role": "column"},
        ]
        rebars = []
        nL = int(np.clip(round(AsL / 314.0), 4, 14))
        nB = int(np.clip(round(AsB / 314.0), 4, 14))
        rL = float(np.sqrt((AsL / nL) / np.pi))
        rB = float(np.sqrt((AsB / nB) / np.pi))
        for k in range(nL):                      # bars along L, spread across B
            z = -B / 2 + 90.0 + k * (B - 180.0) / max(nL - 1, 1)
            rebars.append({"x1": -L / 2 + 70, "y1": 75.0, "z1": z,
                           "x2": L / 2 - 70, "y2": 75.0, "z2": z, "r": rL})
        for k in range(nB):                      # bars along B, spread across L
            xx = -L / 2 + 90.0 + k * (L - 180.0) / max(nB - 1, 1)
            rebars.append({"x1": xx, "y1": 75.0 + 2 * rL, "z1": -B / 2 + 70,
                           "x2": xx, "y2": 75.0 + 2 * rL, "z2": B / 2 - 70, "r": rB})
        return {"type": "rc", "boxes": boxes, "rebars": rebars,
                "ext": max(B, L) * 1.6}


# -----------------------------------------------------------------------------
# P13: Three-storey, two-bay RC moment frame, minimum embodied CO2
# -----------------------------------------------------------------------------
# An instance of the published RC-frame CO2 benchmark family:
#   Camp & Huq (2013), Eng. Struct. 48:363-372 (ACI 318, frames of 2-4 bays
#   and up to 8 storeys, cost and CO2 objectives); Camp, Pezeshk & Hansson
#   (2003), J. Struct. Eng. 129(1); Paya-Zaforteza et al. (2009), Eng.
#   Struct. 31:1501-1508 (simulated annealing, BEDEC emissions).
# Fabrication grouping as in the frame literature: one section + steel
# layout for all beams, one for all columns.  Analysis is first-order
# elastic with ACI 6.6.3.1.1 cracked stiffnesses (0.35Ig beams, 0.70Ig
# columns) under two factored combinations: 1.2D+1.6L and 1.2D+1.0L+1.0E.
# The strong-column/weak-beam provision (ACI 18.7.3.2) is enforced at all
# beam-column joints below the roof.
# -----------------------------------------------------------------------------
def _rc_Ie(b, h, d, dp, As_t, As_c, fc, Ma):
    """Effective moment of inertia per ACI 318-19 Table 24.2.3.5 for a doubly
    reinforced rectangular section at service moment Ma (N*mm).  The cracked
    inertia comes from the transformed section (n = Es/Ec, compression steel
    weighted n-1); Ie = Ig below (2/3)Mcr, else the Bischoff form.
    Returns (Ie, Ig, Icr, Mcr)."""
    Ec = 4700.0*np.sqrt(fc); n = 200000.0/Ec
    Ig = b*h**3/12.0
    Mcr = 0.62*np.sqrt(fc)*Ig/(h/2.0)
    a = b/2.0; bq = (n-1.0)*As_c + n*As_t; cq = -((n-1.0)*As_c*dp + n*As_t*d)
    kd = (-bq + np.sqrt(bq*bq - 4.0*a*cq))/(2.0*a)
    Icr = b*kd**3/3.0 + n*As_t*(d-kd)**2 + (n-1.0)*As_c*(kd-dp)**2
    if Ma <= (2.0/3.0)*Mcr:
        Ie = Ig
    else:
        r = ((2.0/3.0)*Mcr/Ma)**2
        Ie = Icr/(1.0 - r*(1.0 - Icr/Ig))
    return float(min(Ie, Ig)), float(Ig), float(Icr), float(Mcr)


def _rc_pm_section(b, h, As_c, As_t, fc, fy, c):
    """(Pn, Mn) of a 2-layer rectangular RC section with (possibly unequal)
    compression-face steel As_c at d' and tension-face steel As_t at h-d';
    compression positive, moment about mid-height."""
    dp, dd = 60.0, h - 60.0
    a = min(_beta1(fc) * c, h)
    Cc = 0.85 * fc * b * a
    f_top = np.clip(200000.0 * 0.003 * (c - dp) / c, -fy, fy)
    f_bot = np.clip(200000.0 * 0.003 * (c - dd) / c, -fy, fy)
    F_top = As_c * f_top
    F_bot = As_t * f_bot
    Pn = Cc + F_top + F_bot
    Mn = (Cc * (h / 2.0 - a / 2.0) + F_top * (h / 2.0 - dp)
          + F_bot * (h / 2.0 - dd))
    return Pn, Mn


def _rc_phiPn_at_e(b, h, As_c, As_t, fc, fy, e, phi=0.65):
    """phi*Pn on the interaction surface at eccentricity e (bisection),
    bending putting As_t in tension."""
    lo_c, hi_c = 0.05 * h, 8.0 * h
    g = lambda c: (lambda PM: PM[1] - e * PM[0])(
        _rc_pm_section(b, h, As_c, As_t, fc, fy, c))
    glo, ghi = g(lo_c), g(hi_c)
    if glo * ghi > 0:
        return 0.0
    for _ in range(50):
        mid = 0.5 * (lo_c + hi_c)
        gm = g(mid)
        if glo * gm <= 0: hi_c = mid
        else: lo_c = mid; glo = gm
    Pn, Mn = _rc_pm_section(b, h, As_c, As_t, fc, fy, 0.5 * (lo_c + hi_c))
    As = As_c + As_t
    Po = 0.85 * fc * (b * h - As) + fy * As
    return phi * min(max(Pn, 0.0), 0.80 * Po)


def _rc_Mn_at_P(b, h, As_c, As_t, fc, fy, P):
    """Nominal Mn at axial load P (bisection on c; Pn increases with c)."""
    lo_c, hi_c = 0.02 * h, 10.0 * h
    for _ in range(50):
        mid = 0.5 * (lo_c + hi_c)
        Pn, _ = _rc_pm_section(b, h, As_c, As_t, fc, fy, mid)
        if Pn < P: lo_c = mid
        else: hi_c = mid
    return _rc_pm_section(b, h, As_c, As_t, fc, fy, 0.5 * (lo_c + hi_c))[1]


class RCFrame3CO2(_RCProblem):
    key = "rc_frame3"; name = "3-Storey RC Frame (min CO\u2082)"
    ndm = 2
    BAY = 6000.0; H = 3000.0
    def __init__(self):
        super().__init__()
        B, H = self.BAY, self.H
        self.nodes = {}
        for lvl in range(4):
            for c in range(3):
                self.nodes[3 * lvl + c + 1] = (c * B, lvl * H)
        elements = []; eid = 1
        for st in range(3):
            for c in range(3):
                elements.append((eid, 3*st+c+1, 3*(st+1)+c+1, eid-1, "column")); eid += 1
        for lvl in range(1, 4):
            for bay in range(2):
                elements.append((eid, 3*lvl+bay+1, 3*lvl+bay+2, eid-1, "beam")); eid += 1
        self.elements = elements
        self.fixed = {1, 2, 3}
        self.fc = 25.0; self.fy = 420.0
        self.Ec = 4700.0 * np.sqrt(self.fc)
        self.wD = 22.0   # N/mm superimposed dead (slab+finishes, 6 m tributary)
        self.wL = 10.0   # N/mm live
        self.Elat = {4: 25.0e3, 7: 50.0e3, 10: 75.0e3}   # N, seismic-type
        self.var_defs = [("Beam width b\u1d47", 250.0, 450.0, "mm"),
                         ("Beam depth h\u1d47", 400.0, 800.0, "mm"),
                         ("Beam top steel As,top", 600.0, 5000.0, "mm\u00b2"),
                         ("Beam bottom steel As,bot", 600.0, 5000.0, "mm\u00b2"),
                         ("Column width b\u1d9c", 300.0, 700.0, "mm"),
                         ("Column depth h\u1d9c", 300.0, 700.0, "mm"),
                         ("Column steel ratio \u03c1\u1d9c", 0.01, 0.04, "")]
        self.n_vars = 7
        self.ref_mass = 5301.9   # studio reference: best of multi-seed GA runs
        self.group_labels = [v[0] for v in self.var_defs]
    def _solve(self, bb, hb, bc, hc, w_beam, with_lat):
        Ab = float(bb) * float(hb) + 1e-3; Ac = float(bc) * float(hc)
        Ib = 0.35 * bb * hb**3 / 12.0; Icc = 0.70 * bc * hc**3 / 12.0
        areas = np.array([Ac]*9 + [Ab]*6)
        # closest-match assignment is immune to float-rounding mismatches
        sectI = lambda A: Ib if abs(A - Ab) < abs(A - Ac) else Icc
        L = self.BAY; FEF_M = w_beam * L * L / 12.0
        loads = {n: [0.0, 0.0, 0.0] for n in self.nodes}
        for (e, i, j, g, r) in self.elements:
            if r == "beam":
                loads[i][1] -= w_beam*L/2.0; loads[i][2] -= FEF_M
                loads[j][1] -= w_beam*L/2.0; loads[j][2] += FEF_M
        if with_lat:
            for n, F in self.Elat.items():
                loads[n][0] += F
        ok, disp, endf = frame_static(self.nodes, self.elements, areas, self.Ec,
                                      sectI, self.fixed,
                                      {n: tuple(v) for n, v in loads.items()})
        return ok, endf, FEF_M
    def evaluate(self, x):
        bb, hb, At, Abot, bc, hc, rc = self._phys(x)
        fc, fy, L, H = self.fc, self.fy, self.BAY, self.H
        As_c = rc * bc * hc
        d_b = hb - 60.0
        wself = 24.0e-6 * bb * hb
        combos = [(1.2*(self.wD+wself) + 1.6*self.wL, False),
                  (1.2*(self.wD+wself) + 1.0*self.wL, True)]
        Mu_hog = Mu_sag = Vu = 0.0
        Pu_col = {e: 0.0 for e in range(1, 10)}
        Mu_col = {e: 0.0 for e in range(1, 10)}
        for (w, lat) in combos:
            ok, endf, FEF_M = self._solve(bb, hb, bc, hc, w, lat)
            if not ok:
                return {"ok": False, "mass": 1e9, "n_viol": 99}
            for (e, i, j, g, r) in self.elements:
                Ni, Mi, Nj, Mj = endf[e]
                if r == "beam":
                    Mi_c = Mi + FEF_M; Mj_c = Mj - FEF_M
                    Mu_hog = max(Mu_hog, abs(Mi_c), abs(Mj_c))
                    Mu_sag = max(Mu_sag, abs(w*L*L/8.0 - (Mi_c - Mj_c)/2.0))
                    Vu = max(Vu, w*L/2.0 + abs(Mi_c + Mj_c)/L)
                else:
                    Pu_col[e] = max(Pu_col[e], abs(Ni), abs(Nj))
                    Mu_col[e] = max(Mu_col[e], abs(Mi), abs(Mj))
        # beam capacities: doubly-reinforced strain compatibility -- the far
        # face steel acts in compression for each bending sense
        Mn_T, phiMn_T, epsT, _ = _rc_flex_doubly(bb, d_b, 60.0, At, Abot, fc, fy)
        Mn_B, phiMn_B, epsB, _ = _rc_flex_doubly(bb, d_b, 60.0, Abot, At, fc, fy)
        eps_min = min(epsT, epsB)
        Vc = 0.17*np.sqrt(fc)*bb*d_b
        phiVn = 0.75*(Vc + 0.66*np.sqrt(fc)*bb*d_b)
        rho_T = At/(bb*d_b); rho_B = Abot/(bb*d_b)
        rho_min = max(0.25*np.sqrt(fc), 1.4)/fy
        # column interaction (worst of 9 columns over the combo envelope);
        # symmetric cage (As_c/2 per face): seismic lateral load acts in both
        # directions, so column moments reverse and symmetry is the correct
        # engineering layout (unlike the single-sense isolated column above)
        util_pm = 0.0
        for e in range(1, 10):
            Pu, Mu = Pu_col[e], max(Mu_col[e], Pu_col[e]*(15.0 + 0.03*hc))
            phiPn = _rc_phiPn_at_e(bc, hc, As_c/2.0, As_c/2.0, fc, fy,
                                   Mu/max(Pu, 1.0))
            util_pm = max(util_pm, Pu/max(phiPn, 1.0))
        # strong column - weak beam at joints below the roof (ACI 18.7.3.2)
        Mnb_T, Mnb_B = Mn_T, Mn_B
        scwb = 0.0
        for n in range(4, 10):                      # level-1 and level-2 joints
            lvl = (n - 1)//3; line = (n - 1) % 3
            e_below = 3*(lvl-1) + line + 1; e_above = 3*lvl + line + 1
            sMnc = (_rc_Mn_at_P(bc, hc, As_c/2.0, As_c/2.0, fc, fy, Pu_col[e_below]) +
                    _rc_Mn_at_P(bc, hc, As_c/2.0, As_c/2.0, fc, fy, Pu_col[e_above]))
            sMnb = (Mnb_T + Mnb_B) if line == 1 else max(Mnb_T, Mnb_B)
            scwb = max(scwb, 1.2*sMnb/max(sMnc, 1.0))
        cons = [
            _con("Beam hogging \u03c6Mn \u2265 Mu", Mu_hog/1e6, phiMn_T/1e6, "kN\u00b7m"),
            _con("Beam sagging \u03c6Mn \u2265 Mu", Mu_sag/1e6, phiMn_B/1e6, "kN\u00b7m"),
            _con("Beam shear \u03c6Vn \u2265 Vu", Vu/1e3, phiVn/1e3, "kN"),
            _con("\u03c1 \u2265 \u03c1min (beam)", rho_min, min(rho_T, rho_B), ""),
            _con("Ductility \u03b5t \u2265 0.004 (beam)", 0.004, eps_min, ""),
            _con("Beam depth \u2265 L/21", L/21.0, hb, "mm"),
            _con("Column P-M interaction", util_pm, 1.0, ""),
            _con("Column slenderness lu/r \u2264 22", H/(0.3*hc), 22.0, ""),
            _con("Strong col / weak beam \u2265 1.2", scwb, 1.0, ""),
        ]
        nv = sum(0 if c0["ok"] else 1 for c0 in cons)
        # quantities & CO2
        Vs_req = max(Vu/0.75 - Vc, 0.0)
        Av = 2.0*78.5
        s = min(d_b/2.0, 600.0)
        if Vs_req > 1e-6:
            s = max(80.0, min(s, Av*fy*d_b/Vs_req))
        n_st = (int(L/s) + 1) * 6
        st_len = 2.0*((bb - 80.0) + (hb - 80.0)) + 100.0
        s_tie = min(320.0, 384.0, min(bc, hc))
        n_tie = (int(H/s_tie) + 1) * 9
        tie_len = 2.0*((bc - 80.0) + (hc - 80.0)) + 150.0
        steel_mm3 = ((At + Abot)*L*6 + n_st*st_len*78.5
                     + As_c*H*9 + n_tie*tie_len*50.3)
        conc_m3 = (bb*hb*L*6 + bc*hc*H*9) * MM3_TO_M3
        steel_kg = steel_mm3 * RHO_STEEL_KG
        form_m2 = ((bb + 2*hb)*L*6 + 2*(bc + hc)*H*9) * MM2_TO_M2
        co2_c = conc_m3*EMISSION["concrete"]; co2_s = steel_kg*self.steel_co2
        co2_f = form_m2*EMISSION["formwork"]
        total = co2_c + co2_s + co2_f
        return {"ok": True, "mass": float(total), "n_viol": nv, "feasible": nv == 0,
                "variables": self._variables([bb, hb, At, Abot, bc, hc, rc]),
                "constraints": cons,
                "steel_route": self.steel_route,
                "steel_co2_factor": self.steel_co2,
                "breakdown": {"concrete": float(co2_c), "steel": float(co2_s),
                              "formwork": float(co2_f)},
                "quantities": {"concrete_m3": float(conc_m3),
                               "steel_kg": float(steel_kg),
                               "formwork_m2": float(form_m2),
                               "stirrup_spacing_mm": float(s)}}
    def model_3d(self, x):
        bb, hb, At, Abot, bc, hc, rc = self._phys(x)
        As_c = rc * bc * hc
        B, H = self.BAY, self.H
        boxes = []; rebars = []
        for st in range(3):
            for c in range(3):
                boxes.append({"cx": c*B, "cy": st*H + H/2, "cz": 0,
                              "dx": hc, "dy": H, "dz": bc, "role": "concrete"})
                nb = int(np.clip(2*round(As_c/491.0/2), 4, 8))
                rb = float(np.sqrt((As_c/nb)/np.pi))
                per = nb // 2
                for k in range(per):
                    xx = c*B - hc/2 + 50 + k*(hc - 100)/max(per - 1, 1)
                    for zz in (-bc/2 + 50, bc/2 - 50):
                        rebars.append({"x1": xx, "y1": st*H + 20, "z1": zz,
                                       "x2": xx, "y2": (st+1)*H - 20, "z2": zz, "r": rb})
        for lvl in range(1, 4):
            for bay in range(2):
                x0 = bay*B; xc = x0 + B/2
                boxes.append({"cx": xc, "cy": lvl*H - hb/2, "cz": 0,
                              "dx": B, "dy": hb, "dz": bb, "role": "concrete"})
                for (As_l, yoff) in ((Abot, -hb + 50), (At, -50)):
                    nb = int(np.clip(round(As_l/314.0), 2, 5))
                    rb = float(np.sqrt((As_l/nb)/np.pi))
                    for k in range(nb):
                        z = -bb/2 + 45 + k*(bb - 90)/max(nb - 1, 1)
                        rebars.append({"x1": x0 + 40, "y1": lvl*H + yoff, "z1": z,
                                       "x2": x0 + B - 40, "y2": lvl*H + yoff,
                                       "z2": z, "r": rb})
        return {"type": "rc", "boxes": boxes, "rebars": rebars, "ext": 2*B}


# -----------------------------------------------------------------------------
# P14/P15: Built-up I-beam design to AISC 360 -- ASD and LRFD
# -----------------------------------------------------------------------------
# Doubly symmetric welded I-section sized for minimum mass under a user-set
# moment demand and span.  The formulation carries the complete AISC 360
# flexural machinery so every classification the code recognises is designed
# correctly: compact / noncompact / slender FLANGES (F2, F3) and compact /
# noncompact / slender WEBS (F2-F3 / F4 / F5), each either laterally
# supported (Lb = 0) or unsupported (Lb = span, or a user value), with
# lateral-torsional buckling per the relevant chapter and Cb = 1
# (conservative, uniform-moment).  Shear follows G2 (unstiffened web,
# kv = 5.34) with the G1 phi/Omega exception; serviceability is a live-level
# deflection limit of L/360; proportioning limits F13.2 (h/tw <= 0.40 E/Fy)
# and F5 (aw <= 10) plus the weldability rule tf >= tw complete the set.
# The default demand (100 kN*m over 7 m, Fy = 345 MPa, laterally
# unsupported) is editable per run from the workspace.
# -----------------------------------------------------------------------------
class _BuiltUpIBeam(Problem):
    family = "member"
    kind = "beam"
    ndm = 3
    method = "LRFD"
    def __init__(self):
        super().__init__()
        self.bounds = (0.0, 1.0)
        self.E = 200000.0
        self.Fy = 345.0
        self.M = 100.0e6        # N*mm demand (ASD: Ma, LRFD: Mu)
        self.L = 7000.0         # mm span
        self.Lb = 7000.0        # mm unbraced length (0 = laterally supported)
        self.Cb = 1.0           # LTB modification factor (1.0 = uniform moment)
        self.var_defs = [("Flange width bf", 150.0, 450.0, "mm"),
                         ("Flange thickness tf", 8.0, 40.0, "mm"),
                         ("Web height hw", 250.0, 1400.0, "mm"),
                         ("Web thickness tw", 5.0, 22.0, "mm")]
        self.n_vars = 4
        self.group_labels = [v[0] for v in self.var_defs]
    def _phys(self, x):
        x = np.clip(np.asarray(x, float), 0.0, 1.0)
        return [lo + xi*(hi-lo) for xi, (n, lo, hi, u) in zip(x, self.var_defs)]
    def _variables(self, vals):
        return [{"name": n, "value": float(v), "unit": u}
                for (n, lo, hi, u), v in zip(self.var_defs, vals)]
    def set_inputs(self, M_kNm=None, L_m=None, Lb_mode=None, Lb_m=None, Fy=None, Cb=None):
        if Cb:    self.Cb = min(3.0, max(1.0, float(Cb)))
        if M_kNm: self.M = max(1.0, float(M_kNm))*1.0e6
        if L_m:   self.L = max(0.5, float(L_m))*1000.0
        if Fy:    self.Fy = min(690.0, max(200.0, float(Fy)))
        if Lb_mode == "supported": self.Lb = 0.0
        elif Lb_mode == "unbraced": self.Lb = self.L
        elif Lb_mode == "custom" and Lb_m is not None:
            self.Lb = min(self.L, max(0.0, float(Lb_m)*1000.0))
        else: self.Lb = self.L
    # ---------------- AISC 360 flexure: F2 / F3 / F4 / F5, Cb = 1 ----------
    def _design(self, bf, tf, hw, tw):
        E, Fy = self.E, self.Fy
        d = hw + 2*tf
        A = 2*bf*tf + hw*tw
        Ix = bf*d**3/12.0 - (bf-tw)*hw**3/12.0
        Sx = 2.0*Ix/d
        Zx = bf*tf*(d-tf) + tw*hw*hw/4.0
        Iy = 2*tf*bf**3/12.0 + hw*tw**3/12.0
        ry = np.sqrt(Iy/A)
        J = (2*bf*tf**3 + hw*tw**3)/3.0
        h0 = d - tf
        Cw = Iy*h0*h0/4.0
        rts = np.sqrt(np.sqrt(Iy*Cw)/Sx)
        Mp = Fy*Zx; My = Fy*Sx; FL = 0.7*Fy
        # classification (Table B4.1b, built-up)
        kc = float(np.clip(4.0/np.sqrt(hw/tw), 0.35, 0.76))
        lf = bf/(2*tf); lpf = 0.38*np.sqrt(E/Fy); lrf = 0.95*np.sqrt(kc*E/FL)
        lw = hw/tw; lpw = 3.76*np.sqrt(E/Fy); lrw = 5.70*np.sqrt(E/Fy)
        fcls = "compact" if lf <= lpf else ("noncompact" if lf <= lrf else "slender")
        wcls = "compact" if lw <= lpw else ("noncompact" if lw <= lrw else "slender")
        aw = min(hw*tw/(bf*tf), 25.0)
        rt = bf/np.sqrt(12.0*(1.0 + aw/6.0))
        Lb, Cb = self.Lb, self.Cb
        lim = {}
        if wcls == "compact":                              # chapters F2 / F3
            lim["yielding (Mp)"] = Mp
            Lp = 1.76*ry*np.sqrt(E/Fy)
            g = J/(Sx*h0)
            Lr = 1.95*rts*(E/FL)*np.sqrt(g + np.sqrt(g*g + 6.76*(FL/E)**2))
            if Lb > Lp:
                if Lb <= Lr:
                    Mltb = Cb*(Mp - (Mp - FL*Sx)*(Lb-Lp)/(Lr-Lp))
                else:
                    Fcr = Cb*np.pi**2*E/(Lb/rts)**2*np.sqrt(1 + 0.078*g*(Lb/rts)**2)
                    Mltb = Fcr*Sx
                lim["lateral-torsional buckling"] = min(Mltb, Mp)
            if fcls == "noncompact":
                lim["flange local buckling"] = Mp - (Mp - FL*Sx)*(lf-lpf)/(lrf-lpf)
            elif fcls == "slender":
                lim["flange local buckling"] = 0.9*E*kc*Sx/lf**2
        elif wcls == "noncompact":                          # chapter F4
            Rpc = min(Mp/My, Mp/My - (Mp/My - 1.0)*(lw-lpw)/(lrw-lpw))
            lim["compr.-flange yielding"] = Rpc*My
            Lp = 1.1*rt*np.sqrt(E/Fy)
            g = J/(Sx*h0)
            Lr = 1.95*rt*(E/FL)*np.sqrt(g + np.sqrt(g*g + 6.76*(FL/E)**2))
            if Lb > Lp:
                if Lb <= Lr:
                    Mltb = Cb*(Rpc*My - (Rpc*My - FL*Sx)*(Lb-Lp)/(Lr-Lp))
                else:
                    Fcr = Cb*np.pi**2*E/(Lb/rt)**2*np.sqrt(1 + 0.078*g*(Lb/rt)**2)
                    Mltb = Fcr*Sx
                lim["lateral-torsional buckling"] = min(Mltb, Rpc*My)
            if fcls == "noncompact":
                lim["flange local buckling"] = Rpc*My - (Rpc*My - FL*Sx)*(lf-lpf)/(lrf-lpf)
            elif fcls == "slender":
                lim["flange local buckling"] = 0.9*E*kc*Sx/lf**2
        else:                                               # chapter F5
            Rpg = min(1.0, 1.0 - aw/(1200.0+300.0*aw)*(lw - 5.7*np.sqrt(E/Fy)))
            Rpg = max(Rpg, 0.1)
            lim["compr.-flange yielding"] = Rpg*Fy*Sx
            Lp = 1.1*rt*np.sqrt(E/Fy)
            Lr = np.pi*rt*np.sqrt(E/FL)
            if Lb > Lp:
                if Lb <= Lr:
                    Fcr = min(Fy, Cb*(Fy - 0.3*Fy*(Lb-Lp)/(Lr-Lp)))
                else:
                    Fcr = min(Fy, Cb*np.pi**2*E/(Lb/rt)**2)
                lim["lateral-torsional buckling"] = Rpg*Fcr*Sx
            if fcls == "noncompact":
                Fcr = Fy - 0.3*Fy*(lf-lpf)/(lrf-lpf)
                lim["flange local buckling"] = Rpg*Fcr*Sx
            elif fcls == "slender":
                lim["flange local buckling"] = Rpg*(0.9*E*kc/lf**2)*Sx
        gov = min(lim, key=lim.get)
        Mn = lim[gov]
        # shear, AISC G2 (unstiffened, kv = 5.34) with the G1 exception
        kv = 5.34
        if lw <= 1.10*np.sqrt(kv*E/Fy): Cv1 = 1.0
        else: Cv1 = 1.10*np.sqrt(kv*E/Fy)/lw
        Vn = 0.6*Fy*(d*tw)*Cv1
        g1 = lw <= 2.24*np.sqrt(E/Fy)
        return dict(d=d, A=A, Ix=Ix, Sx=Sx, Zx=Zx, Iy=Iy, ry=ry, J=J, Cw=Cw,
                    rts=rts, rt=rt, aw=aw, kc=kc, Mp=Mp, My=My, lim=lim,
                    gov=gov, Mn=Mn, Vn=Vn, g1=g1, lf=lf, lpf=lpf, lrf=lrf,
                    lw=lw, lpw=lpw, lrw=lrw, fcls=fcls, wcls=wcls,
                    Lp=Lp if Lb > 0 else None, Lr=Lr if Lb > 0 else None)
    def evaluate(self, x):
        bf, tf, hw, tw = self._phys(x)
        E, Fy, M, L, Lb = self.E, self.Fy, self.M, self.L, self.Lb
        D = self._design(bf, tf, hw, tw)
        asd = self.method == "ASD"
        Mcap = D["Mn"]/1.67 if asd else 0.90*D["Mn"]
        phv, omv = (1.0, 1.50) if D["g1"] else (0.90, 1.67)
        Vcap = D["Vn"]/omv if asd else phv*D["Vn"]
        V = 4.0*M/L                              # equivalent UDL: w = 8M/L^2
        w_s = (8.0*M/L**2)/(1.0 if asd else 1.5) # service-level load
        defl = 5.0*w_s*L**4/(384.0*E*D["Ix"])
        fb = M/D["Sx"]; Fb = Mcap/D["Sx"]
        cons = [
            _con(("Flexure Ma \u2264 Mn/\u03a9" if asd else "Flexure Mu \u2264 \u03c6Mn"),
                 M/1e6, Mcap/1e6, "kN\u00b7m"),
            _con(("Shear Va \u2264 Vn/\u03a9" if asd else "Shear Vu \u2264 \u03c6Vn"),
                 V/1e3, Vcap/1e3, "kN"),
            _con("Deflection \u2264 L/360", defl, L/360.0, "mm"),
            _con("Web h/tw \u2264 0.40E/Fy (F13.2)", D["lw"], 0.40*E/Fy, ""),
            _con("Web-to-flange aw \u2264 10", D["aw"], 10.0, ""),
            _con("Weldability tf \u2265 tw", tw, tf, "mm"),
        ]
        nv = sum(0 if c["ok"] else 1 for c in cons)
        mass = D["A"]*L*7850e-9
        F = lambda v, n=1: f"{v:,.{n}f}"
        lat = "laterally supported (Lb = 0)" if Lb <= 0 else f"unbraced Lb = {Lb/1e3:.2f} m, Cb = {self.Cb:.2f}"
        details = [
          ("Method", "ASD (\u03a9b = 1.67)" if asd else "LRFD (\u03c6b = 0.90)", ""),
          ("Demand M / span / bracing", f"{M/1e6:.1f} kN\u00b7m \u00b7 L = {L/1e3:.2f} m \u00b7 {lat}", ""),
          ("Section d \u00d7 bf", f"{F(D['d'],0)} \u00d7 {F(bf,0)}", "mm"),
          ("Area A", F(D["A"],0), "mm\u00b2"),
          ("Ix / Iy", f"{F(D['Ix']/1e6,1)} / {F(D['Iy']/1e6,1)}", "\u00d710\u2076 mm\u2074"),
          ("Sx / Zx", f"{F(D['Sx']/1e3,0)} / {F(D['Zx']/1e3,0)}", "\u00d710\u00b3 mm\u00b3"),
          ("ry / rts / rt", f"{F(D['ry'],1)} / {F(D['rts'],1)} / {F(D['rt'],1)}", "mm"),
          ("J / Cw", f"{F(D['J']/1e3,0)}\u00d710\u00b3 mm\u2074 / {F(D['Cw']/1e9,1)}\u00d710\u2079 mm\u2076", ""),
          ("Flange \u03bbf | \u03bbpf | \u03bbrf", f"{D['lf']:.1f} | {D['lpf']:.1f} | {D['lrf']:.1f} \u2192 {D['fcls'].upper()}", ""),
          ("Web \u03bbw | \u03bbpw | \u03bbrw", f"{D['lw']:.1f} | {D['lpw']:.1f} | {D['lrw']:.1f} \u2192 {D['wcls'].upper()}", ""),
          ("Mp / My", f"{F(D['Mp']/1e6,1)} / {F(D['My']/1e6,1)}", "kN\u00b7m"),
        ]
        if D["Lp"] is not None:
            details.append(("Lp / Lr / Lb", f"{F(D['Lp']/1e3,2)} / {F(D['Lr']/1e3,2)} / {F(Lb/1e3,2)}", "m"))
        for nmk, vv in D["lim"].items():
            details.append((f"Mn \u2014 {nmk}", F(vv/1e6,1), "kN\u00b7m"))
        details += [
          ("Governing limit state", D["gov"], ""),
          (("Fb = Mn/(\u03a9Sx)" if asd else "\u03c6Fb-equivalent"), F(Fb,1), "MPa"),
          ("Bending stress fb = M/Sx", f"{F(fb,1)}  ({fb/Fb*100:.0f}% of allowable)", "MPa"),
          ("Shear capacity " + ("Vn/\u03a9" if asd else "\u03c6Vn"), F((D['Vn']/omv if asd else phv*D['Vn'])/1e3,1), "kN"),
          ("Midspan deflection (service)", f"{F(defl,1)} vs {F(L/360.0,1)} limit", "mm"),
        ]
        return {"ok": True, "mass": float(mass), "n_viol": nv, "feasible": nv == 0,
                "variables": self._variables([bf, tf, hw, tw]),
                "constraints": cons,
                "details": [{"name": a, "value": b, "unit": c} for a, b, c in details],
                "governing": D["gov"],
                "quantities": {"steel_kg": float(mass), "area_mm2": float(D["A"])}}
    def _mass_by_role(self, ev, x):
        bf, tf, hw, tw = self._phys(x)
        return {"flanges": float(2*bf*tf*self.L*7850e-9),
                "web": float(hw*tw*self.L*7850e-9)}
    def model_3d(self, x):
        bf, tf, hw, tw = self._phys(x)
        L = self.L
        boxes = [
          {"cx": 0, "cy": hw/2 + tf, "cz": 0, "dx": L, "dy": hw, "dz": tw, "role": "steel"},
          {"cx": 0, "cy": tf/2, "cz": 0, "dx": L, "dy": tf, "dz": bf, "role": "steel"},
          {"cx": 0, "cy": hw + 1.5*tf, "cz": 0, "dx": L, "dy": tf, "dz": bf, "role": "steel"},
        ]
        return {"type": "rc", "boxes": boxes, "rebars": [], "ext": L}


class BuiltUpBeamASD(_BuiltUpIBeam):
    key = "asd_beam"; name = "Built-up I-Beam \u00b7 ASD"
    method = "ASD"
    def __init__(self):
        super().__init__()
        self.ref_mass = 312.7   # studio reference at the defaults (multi-seed GA)


class BuiltUpBeamLRFD(_BuiltUpIBeam):
    key = "lrfd_beam"; name = "Built-up I-Beam \u00b7 LRFD"
    method = "LRFD"
    def __init__(self):
        super().__init__()
        self.ref_mass = 276.7   # studio reference at the defaults (multi-seed GA)


# =============================================================================
# Registry
# =============================================================================
PROBLEM_CLASSES = [TenBar, TwentyFiveBar, SeventyTwoBar, TenMemberFrame,
                   TwentyFiveMemberFrame, SteelMRF3, TenBarFreq,
                   SeventyTwoBarFreq, SixMemberFrameFreq,
                   RCBeamCO2, RCColumnCO2, RCFootingCO2, RCFrame3CO2,
                   BuiltUpBeamASD, BuiltUpBeamLRFD]

PROBLEMS = {cls.key: cls for cls in PROBLEM_CLASSES}


META = {
    "10bar": dict(family="static", kind="Planar truss", n_vars=10,
        nodes=6, members=10, ref_mass=2299.65, unit="kg",
        constraint="Stress \u00b1172.4 MPa, displacement \u00b150.8 mm",
        blurb="The classic cantilever sizing benchmark: six nodes, two square bays, two tip loads.",
        ndm=3),
    "25bar": dict(family="static", kind="Space truss", n_vars=8,
        nodes=10, members=25, ref_mass=649.7, unit="kg",
        constraint="AISC compression, tension 240 MPa, disp 10 mm",
        blurb="Schmit\u2013Farshi transmission tower with eight symmetry groups and a code-based compression check.",
        ndm=3),
    "72bar": dict(family="static", kind="Space truss", n_vars=16,
        nodes=20, members=72, ref_mass=172.20, unit="kg",
        constraint="Stress \u00b1172.4 MPa, disp \u00b16.35 mm, 2 load cases",
        blurb="Four-storey tower, sixteen symmetry groups, two independent load cases.",
        ndm=3),
    "10frame": dict(family="static", kind="Moment frame", n_vars=10,
        nodes=9, members=10, ref_mass=3307.23, unit="kg",
        constraint="Axial+bending 165.5 MPa, drift 0.254 mm",
        blurb="Two-bay, two-storey moment frame; bending governs through the Eq.(37) section law.",
        ndm=2),
    "25frame": dict(family="static", kind="Braced frame", n_vars=25,
        nodes=16, members=25, ref_mass=9508.32, unit="kg",
        constraint="Axial+bending 165.5 MPa, drift 0.127 mm",
        blurb="Three-bay, three-storey frame with corner X-bracing; the largest static benchmark.",
        ndm=2),
    "10bar_freq": dict(family="frequency", kind="Planar truss", n_vars=10,
        nodes=6, members=10, ref_mass=2637.85, unit="kg",
        constraint="First frequency = 14 Hz",
        blurb="The 10-bar truss with 454 kg lumped masses, sized so the fundamental frequency lands on the 14 Hz target.",
        ndm=2),
    "72bar_freq": dict(family="frequency", kind="Space truss", n_vars=16,
        nodes=20, members=72, ref_mass=287.09, unit="kg",
        constraint="First frequency = 4 Hz",
        blurb="The 72-bar tower with top-mass loading; the cleanest frequency reproduction in the suite.",
        ndm=3),
    "6frame_freq": dict(family="frequency", kind="Portal frame", n_vars=6,
        nodes=6, members=6, ref_mass=4272.32, unit="kg",
        constraint="First frequency = 78.5 rad/s",
        blurb="A two-storey portal with distributed beam mass and a frequency target stated in rad/s.",
        ndm=2),
    "mrf3": dict(family="static", kind="Steel MRF \u00b7 discrete W-shapes", n_vars=2,
        nodes=12, members=15, ref_mass=8513.6, unit="kg",
        constraint="AISC-LRFD interaction, all W10 columns + W-beam catalogue",
        blurb="The canonical two-bay three-storey moment frame of Pezeshk, Camp & Chen (2000): pick one W-shape for all beams and one W10 for all columns.",
        ndm=2),
    "rc_beam": dict(family="co2", kind="RC beam \u00b7 doubly reinforced", n_vars=4, n_con=6,
        nodes=None, members=None, ref_mass=727.8, unit="kg CO\u2082",
        constraint="ACI flexure (doubly), shear, ductility, deflection",
        blurb="Simply supported RC beam with both steel layers and both dimensions in the search space, priced by a selectable steel route \u2014 after Paya-Zaforteza et al. (2009) and Camp & Huq (2013).",
        ndm=3),
    "rc_column": dict(family="co2", kind="RC column \u00b7 asymmetric faces", n_vars=4, n_con=6,
        nodes=None, members=None, ref_mass=163.0, unit="kg CO\u2082",
        constraint="P-M interaction, axial cap, slenderness, rho limits",
        blurb="RC column under compression + uniaxial bending with the steel on each face optimized independently \u2014 after de Medeiros & Kripka (2014).",
        ndm=3),
    "rc_footing": dict(family="co2", kind="RC spread footing", n_vars=5, n_con=8,
        nodes=None, members=None, ref_mass=1155.8, unit="kg CO\u2082",
        constraint="Soil bearing + ACI punching, shear, flexure",
        blurb="Concentrically loaded spread footing with structural and geotechnical limit states \u2014 after Camp & Assadollahi (2013).",
        ndm=3),
    "rc_frame3": dict(family="co2", kind="RC moment frame", n_vars=7, n_con=9,
        nodes=12, members=15, ref_mass=5301.9, unit="kg CO\u2082",
        constraint="ACI flexure/shear, P-M, slenderness, strong-col/weak-beam",
        blurb="Three-storey, two-bay RC moment frame sized for minimum embodied CO\u2082 \u2014 after Camp & Huq (2013) and Paya-Zaforteza et al. (2009).",
        ndm=2),
    "asd_beam": dict(family="member", kind="Built-up I-beam \u00b7 ASD", n_vars=4,
        n_con=6, nodes=None, members=None, ref_mass=312.7, unit="kg",
        constraint="AISC 360: F2\u2013F5 flexure, G2 shear, L/360, F13 limits",
        blurb="Welded I-section sized for minimum mass under allowable-strength design; handles compact, noncompact and slender flanges and webs, laterally supported or unbraced.",
        ndm=3),
    "lrfd_beam": dict(family="member", kind="Built-up I-beam \u00b7 LRFD", n_vars=4,
        n_con=6, nodes=None, members=None, ref_mass=276.7, unit="kg",
        constraint="AISC 360: F2\u2013F5 flexure, G2 shear, L/360, F13 limits",
        blurb="The same complete AISC flexural machinery under load-and-resistance-factor design \u2014 compare the two philosophies on identical demands.",
        ndm=3),
}
