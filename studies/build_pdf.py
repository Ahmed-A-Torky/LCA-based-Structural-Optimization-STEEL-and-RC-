# -*- coding: utf-8 -*-
"""Build the benchmark documentation PDF: cover + one page per problem."""
import os as _os, sys as _sys
ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
_sys.path.insert(0, ROOT)
RUNS = _os.environ.get("STUDIO_RUNS", _os.path.join(ROOT, "studies", "out", "runs"))
FIGS = _os.environ.get("STUDIO_FIGS", _os.path.join(ROOT, "studies", "out", "figs"))
_os.makedirs(RUNS, exist_ok=True); _os.makedirs(FIGS, exist_ok=True)
import json, datetime
import numpy as np
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
import engine as E

W, H = A4                      # 595.27 x 841.89
M = 38                         # margin
NAVY = HexColor("#16263f"); AMBER = HexColor("#e08a1e")
TEAL = HexColor("#1a8fa0"); GREEN = HexColor("#2e9e63")
GREY = HexColor("#6c7891"); LGREY = HexColor("#aab3c5"); BG = HexColor("#f4f6fa")
FAMC = {"static": AMBER, "frequency": TEAL, "co2": GREEN}
FAML = {"static": "STATIC", "frequency": "FREQUENCY", "co2": "RC - MIN CO2"}

def SAN(t):
    """Latin-1-safe text for built-in fonts."""
    rep = {"\u03c6": "phi-", "\u03c1": "rho", "\u03c3": "sigma", "\u03c9": "omega",
           "\u0394": "Delta-", "\u2265": ">=", "\u2264": "<=", "\u2082": "2",
           "\u1d47": "(b)", "\u1d9c": "(c)", "\u1d2e": "(B)", "\u1d38": "(L)",
           "\u2014": "-", "\u2013": "-", "\u2019": "'", "\u201c": '"',
           "\u201d": '"', "\u221a": "sqrt", "\u2192": "->", "\u22c5": "\xb7"}
    for k, v in rep.items():
        t = t.replace(k, v)
    return t.encode("latin-1", "replace").decode("latin-1")

def load(key):
    return json.load(open(RUNS + f"/{key}.json"))

FIG = FIGS
KEYS = ["10bar","25bar","72bar","10frame","25frame","mrf3",
        "10bar_freq","72bar_freq","6frame_freq",
        "rc_beam","rc_column","rc_footing","rc_frame3"]
GRID_KEYS = {"72bar","25frame","72bar_freq"}   # many groups -> text grid

# -------------------------------------------------------------- page content
def kN(x): return f"{x/1e3:.1f} kN"

