# -*- coding: utf-8 -*-
"""Verification suite for the Structural Optimization Studio engine.

Each test pins a mechanical or numerical truth the benchmark suite relies on:
closed-form anchors, published designs, code-classification behaviour, and
end-to-end smoke of every registered problem.  Run:  python -m pytest -q
"""
import os, sys
import numpy as np
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import engine as E

FC, FY = 25.0, 420.0


# ----------------------------------------------------------- RC mechanics
def test_doubly_reinforced_matches_closed_form_when_steel_yields():
    b, d = 300.0, 540.0
    for As in np.linspace(600, 2400, 7):
        a = As*FY/(0.85*FC*b); c = a/E._beta1(FC)
        eps = 0.003*(d-c)/c
        assert eps >= FY/200000.0           # closed form valid only when yielding
        phi = 0.9 if eps >= 0.005 else 0.65 + 0.25*(eps-0.002)/0.003
        _, phiMn, _, _ = E._rc_flex_doubly(b, d, 60.0, As, 0.0, FC, FY)
        assert abs(phiMn - phi*As*FY*(d-a/2)) / (phi*As*FY*(d-a/2)) < 1e-9


def test_compression_steel_raises_capacity_and_ductility():
    m1, _, e1, _ = E._rc_flex_doubly(300, 540, 60, 2000, 226, FC, FY)
    m2, _, e2, _ = E._rc_flex_doubly(300, 540, 60, 2000, 1500, FC, FY)
    assert m2 > m1 and e2 > e1


def test_column_pure_bending_agrees_between_solvers():
    b, h, Asf = 300.0, 579.0, 895.0
    Mn_flex, _, _, _ = E._rc_flex_doubly(b, h-60, 60, Asf, Asf, FC, FY)
    Mn_pm = E._rc_Mn_at_P(b, h, Asf, Asf, FC, FY, 0.0)
    assert abs(Mn_pm - Mn_flex)/Mn_flex < 0.005


def test_column_interaction_capacity_decreases_with_eccentricity():
    caps = [E._rc_phiPn_at_e(300, 500, 800, 800, FC, FY, e) for e in (20, 100, 300, 800)]
    assert all(caps[i] > caps[i+1] for i in range(3))


# ----------------------------------------------------------- AISC 360 beam
@pytest.fixture
def beam():
    p = E.PROBLEMS["lrfd_beam"]()
    p.set_inputs(Lb_mode="supported")
    return p


def test_compact_supported_reaches_plastic_moment(beam):
    D = beam._design(300, 20, 460, 12)
    assert D["fcls"] == "compact" and D["wcls"] == "compact"
    assert abs(D["Mn"] - D["Mp"]) < 1e-6


def test_ltb_monotone_in_unbraced_length(beam):
    m = []
    for Lb in (0.0, 3500.0, 7000.0, 12000.0):
        beam.Lb = Lb
        m.append(beam._design(300, 20, 460, 12)["Mn"])
    assert all(m[i] >= m[i+1] for i in range(3)) and m[-1] < m[0]


def test_flange_and_web_classifications(beam):
    beam.Lb = 0.0
    slender_f = beam._design(440, 8, 460, 12)
    assert slender_f["fcls"] == "slender" and slender_f["Mn"] < 0.6*slender_f["Mp"]
    f4 = beam._design(300, 20, 1200, 11)
    assert f4["wcls"] == "noncompact" and f4["My"] <= f4["Mn"] + 1 <= f4["Mp"] + 2
    f5 = beam._design(300, 20, 1400, 8)
    assert f5["wcls"] == "slender" and f5["Mn"] < f5["My"]


def test_lrfd_over_asd_capacity_ratio_is_phi_times_omega():
    x = [0.4, 0.3, 0.2, 0.35]
    ca = next(c for c in E.PROBLEMS["asd_beam"]().evaluate(x)["constraints"] if "Flexure" in c["name"])
    cl = next(c for c in E.PROBLEMS["lrfd_beam"]().evaluate(x)["constraints"] if "Flexure" in c["name"])
    assert abs(cl["capacity"]/ca["capacity"] - 0.90*1.67) < 1e-6