def props_for(key, p, d):
    rho = lambda: f"{p.rho*1e9:,.0f} kg/m3"
    if key == "10bar":
        return [("Structure", "Planar cantilever truss - 6 nodes, 10 members"),
                ("Material", f"Aluminium: E = {p.E/1e3:.2f} GPa, density {rho()}"),
                ("Stress limit", f"+/- {p.SIGMA:.2f} MPa (25 ksi), all members"),
                ("Displacement limit", f"+/- {p.DISP:.1f} mm (2 in), all free nodes"),
                ("Loads", "444.8 kN (100 kip) downward at the two free bottom nodes"),
                ("Design variables", "10 continuous member areas (one per member)"),
                ("Area bounds", f"{p.bounds[0]:.1f} - {p.bounds[1]:,.0f} mm2 (0.1 - 35 in2)"),
                ("Reference optimum", f"{p.ref_mass} kg (Sedaghati 2005)")]
    if key == "25bar":
        return [("Structure", "Space-truss transmission tower - 10 nodes, 25 members"),
                ("Symmetry groups", "8 design groups"),
                ("Material", f"E = {p.E/1e3:.0f} GPa, density {rho()}"),
                ("Tension limit", f"{p.SIGMA_T:.0f} MPa"),
                ("Compression limit", "AISC buckling formula, per group (code-based)"),
                ("Displacement limit", f"+/- {p.DISP:.1f} mm, top nodes (x and y)"),
                ("Loads", "Single case: forces at the four top nodes (max 44.5 kN)"),
                ("Area bounds", f"{p.bounds[0]:.0f} - {p.bounds[1]:,.0f} mm2"),
                ("Reference optimum", f"{p.ref_mass} kg")]
    if key == "72bar":
        return [("Structure", "Four-storey space-truss tower - 20 nodes, 72 members"),
                ("Symmetry groups", "16 design groups (4 per storey)"),
                ("Material", f"Aluminium: E = {p.E/1e3:.2f} GPa, density {rho()}"),
                ("Stress limit", f"+/- {p.SIGMA:.2f} MPa (25 ksi)"),
                ("Displacement limit", f"+/- {p.DISP:.2f} mm (0.25 in), top nodes"),
                ("Loads", "Two independent load cases on the top storey"),
                ("Area bounds", f"{p.bounds[0]:.1f} - {p.bounds[1]:,.0f} mm2"),
                ("Reference optimum", f"{p.ref_mass} kg")]
    if key == "10frame":
        return [("Structure", "Two-bay, two-storey moment frame - 9 nodes, 10 members"),
                ("Material", f"Steel: E = {p.E/1e3:.0f} GPa, density {rho()}"),
                ("Combined stress limit", f"{p.SIGMA:.2f} MPa (axial + bending)"),
                ("Drift limit", f"{p.DISP:.3f} mm at the control node"),
                ("Section law", "I(A) per Eq. (37) of Sedaghati (2005)"),
                ("Loads", "Lateral + gravity nodal set, scaled by 0.06 (see note)"),
                ("Area bounds", f"{p.bounds[0]:,.0f} - {p.bounds[1]:,.0f} mm2"),
                ("Reference optimum", f"{p.ref_mass} kg")]
    if key == "25frame":
        return [("Structure", "Three-bay, three-storey braced frame - 16 nodes, 25 members"),
                ("Material", f"Steel: E = {p.E/1e3:.0f} GPa, density {rho()}"),
                ("Combined stress limit", f"{p.SIGMA:.2f} MPa (axial + bending)"),
                ("Drift limit", f"{p.DISP:.3f} mm at the control node"),
                ("Section law", "I(A) per Eq. (37); X-braces in the corner bays"),
                ("Loads", "Gravity + lateral nodal set, scaled by 0.03 (see note)"),
                ("Area bounds", f"{p.bounds[0]:,.0f} - {p.bounds[1]:,.0f} mm2"),
                ("Reference optimum", f"{p.ref_mass} kg")]
    if key == "mrf3":
        return [("Structure", "Two-bay x 36 ft, three-storey x 10 ft steel MRF - 12 nodes, 15 members"),
                ("Material", "A36 steel: E = 29,000 ksi (199.9 GPa), Fy = 36 ksi (248.2 MPa)"),
                ("Gravity load", "w = 2.8 kip/ft (40.9 N/mm) on every beam"),
                ("Lateral loads", "5 / 5 / 2.5 kip at levels 1 / 2 / roof (windward line)"),
                ("Design checks", "AISC-LRFD H1 interaction; sway Kx (Dumonteil), Ky = 1"),
                ("2nd-order effects", "B1/B2 amplification from separate nt / lt analyses"),
                ("Design variables", "2 discrete: one W-shape for all beams (31-shape catalogue),"),
                ("", "one W10 for all columns (all 18 W10 shapes, as in the original)"),
                ("Reference optimum", "W24x62 + W10x60 = 18,769 lb = 8513.6 kg (publ. 18,792 lb)")]
    if key == "10bar_freq":
        return [("Structure", "10-bar planar truss with nonstructural masses"),
                ("Nonstructural mass", f"{p.lumped:.0f} kg lumped at each of the 4 free nodes"),
                ("Material", f"Aluminium: E = {p.E/1e3:.2f} GPa, density {rho()}"),
                ("TARGET (reference)", "f1 = 14 Hz, +/-1% band on the equality target"),
                ("Objective", "Minimum mass subject to the frequency target; infeasible"),
                ("", "designs are ranked by normalized frequency error, so the"),
                ("", "search homes in on the target itself"),
                ("Analysis", "Consistent-mass modal analysis, eigen(K, M)"),
                ("Area bounds", f"{p.bounds[0]:.1f} - {p.bounds[1]:,.0f} mm2"),
                ("Published mass", f"{p.ref_mass} kg at f1 = 14 Hz exactly (context)")]
    if key == "72bar_freq":
        return [("Structure", "72-bar tower with top-storey nonstructural masses"),
                ("Nonstructural mass", f"{p.lumped:.0f} kg lumped at each of the 4 top nodes"),
                ("Material", f"Aluminium: E = {p.E/1e3:.2f} GPa, density {rho()}"),
                ("TARGET (reference)", "f1 = 4 Hz, +/-2% band on the equality target"),
                ("Objective", "Minimum mass subject to the frequency target; infeasible"),
                ("", "designs ranked by normalized frequency error"),
                ("Analysis", "Consistent-mass modal analysis, eigen(K, M)"),
                ("Area bounds", f"{p.bounds[0]:.1f} - {p.bounds[1]:,.0f} mm2"),
                ("Published mass", f"{p.ref_mass} kg at the target (context; reproduced)")]
    if key == "6frame_freq":
        return [("Structure", "Two-storey portal frame - 6 nodes, 6 members"),
                ("Distributed mass", f"{p.dist_per_mm*1e3:.1f} kg/m on both beams"),
                ("Material", f"Steel: E = {p.E/1e3:.0f} GPa, density {rho()}"),
                ("TARGET (reference)", "omega-1 = 78.5 rad/s (12.49 Hz), +/-3% band"),
                ("Objective", "Minimum mass subject to the frequency target; infeasible"),
                ("", "designs ranked by normalized frequency error"),
                ("Section law", "I(A) per Eq. (38) of Sedaghati (2005)"),
                ("Area bounds", f"{p.bounds[0]:,.0f} - {p.bounds[1]:,.0f} mm2"),
                ("Published mass", f"{p.ref_mass} kg at the target (context)")]
    if key == "rc_beam":
        return [("Structure", f"Simply supported RC beam, span L = {p.L/1e3:.1f} m"),
                ("Loads", f"wD = {p.wD:.0f} kN/m (+ self-weight), wL = {p.wL:.0f} kN/m; U = 1.2D + 1.6L"),
                ("Materials", f"f'c = {p.fc:.0f} MPa, fy = {p.fy:.0f} MPa"),
                ("Variables (4)", "width b [250-500], depth h [400-1000] mm, AND both steel"),
                ("", "layers: As,bot [600-6000], As,top [226-3000] mm2 (226 = 2 dia-12"),
                ("", "hanger minimum). Full flexural search space."),
                ("Flexural model", "doubly-reinforced strain compatibility; compression steel"),
                ("", "stress from its strain (no yield assumption); ACI phi transition"),
                ("Constraints (6)", "phi-Mn >= Mu - phi-Vn >= Vu - rho-min - ductility eps-t >= 0.004 -"),
                ("", "live-load deflection <= L/360 - h/b <= 3"),
                ("Steel route (rebar)", "selectable: BEDEC 2.82 (default) / BF-BOF 1.99 / world-avg"),
                ("", "1.85 / EAF-scrap 0.67 / low-carbon EAF 0.36 kg CO2/kg; the"),
                ("", "optimizer prices reinforcement by the chosen route"),
                ("Reference (studio)", f"{p.ref_mass} kg CO2 at the default route - flexure exactly active")]
    if key == "rc_column":
        return [("Structure", f"Rectangular RC column, clear height lu = {p.lu/1e3:.1f} m (braced ends)"),
                ("Factored loads", f"Pu = {kN(p.Pu)}, Mu = {p.Mu/1e6:.0f} kN-m (uniaxial, fixed sense)"),
                ("Materials", f"f'c = {p.fc:.0f} MPa, fy = {p.fy:.0f} MPa"),
                ("Variables (4)", "width b [250-600], depth h [250-800] mm, AND the steel on"),
                ("", "each face independently: As,t and As,c [300-5000] mm2 -"),
                ("", "asymmetric cages are admissible since the moment sense is fixed"),
                ("Constraints (6)", "P-M interaction at e = max(Mu/Pu, e-min) - axial cap 0.80 phi-Po -"),
                ("", "slenderness k-lu/r <= 34 - h/b <= 3 - rho-total in [1%, 4%]"),
                ("Section analysis", "Strain-compatibility P-M surface with unequal face steels,"),
                ("", "bisection on the neutral axis"),
                ("Steel route (rebar)", "selectable: BEDEC 2.82 (default) / BF-BOF 1.99 / world-avg"),
                ("", "1.85 / EAF-scrap 0.67 / low-carbon EAF 0.36 kg CO2/kg; the"),
                ("", "optimizer prices reinforcement by the chosen route"),
                ("Reference (studio)", f"{p.ref_mass} kg CO2 at the default route")]
    if key == "rc_footing":
        return [("Structure", f"Spread footing under a {p.c:.0f} mm square column, Df = {p.Df/1e3:.1f} m"),
                ("Service loads", f"PD = {kN(p.PD)}, PL = {kN(p.PL)} (concentric)"),
                ("Soil", f"qa = {p.qa*1e3:.0f} kPa gross; soil 18 kN/m3, concrete 24 kN/m3"),
                ("Materials", f"f'c = {p.fc:.0f} MPa, fy = {p.fy:.0f} MPa"),
                ("Variables (5)", "B, L [1.8-4.0 m], h [0.35-1.0 m], As per direction [1500-12000 mm2]"),
                ("Constraints (8)", "bearing - punching shear - one-way shear (2) - flexure (2) - As,min (2)"),
                ("CO2 factors", "BEDEC set incl. excavation 13.16 kg/m3 (B x L x Df)"),
                ("Steel layout", "bottom mats in both directions (the full steel search space:"),
                ("", "top steel is non-structural for concentric bearing - flexural"),
                ("", "tension is at the bottom face only)"),
                ("Steel route", "selectable (BEDEC 2.82 default ... green EAF 0.36 kg CO2/kg)"),
                ("Reference (studio)", f"{p.ref_mass} kg CO2 - bearing, punching and flexure all active")]
    if key == "rc_frame3":
        return [("Structure", "Two-bay x 6 m, three-storey x 3 m RC moment frame - 12 nodes, 15 members"),
                ("Loads", f"wD = {p.wD:.0f} kN/m (+ self), wL = {p.wL:.0f} kN/m; E-lat = 25/50/75 kN"),
                ("Combinations", "1.2D + 1.6L   and   1.2D + 1.0L + 1.0E"),
                ("Materials / stiffness", f"f'c = {p.fc:.0f}, fy = {p.fy:.0f} MPa; cracked: 0.35 Ig beams, 0.70 Ig columns"),
                ("Variables (7)", "beam b, h, As-top, As-bot; column b, h, rho (grouped: all beams alike,"),
                ("", "all columns alike, as in the frame-optimization literature)"),
                ("Constraints (9)", "beam flexure (hog + sag, doubly-reinforced strain compat.),"),
                ("", "shear, rho-min, ductility eps-t >= 0.004, depth >= L/21, column P-M,"),
                ("", "sway slenderness, strong-column / weak-beam (ACI 18.7.3.2)"),
                ("Column cage", "symmetric (As/2 per face): seismic lateral load reverses, so"),
                ("", "column moments change sign - symmetry is the correct layout here"),
                ("Steel route", "selectable (BEDEC 2.82 default ... green EAF 0.36 kg CO2/kg)"),
                ("Reference (studio)", f"{p.ref_mass} kg CO2 - beam hogging and column P-M both active")]
    return []