# ----------------------------------------------------------- steel benchmarks
def test_published_mrf_design_is_feasible_and_near_active():
    p = E.PROBLEMS["mrf3"]()
    ev = p.evaluate([16/30, 12/17])        # W24x62 beams, W10x60 columns
    assert ev["feasible"] and ev["sections"]["beams"] == "W24x62"
    u = max(abs(b.get("sigma", 0))/max(abs(b.get("limit", 1)), 1e-9) for b in ev["bars"])
    assert 0.85 < u <= 1.0


def test_frequency_error_ranks_infeasible_designs_by_target_distance():
    p = E.PROBLEMS["10bar_freq"]()
    lo, hi = p.bounds
    tiny = p.evaluate([lo]*p.n_vars); big = p.evaluate([hi]*p.n_vars)
    assert tiny["freq_err"] > big["freq_err"]
    assert p.objective([lo]*p.n_vars) > p.objective([hi]*p.n_vars)


def test_steel_route_reprices_reinforcement():
    p0 = E.PROBLEMS["rc_beam"](); p1 = E.PROBLEMS["rc_beam"](); p1.set_steel_route("green")
    e0, e1 = p0.evaluate([0.6]*4), p1.evaluate([0.6]*4)
    assert e1["mass"] < e0["mass"] and e1["breakdown"]["concrete"] == e0["breakdown"]["concrete"]


# ----------------------------------------------------------- suite smoke
@pytest.mark.parametrize("key", list(E.PROBLEMS))
def test_every_problem_evaluates_and_optimizes(key):
    p = E.PROBLEMS[key]()
    lo, hi = p.bounds
    ev = p.evaluate([lo + 0.6*(hi-lo)]*p.n_vars)
    assert ev["ok"] and ev["mass"] > 0 and "n_viol" in ev
    res = E.run_ga(p, pop_size=12, n_gen=4, seed=1)
    assert len(res["history"]) == 4 and np.isfinite(res["best_obj"])
    m = p.model_3d(res["best_x"])
    assert isinstance(m, dict) and m.get("type") in ("truss", "frame", "rc")
    assert key in E.META and E.META[key]["n_vars"] == p.n_vars


# ----------------------------------------------------------- 2026-09 revisions
def test_effective_inertia_is_bounded_and_cracks_with_moment():
    Ie1, Ig, Icr, Mcr = E._rc_Ie(300, 600, 540, 60, 1500, 226, FC, 0.5*1e8)
    Ie2, _, _, _ = E._rc_Ie(300, 600, 540, 60, 1500, 226, FC, 3.0*1e8)
    assert Icr < Ig and Ie2 <= Ie1 <= Ig and Ie2 >= Icr


def test_cb_scales_ltb_and_is_capped_at_mp():
    p = E.PROBLEMS["lrfd_beam"]()
    m1 = p._design(300, 20, 460, 12)["Mn"]
    p.set_inputs(Cb=1.14); m2 = p._design(300, 20, 460, 12)["Mn"]
    p.set_inputs(Cb=3.0);  m3 = p._design(300, 20, 460, 12)["Mn"]
    assert abs(m2/m1 - 1.14) < 1e-6 and abs(m3 - p._design(300, 20, 460, 12)["Mp"]) < 1e-6


@pytest.mark.parametrize("key", list(E.PROBLEMS))
def test_every_problem_reports_carbon_total_and_breakdown(key):
    p = E.PROBLEMS[key](); lo, hi = p.bounds
    ev = p.evaluate_full([lo + 0.6*(hi-lo)]*p.n_vars)
    c = ev["carbon"]
    assert c["total"] > 0 and abs(sum(c["breakdown"].values()) - c["total"]) < 1e-6
    assert c["material"] in ("steel", "aluminium", "rebar") and c["factor"] > 0