SOURCES = {
 "10bar": "Sedaghati (2005), Int. J. Solids & Structures 42:5848-5871 - classic sizing benchmark.",
 "25bar": "Schmit & Farshi tower, as reproduced in Sedaghati (2005).",
 "72bar": "Sedaghati (2005), Int. J. Solids & Structures 42:5848-5871.",
 "10frame": "Sedaghati (2005) - frame example with the Eq. (37) section law.",
 "25frame": "Sedaghati (2005) - largest static example of the suite.",
 "mrf3": "Pezeshk, Camp & Chen (2000), J. Struct. Eng. 126(3):382-388; reproductions by Camp et al. (2005) and others.",
 "10bar_freq": "Sedaghati (2005) - frequency-constrained variant of the 10-bar truss.",
 "72bar_freq": "Sedaghati (2005) - frequency-constrained 72-bar tower.",
 "6frame_freq": "Sedaghati (2005) - portal frame with a target stated in rad/s.",
 "rc_beam": "After Paya-Zaforteza, Yepes, Hospitaler & Gonzalez-Vidosa (2009), Eng. Struct. 31; Camp & Huq (2013), Eng. Struct. 48.",
 "rc_column": "After de Medeiros & Kripka (2014), Eng. Struct. 59:185-194.",
 "rc_footing": "After Camp & Assadollahi (2013), Struct. Multidisc. Optim. 48:411-426.",
 "rc_frame3": "After Camp & Huq (2013), Eng. Struct. 48; Camp, Pezeshk & Hansson (2003); Paya-Zaforteza et al. (2009).",
}
DESC = {
 "10bar": "The most-cited truss sizing benchmark: a cantilevered two-bay planar truss whose ten member areas are sized for minimum mass under stress and displacement limits. Bending-free axial behaviour makes it the cleanest introduction to constrained structural optimization.",
 "25bar": "A transmission-tower space truss with eight symmetry-linked design groups. Tension members are checked against a fixed allowable while compression members use a code-based (AISC) buckling allowable that depends on the section, coupling the constraint set to the design itself.",
 "72bar": "A four-storey tower with 72 members in sixteen groups and two independent load cases. The active constraint set switches between displacement and stress as the design evolves, and the cached-geometry solver in the engine makes its many analyses fast.",
 "10frame": "A two-bay, two-storey moment frame in which bending governs: combined axial-plus-bending fibre stresses are checked with section properties tied to the area through the published Eq. (37) law. A very tight drift limit drives the design. Loads are applied at the verified scale (0.06) at which the published optimum is attainable - documented honestly in the app.",
 "25frame": "The largest static example: a three-bay, three-storey frame with X-braced corner bays and 25 independent member areas. Same Eq. (37) section law and combined-stress check as the 10-member frame; the brace areas interact strongly with the drift constraint. Load scale 0.03, as in the verified suite.",
 "mrf3": "The canonical discrete steel-frame benchmark: choose one W-shape for all six beams and one W10 shape for all nine columns of a two-bay, three-storey moment frame so the AISC-LRFD interaction is satisfied at minimum weight. This implementation reproduces the published optimum as feasible (beams governing at 93.6%) and correctly rejects the next-lighter beam at 106%.",
 "10bar_freq": "The 10-bar truss carrying 454 kg at each free node, redesigned so the fundamental frequency lands on the 14 Hz target. Frequency is not monotonic in member area here (area adds stiffness and mass), so the optimizer ranks designs by their frequency error - the search visibly homes in on the target band, then minimizes mass along it.",
 "72bar_freq": "The 72-bar tower with 2270 kg masses on its top nodes, sized so the fundamental frequency lands on the 4 Hz target. The cleanest frequency benchmark in the suite: the achieved frequency settles inside the target band and the mass reproduces the published ~287 kg value almost exactly.",
 "6frame_freq": "A two-storey portal frame whose beams carry distributed nonstructural mass; the target is stated in rad/s (78.5). Section properties follow the published Eq. (38) law for frames.",
 "rc_beam": "A simply supported RC beam with the full flexural search space: both section dimensions and both steel layers. Capacity comes from doubly-reinforced strain compatibility with the ACI phi transition. At the default steel route the optimizer drives top steel to its constructive (hanger) minimum - compression steel is not carbon-economical at this span - and lands flexure exactly at 100%.",
 "rc_column": "An RC column under compression plus uniaxial bending with the steel on each face optimized independently. Because the eccentricity is small (e/h ~ 0.2, compression-controlled), the optimizer correctly places MORE steel on the compression face - and total rho lands at the ACI 1% minimum. With cheap-carbon EAF rebar the optimum shifts to a smaller section with roughly 3x the steel: the search space responds to the chosen production route.",
 "rc_footing": "A concentrically loaded spread footing combining geotechnical (service bearing) and structural (ACI punching, one-way shear, flexure) limit states. At the optimum, bearing, punching and flexure are simultaneously active - a genuine multi-constraint corner.",
 "rc_frame3": "A three-storey, two-bay RC moment frame designed for minimum embodied CO2 under gravity and seismic-type lateral loading, with cracked-section analysis and the ACI strong-column/weak-beam provision enforced at every joint below the roof. Beam hogging flexure and column P-M interaction are both active at the optimum.",
}
NOTES = {
 "mrf3": "Honest modelling note: under this implementation the W10x49 column alternative sits at 99.7% utilisation - 0.3% inside the boundary - so the GA finds W24x62 + W10x49 (17,789 lb). The original studies' full-code checking puts that member just over 100%, giving their W10x60 optimum: a 0.3% margin on one member decides a 5% weight difference.",
 "10bar_freq": "Validation: an earlier optimizer ranked infeasible designs by violation count and never reached the target; with the frequency-error objective the problem is feasible. Tightening the band converges the optimal mass to the published value: 2503 kg at +/-2%, 2573 kg at +/-1%, 2611 kg at +/-0.5%, vs the published 2637.85 kg at exactly 14 Hz.",
 "10frame": "The published loads make the drift limit unattainable at full magnitude; the suite applies the verified 0.06 scale at which the published optimum is reproducible.",
 "25frame": "Loads applied at the verified 0.03 scale, consistent with the validated suite.",
}

# -------------------------------------------------------------- draw helpers
def wrap(c, text, x, y, width, size=8.6, leading=11.6, font="Helvetica", color=NAVY):
    c.setFont(font, size); c.setFillColor(color)
    words = SAN(text).split()
    line = ""
    for w_ in words:
        t = (line + " " + w_).strip()
        if c.stringWidth(t, font, size) > width:
            c.drawString(x, y, line); y -= leading; line = w_
        else:
            line = t
    if line: c.drawString(x, y, line); y -= leading
    return y

def heading(c, x, y, text, color=NAVY):
    c.setFont("Helvetica-Bold", 7.6); c.setFillColor(color)
    c.drawString(x, y, SAN(text).upper())
    c.setStrokeColor(LGREY); c.setLineWidth(0.5)
    tw = c.stringWidth(SAN(text).upper(), "Helvetica-Bold", 7.6)
    c.line(x + tw + 6, y + 2.4, x + 250, y + 2.4)
    return y - 12

def kvrows(c, x, y, rows, lw=108, vw=145, size=7.9, leading=11.4):
    for lab, val in rows:
        c.setFont("Helvetica-Bold", size); c.setFillColor(GREY)
        c.drawString(x, y, SAN(lab))
        y = wrap(c, val, x + lw, y, vw, size=size, leading=leading-1.4,
                 font="Helvetica", color=NAVY) - (leading - (leading-1.4))
        y -= 1.2
    return y

def img(c, path, x, y_top, max_w, max_h):
    im = ImageReader(path)
    iw, ih = im.getSize()
    s = min(max_w/iw, max_h/ih)
    w_, h_ = iw*s, ih*s
    c.drawImage(im, x + (max_w-w_)/2, y_top - h_, w_, h_, mask="auto")
    return y_top - h_

def metric(c, x, y, w_, label, value, accent=NAVY):
    c.setFillColor(BG); c.roundRect(x, y, w_, 40, 4, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 6.4); c.setFillColor(GREY)
    c.drawString(x+8, y+28, SAN(label).upper())
    c.setFont("Helvetica-Bold", 12.5); c.setFillColor(accent)
    c.drawString(x+8, y+11, SAN(value))

def footer(c, page):
    c.setFont("Helvetica", 7); c.setFillColor(LGREY)
    c.drawString(M, 22, "Structural Optimization Studio - Benchmark Documentation")
    c.drawRightString(W-M, 22, f"{page:02d}")

# ------------------------------------------------------------------ cover
def cover(c):
    c.setFillColor(NAVY); c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setStrokeColor(HexColor("#24364f")); c.setLineWidth(0.4)
    for gx in range(0, int(W), 28): c.line(gx, 0, gx, H)
    for gy in range(0, int(H), 28): c.line(0, gy, W, gy)
    c.setFillColor(AMBER); c.rect(M, H-150, 46, 5, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 30); c.setFillColor(HexColor("#ffffff"))
    c.drawString(M, H-195, "Structural Optimization Studio")
    c.setFont("Helvetica", 15); c.setFillColor(HexColor("#9fb0c8"))
    c.drawString(M, H-222, "Benchmark Documentation - thirteen problems, one workbench")
    y = H-280
    groups = [("STATIC - STRESS & DISPLACEMENT", AMBER,
               ["01  10-Bar Planar Truss", "02  25-Bar Space Truss", "03  72-Bar Space Truss",
                "04  10-Member Frame", "05  25-Member Frame", "06  3-Storey Steel MRF (discrete)"]),
              ("DYNAMIC - NATURAL FREQUENCY", TEAL,
               ["07  10-Bar Truss (Frequency)", "08  72-Bar Truss (Frequency)", "09  6-Member Frame (Frequency)"]),
              ("REINFORCED CONCRETE - MIN CO2", GREEN,
               ["10  RC Beam", "11  RC Column", "12  RC Spread Footing", "13  3-Storey RC Moment Frame"])]
    for title, col, items in groups:
        c.setFont("Helvetica-Bold", 9.5); c.setFillColor(col)
        c.drawString(M, y, title); y -= 17
        c.setFont("Helvetica", 10.5); c.setFillColor(HexColor("#dbe2ee"))
        for it in items:
            c.drawString(M+14, y, it); y -= 15.5
        y -= 13
    c.setFont("Helvetica", 8.6); c.setFillColor(HexColor("#8a93a3"))
    y2 = 96
    for line in ["Each page documents one benchmark: model properties, design variables and cross-sections,",
                 "constraints, and a reproducible sample optimization run (real-coded genetic algorithm with",
                 "elitism and local polish; finite-element analysis in NumPy/SciPy - no external solvers).",
                 f"Generated {datetime.date.today().strftime('%d %B %Y')} - engine and GUI: Flask + NumPy/SciPy + three.js"]:
        c.drawString(M, y2, line); y2 -= 13
    c.showPage()

# ------------------------------------------------------------- problem page
def page(c, idx, key, pageno):
    d = load(key); p = E.PROBLEMS[key]()
    meta = E.META[key]
    fam = meta["family"]; col = FAMC[fam]
    # header band
    c.setFillColor(NAVY); c.rect(M, H-92, W-2*M, 52, stroke=0, fill=1)
    c.setFillColor(col); c.rect(M, H-92, 5, 52, stroke=0, fill=1)
    c.setFont("Helvetica-Bold", 17); c.setFillColor(HexColor("#ffffff"))
    c.drawString(M+18, H-72, SAN(f"{idx:02d}   {meta['kind']}" if False else f"{idx:02d}   {SAN(p.name)}"))
    c.setFont("Helvetica", 8.4); c.setFillColor(HexColor("#9fb0c8"))
    c.drawString(M+18, H-86, SAN(meta["kind"]))
    tag = FAML[fam]
    c.setFont("Helvetica-Bold", 8)
    tw = c.stringWidth(tag, "Helvetica-Bold", 8)
    c.setFillColor(col); c.roundRect(W-M-tw-26, H-70, tw+16, 16, 8, stroke=0, fill=1)
    c.setFillColor(NAVY); c.drawString(W-M-tw-18, H-65.5, tag)
    # source + description
    y = H-104
    c.setFont("Helvetica-Oblique", 7.6); c.setFillColor(GREY)
    c.drawString(M, y, SAN("Source: " + SOURCES[key])); y -= 13
    y = wrap(c, DESC[key], M, y, W-2*M, size=8.8, leading=12) - 6
    col_top = y
    # left column: properties
    yl = heading(c, M, col_top, "Model properties")
    yl = kvrows(c, M, yl, props_for(key, p, d))
    if key in NOTES:
        yl -= 3
        c.setFillColor(HexColor("#fdf3e3"))
        nh = 52 if key in ("mrf3", "10bar_freq") else 40
        c.roundRect(M, yl-nh+8, 253, nh, 4, stroke=0, fill=1)
        yn = yl - 3
        c.setFont("Helvetica-Bold", 7); c.setFillColor(AMBER)
        yn = wrap(c, NOTES[key], M+7, yn, 240, size=6.9, leading=8.8,
                  font="Helvetica", color=HexColor("#7a5210")) - 2
        yl = yn - 4
    # right column: figures
    xr = M + 268; wr = W - M - xr
    yr = heading(c, xr, col_top, "Geometry & loading")
    yr = img(c, f"{FIG}/{key}_geom.png", xr, yr, wr, 168) - 14
    yr = heading(c, xr, yr, "Optimized cross-sections")
    if key in GRID_KEYS:
        areas = list(np.atleast_1d(d["best_x"]))
        labels = p.group_labels
        c.setFont("Helvetica", 7.2); c.setFillColor(NAVY)
        ncol = 2; rows_per = int(np.ceil(len(areas)/ncol))
        for k2, (lab, a) in enumerate(zip(labels, areas)):
            cx = xr + (k2 // rows_per)*(wr/2)
            cy = yr - (k2 % rows_per)*10.4
            c.setFillColor(GREY); c.drawString(cx, cy, SAN(str(lab))[:18])
            c.setFillColor(NAVY)
            c.drawRightString(cx + wr/2 - 14, cy, f"{a/100:.1f} cm2")
        yr -= rows_per*10.4 + 6
    else:
        yr = img(c, f"{FIG}/{key}_xsec.png", xr, yr, wr, 170) - 8
    # bottom: sample run
    yb = min(yl, yr) - 8
    c.setStrokeColor(LGREY); c.setLineWidth(0.6); c.line(M, yb, W-M, yb)
    yb -= 14
    c.setFont("Helvetica-Bold", 8.4); c.setFillColor(NAVY)
    c.drawString(M, yb, "SAMPLE OPTIMIZATION RUN")
    c.setFont("Helvetica", 7.6); c.setFillColor(GREY)
    c.drawRightString(W-M, yb, SAN(
        f"GA: population {d['pop']} x {d['gen']} generations - seed {d['seed']} - "
        f"{d['evaluations']:,} evaluations - {d['time_s']:.0f} s"))
    yb -= 50
    unit = meta["unit"]
    delta = (d["mass"]-d["ref"])/d["ref"]*100 if d["ref"] else 0
    bw = (W-2*M-3*8)/4
    feas = d["feasible"]
    ftgt = d.get("freq_target")
    if ftgt:
        fr = d["eval"].get("freqs") or []
        f1 = fr[ftgt["mode"]-1] if len(fr) >= ftgt["mode"] else None
        metric(c, M, yb, bw, f"Achieved f{ftgt['mode']}",
               SAN(f"{f1:.2f} {ftgt['unit']}") if f1 else "-", GREEN if feas else AMBER)
        metric(c, M+bw+8, yb, bw, "Target (reference)",
               SAN(f"{ftgt['value']} {ftgt['unit']} +/-{ftgt['tol']*100:.0f}%"), AMBER)
        metric(c, M+2*(bw+8), yb, bw, "Optimized mass",
               SAN(f"{d['mass']:,.1f} kg"), col)
        metric(c, M+3*(bw+8), yb, bw, "On target",
               "YES" if feas else "NOT YET", GREEN if feas else AMBER)
    else:
        objlab = "Optimized objective" if feas else "Best attempt (infeasible)"
        metric(c, M, yb, bw, objlab, SAN(f"{d['mass']:,.1f} {unit}"), col if feas else GREY)
        metric(c, M+bw+8, yb, bw, "Reference", SAN(f"{d['ref']:,.1f} {unit}"))
        metric(c, M+2*(bw+8), yb, bw, "Delta vs reference",
               f"{delta:+.1f}%" if feas else "n/a",
               GREEN if (feas and delta <= 0.5) else NAVY)
        metric(c, M+3*(bw+8), yb, bw, "Feasible",
               "YES" if feas else "NO (by design)", GREEN if feas else AMBER)
    yb -= 14
    # governing info line
    gov = ""
    ev = d["eval"]
    if "constraints" in ev and ev["constraints"]:
        g = max(ev["constraints"], key=lambda x: x["util"])
        gov = f"Governing constraint: {g['name']} at {g['util']*100:.0f}% utilisation."
    elif "bars" in ev and ev["bars"] and ev["bars"][0].get("limit") is not None \
            and ev["bars"][0].get("sigma") is not None:
        g = max(ev["bars"], key=lambda x: abs(x.get("sigma", 0))/max(abs(x.get("limit", 1)) or 1, 1e-9))
        u = abs(g.get("sigma", 0))/max(abs(g.get("limit", 1)) or 1, 1e-9)*100
        role = f" ({g['role']})" if g.get("role") else ""
        du = (ev["max_disp"]/ev["disp_limit"]*100) if ev.get("max_disp") is not None else 0
        if du >= u and du > 95:
            gov = (f"Governing: displacement at {du:.0f}% of its limit "
                   f"({ev['max_disp']:.3f} / {ev['disp_limit']:.3f} mm); "
                   f"peak member utilisation {u:.0f}% (member #{g['id']}).")
        else:
            gov = f"Governing member: #{g['id']}{role} at {u:.0f}% of its limit."
    if "targets" in ev and ev.get("targets"):
        ts = [t for t in ev["targets"] if t.get("value") is not None]
        if ts:
            gov += "  " + "; ".join(f"f{t['mode']} = {t['value']:.2f} {ev.get('unit','Hz')}" for t in ts)
        if d.get("freq_target"):
            gov += (f".  Mass minimized along the target band: {d['mass']:,.1f} kg "
                    f"(published minimum-mass for context: {d['ref']:,.1f} kg, {delta:+.1f}%)")
    if "sections" in ev and ev.get("sections"):
        gov += "  Selected sections: " + ", ".join(f"{k}: {v}" for k, v in ev["sections"].items()) + "."
    if gov:
        c.setFont("Helvetica", 7.8); c.setFillColor(NAVY)
        c.drawString(M, yb, SAN(gov)[:150]); yb -= 12
    RUN_NOTES = {
      "rc_column": "Note: the asymmetric optimum beats the best symmetric cage (163.0 vs 171.0 kg CO2, -4.7%). Selecting the green-EAF route (0.36 kg/kg) drops the optimum to ~82 kg CO2 with ~3x more steel and a smaller section - the optimizer trades materials by carbon price.",
      "rc_beam": "Note: with cheap-carbon rebar routes the optimum shifts toward more steel and a shallower section; the reference above is calibrated at the default BEDEC route for like-for-like comparison.",
      "72bar": "Note: three independent 30,000-evaluation runs plateau at ~250 kg with the displacement limit exactly active - the implemented checks (both load cases, all top-node DOFs) bind harder than the classic 172.2 kg interpretation.",
      "25bar": "Note: lighter-than-published designs are feasible under the implemented checks; documented in the app.",
      "25frame": "Note: lighter-than-published designs are feasible under the implemented checks at this load scale; documented in the app.",
    }
    if key in RUN_NOTES:
        c.setFont("Helvetica-Oblique", 6.9); c.setFillColor(GREY)
        yb = wrap(c, RUN_NOTES[key], M, yb, W-2*M, size=6.9, leading=8.6,
                  font="Helvetica-Oblique", color=GREY) - 4
    # convergence + design values
    yc = heading(c, M, yb, "Frequency convergence (vs target)" if d.get("freq_target") else "Convergence")
    img(c, f"{FIG}/{key}_conv.png", M, yc, 250, yc-34)
    xv = M+268
    yv = heading(c, xv, yb, "Optimized design values")
    vals = []
    if "variables" in ev and ev.get("variables"):
        def fmtv(x):
            return f"{x:,.0f}" if abs(x) >= 100 else (f"{x:.1f}" if abs(x) >= 1 else f"{x:.3f}")
        vals = [(v["name"], f"{fmtv(v['value'])} {v.get('unit','')}") for v in ev["variables"]]
    elif key == "mrf3":
        vals = [("All 6 beams", ev["sections"]["beams"]),
                ("All 9 columns", ev["sections"]["columns"]),
                ("Total weight", f"{ev['weight_lb']:,.0f} lb")]
    else:
        vals = [("Member areas", "see chart / grid above"),
                ("Mass", f"{d['mass']:,.1f} {unit}")]
        if ev.get("max_disp") is not None:
            vals.append(("Max displacement", f"{ev['max_disp']:.3f} / {ev['disp_limit']:.3f} mm"))
        if ev.get("freqs"):
            vals.append(("First frequencies", ", ".join(f"{f:.2f}" for f in ev["freqs"][:3])))
    if "breakdown" in ev and ev.get("breakdown"):
        bk = ev["breakdown"]
        vals.append(("CO2 by source", " - ".join(f"{k} {v:.0f}" for k, v in bk.items())))
    if ev.get("steel_route"):
        vals.append(("Steel route", f"{ev['steel_route']} ({ev['steel_co2_factor']:.2f} kg CO2/kg)"))
    kvrows(c, xv, yv, vals[:8], lw=112, vw=145, size=7.4, leading=10.2)
    footer(c, pageno)
    c.showPage()

# ------------------------------------------------------------------ build
c = canvas.Canvas(_os.path.join(ROOT, "studies", "out", "Structural_Optimization_Benchmarks.pdf"),
                  pagesize=A4)
c.setTitle("Structural Optimization Studio - Benchmark Documentation")
c.setAuthor("Structural Optimization Studio")
cover(c)
for i, key in enumerate(KEYS, start=1):
    page(c, i, key, i+1)
c.save()
print("PDF built: 14 pages")
