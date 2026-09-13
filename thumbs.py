# -*- coding: utf-8 -*-
"""
thumbs.py -- generate schematic SVG thumbnails from real problem geometry.

Each thumbnail is a projected wireframe of the structure, drawn into a
viewBox so it scales cleanly inside the card. Trusses in 3D get an
isometric projection; 2D problems are drawn directly.
"""
import numpy as np
import engine as E


def _project(nodes, ndm):
    """Return {nid:(px,py)} 2D screen coords (y-down) for drawing."""
    pts = {}
    if ndm == 2:
        for nid, c in nodes.items():
            pts[nid] = (c[0], -c[1])     # flip y so up is up
    else:
        # simple isometric: screen_x = x - z*0.5 ... use (x,y,z)
        # rotate for a pleasing 3/4 view
        ax, ay = np.radians(24), np.radians(32)
        for nid, c in nodes.items():
            x, y, z = c
            # rotate about vertical then tilt
            xr = x * np.cos(ay) + y * np.sin(ay)
            yr = -x * np.sin(ay) + y * np.cos(ay)
            sx = xr
            sy = z * np.cos(ax) - yr * np.sin(ax)
            pts[nid] = (sx, -sy)
    return pts


def build_thumb(key):
    if key in _RC_THUMBS:
        return _RC_THUMBS[key]()
    p = E.PROBLEMS[key]()
    ndm = p.ndm
    pts = _project(p.nodes, ndm)
    xs = [v[0] for v in pts.values()]; ys = [v[1] for v in pts.values()]
    minx, maxx = min(xs), max(xs); miny, maxy = min(ys), max(ys)
    w = maxx - minx or 1; h = maxy - miny or 1
    pad = 0.12 * max(w, h)
    minx -= pad; miny -= pad; w += 2*pad; h += 2*pad
    # target viewBox 340 x 188 (matches .thumb)
    VW, VH = 340.0, 188.0
    sc = min(VW / w, VH / h)
    ox = (VW - w*sc) / 2 - minx*sc
    oy = (VH - h*sc) / 2 - miny*sc

    def X(nid): return pts[nid][0]*sc + ox
    def Y(nid): return pts[nid][1]*sc + oy

    is_freq = p.family == "frequency"
    member_col = "#46c8d6" if is_freq else "#f4a43c"
    pass  # (member operator unused)

    lines = []
    # members
    if p.kind == "truss":
        elems = [(e, i, j) for (e, i, j, g) in p.elements]
    else:
        elems = [(e, i, j) for (e, i, j, g, r) in p.elements]
    for (e, i, j) in elems:
        lines.append(
            f'<line x1="{X(i):.1f}" y1="{Y(i):.1f}" x2="{X(j):.1f}" y2="{Y(j):.1f}" '
            f'stroke="{member_col}" stroke-width="1.6" stroke-opacity="0.85" stroke-linecap="round"/>'
        )
    # mass nodes (frequency problems)
    mass_nodes = set(getattr(p, "mass_nodes", ()))
    dist_elems = set(getattr(p, "dist_elems", ()))
    # distributed-mass beams highlighted
    if dist_elems:
        for (e, i, j, g, r) in p.elements:
            if e in dist_elems:
                lines.append(
                    f'<line x1="{X(i):.1f}" y1="{Y(i):.1f}" x2="{X(j):.1f}" y2="{Y(j):.1f}" '
                    f'stroke="#46c8d6" stroke-width="4.2" stroke-opacity="0.35" stroke-linecap="round"/>'
                )
    # nodes
    dots = []
    for nid in p.nodes:
        fixed = nid in p.fixed
        if nid in mass_nodes:
            dots.append(f'<circle cx="{X(nid):.1f}" cy="{Y(nid):.1f}" r="4.6" fill="#46c8d6"/>')
            dots.append(f'<circle cx="{X(nid):.1f}" cy="{Y(nid):.1f}" r="8" fill="none" stroke="#46c8d6" stroke-opacity="0.4"/>')
        elif fixed:
            dots.append(f'<rect x="{X(nid)-3.5:.1f}" y="{Y(nid)-3.5:.1f}" width="7" height="7" fill="#64758f"/>')
        else:
            dots.append(f'<circle cx="{X(nid):.1f}" cy="{Y(nid):.1f}" r="2.6" fill="#9fb0c8"/>')

    svg = (
        f'<svg viewBox="0 0 {VW:.0f} {VH:.0f}" preserveAspectRatio="xMidYMid meet" '
        f'xmlns="http://www.w3.org/2000/svg">'
        + "".join(lines) + "".join(dots) +
        '</svg>'
    )
    return svg


# -----------------------------------------------------------------------------
# Custom schematic thumbnails for the reinforced-concrete CO2 problems
# -----------------------------------------------------------------------------
GREEN = "#5ec98a"; CONC = "#9fb0c8"; REBAR = "#e8746a"; DIM = "#64758f"

def _svg(body):
    return ('<svg viewBox="0 0 340 188" preserveAspectRatio="xMidYMid meet" '
            'xmlns="http://www.w3.org/2000/svg">' + body + '</svg>')

def _thumb_rc_beam():
    b = []
    # beam body
    b.append(f'<rect x="50" y="84" width="240" height="34" rx="2" fill="none" '
             f'stroke="{CONC}" stroke-width="2"/>')
    # rebar (tension bottom, dashed) + stirrups
    b.append(f'<line x1="58" y1="112" x2="282" y2="112" stroke="{REBAR}" '
             f'stroke-width="2.4" stroke-dasharray="1 0"/>')
    for k in range(9):
        x = 64 + k * 26.5
        b.append(f'<rect x="{x}" y="88" width="6" height="26" rx="2" fill="none" '
                 f'stroke="{GREEN}" stroke-width="1.1" stroke-opacity="0.65"/>')
    # supports
    b.append(f'<path d="M50 118 l-9 14 h18 Z" fill="{DIM}"/>')
    b.append(f'<circle cx="290" cy="126" r="7" fill="none" stroke="{DIM}" stroke-width="2"/>')
    b.append(f'<line x1="276" y1="134" x2="304" y2="134" stroke="{DIM}" stroke-width="2"/>')
    # UDL arrows
    b.append(f'<line x1="50" y1="56" x2="290" y2="56" stroke="{GREEN}" stroke-width="1.6"/>')
    for k in range(9):
        x = 58 + k * 29
        b.append(f'<line x1="{x}" y1="56" x2="{x}" y2="78" stroke="{GREEN}" stroke-width="1.6"/>')
        b.append(f'<path d="M{x} 82 l-3.6 -7 h7.2 Z" fill="{GREEN}"/>')
    b.append(f'<text x="170" y="46" font-family="monospace" font-size="11" '
             f'fill="{GREEN}" text-anchor="middle">w = D + L</text>')
    b.append(f'<text x="170" y="156" font-family="monospace" font-size="10" '
             f'fill="{DIM}" text-anchor="middle">min CO2 : b, h, As</text>')
    return _svg("".join(b))

def _thumb_rc_column():
    b = []
    # column body + footing line
    b.append(f'<rect x="148" y="40" width="44" height="116" rx="2" fill="none" '
             f'stroke="{CONC}" stroke-width="2"/>')
    b.append(f'<line x1="120" y1="156" x2="220" y2="156" stroke="{DIM}" stroke-width="2.4"/>')
    # longitudinal bars
    for x in (156, 184):
        b.append(f'<line x1="{x}" y1="46" x2="{x}" y2="152" stroke="{REBAR}" stroke-width="2.2"/>')
    # ties
    for k in range(6):
        y = 52 + k * 19
        b.append(f'<rect x="153" y="{y}" width="34" height="5" rx="2" fill="none" '
                 f'stroke="{GREEN}" stroke-width="1.1" stroke-opacity="0.7"/>')
    # axial load arrow
    b.append(f'<line x1="170" y1="8" x2="170" y2="32" stroke="{GREEN}" stroke-width="2.4"/>')
    b.append(f'<path d="M170 38 l-5 -9 h10 Z" fill="{GREEN}"/>')
    b.append(f'<text x="180" y="20" font-family="monospace" font-size="11" fill="{GREEN}">Pu</text>')
    # moment arc
    b.append(f'<path d="M 210 60 a 22 22 0 1 1 -8 -28" fill="none" stroke="{GREEN}" '
             f'stroke-width="2"/>')
    b.append(f'<path d="M200 30 l9 -1 -4 8 Z" fill="{GREEN}"/>')
    b.append(f'<text x="226" y="52" font-family="monospace" font-size="11" fill="{GREEN}">Mu</text>')
    b.append(f'<text x="92" y="100" font-family="monospace" font-size="10" fill="{DIM}">b\u00d7h, \u03c1</text>')
    return _svg("".join(b))

def _thumb_rc_footing():
    b = []
    # ground line + hatch
    b.append(f'<line x1="20" y1="52" x2="320" y2="52" stroke="{DIM}" stroke-width="1.6"/>')
    for k in range(15):
        x = 26 + k * 20
        b.append(f'<line x1="{x}" y1="52" x2="{x-8}" y2="44" stroke="{DIM}" stroke-width="1" stroke-opacity="0.7"/>')
    # column stub
    b.append(f'<rect x="156" y="52" width="28" height="46" fill="none" stroke="{CONC}" stroke-width="2"/>')
    # footing slab
    b.append(f'<rect x="84" y="98" width="172" height="34" rx="2" fill="none" stroke="{CONC}" stroke-width="2.2"/>')
    # rebar mat
    b.append(f'<line x1="92" y1="126" x2="248" y2="126" stroke="{REBAR}" stroke-width="2.4"/>')
    for k in range(8):
        x = 100 + k * 20
        b.append(f'<circle cx="{x}" cy="121" r="2.4" fill="{REBAR}"/>')
    # soil pressure arrows (upward)
    for k in range(7):
        x = 96 + k * 25
        b.append(f'<line x1="{x}" y1="166" x2="{x}" y2="142" stroke="{GREEN}" stroke-width="1.6"/>')
        b.append(f'<path d="M{x} 138 l-3.6 7 h7.2 Z" fill="{GREEN}"/>')
    b.append(f'<line x1="96" y1="166" x2="246" y2="166" stroke="{GREEN}" stroke-width="1.4"/>')
    # load arrow on column
    b.append(f'<line x1="170" y1="14" x2="170" y2="42" stroke="{GREEN}" stroke-width="2.4"/>')
    b.append(f'<path d="M170 48 l-5 -9 h10 Z" fill="{GREEN}"/>')
    b.append(f'<text x="180" y="26" font-family="monospace" font-size="11" fill="{GREEN}">P</text>')
    b.append(f'<text x="262" y="120" font-family="monospace" font-size="10" fill="{DIM}">q \u2264 qa</text>')
    return _svg("".join(b))

_RC_THUMBS = {"rc_beam": _thumb_rc_beam, "rc_column": _thumb_rc_column,
              "rc_footing": _thumb_rc_footing}

def _thumb_rc_frame3():
    b = []
    x0, y0 = 70, 152          # base line
    bw, sh = 100, 38          # bay width, storey height px
    # columns (double-line concrete look)
    for c in range(3):
        x = x0 + c*bw
        b.append(f'<rect x="{x-5}" y="{y0-3*sh}" width="10" height="{3*sh}" fill="none" stroke="{CONC}" stroke-width="1.8"/>')
    # beams
    for lvl in range(1, 4):
        y = y0 - lvl*sh
        b.append(f'<rect x="{x0-5}" y="{y-4}" width="{2*bw+10}" height="8" fill="none" stroke="{CONC}" stroke-width="1.8"/>')
        b.append(f'<line x1="{x0+2}" y1="{y+2}" x2="{x0+2*bw-2}" y2="{y+2}" stroke="{REBAR}" stroke-width="1.6"/>')
    # base
    b.append(f'<line x1="{x0-26}" y1="{y0}" x2="{x0+2*bw+26}" y2="{y0}" stroke="{DIM}" stroke-width="2.2"/>')
    for k in range(10):
        xx = x0-22 + k*25
        b.append(f'<line x1="{xx}" y1="{y0}" x2="{xx-7}" y2="{y0+7}" stroke="{DIM}" stroke-width="1" stroke-opacity="0.7"/>')
    # gravity UDL arrows on roof
    yT = y0 - 3*sh
    for k in range(7):
        xx = x0 + 12 + k*29
        b.append(f'<line x1="{xx}" y1="{yT-20}" x2="{xx}" y2="{yT-8}" stroke="{GREEN}" stroke-width="1.4"/>')
        b.append(f'<path d="M{xx} {yT-5} l-3 -6 h6 Z" fill="{GREEN}"/>')
    b.append(f'<line x1="{x0+10}" y1="{yT-20}" x2="{x0+2*bw-10}" y2="{yT-20}" stroke="{GREEN}" stroke-width="1.2"/>')
    # lateral load arrows (seismic-type, increasing with height)
    for lvl, ln in ((1,12),(2,18),(3,24)):
        y = y0 - lvl*sh
        b.append(f'<line x1="{x0-14-ln}" y1="{y}" x2="{x0-12}" y2="{y}" stroke="{GREEN}" stroke-width="2"/>')
        b.append(f'<path d="M{x0-7} {y} l-8 -4 v8 Z" fill="{GREEN}"/>')
    b.append(f'<text x="{x0+2*bw+8}" y="{y0-3*sh+14}" font-family="monospace" font-size="10" fill="{DIM}">SCWB</text>')
    b.append(f'<text x="170" y="178" font-family="monospace" font-size="10" fill="{DIM}" text-anchor="middle">min CO2 : beams + columns + steel</text>')
    return _svg("".join(b))

_RC_THUMBS["rc_frame3"] = _thumb_rc_frame3


def _thumb_ibeam(tag):
    b = []
    # elevation with UDL
    b.append('<rect x="40" y="96" width="200" height="16" fill="none" stroke="#9fb0c8" stroke-width="2"/>')
    for k in range(8):
        x = 48 + k*26
        b.append(f'<line x1="{x}" y1="66" x2="{x}" y2="86" stroke="#f4a43c" stroke-width="1.4"/>')
        b.append(f'<path d="M{x} 92 l-3 -6 h6 Z" fill="#f4a43c"/>')
    b.append('<line x1="46" y1="66" x2="234" y2="66" stroke="#f4a43c" stroke-width="1.2"/>')
    b.append(f'<path d="M40 118 l-8 12 h16 Z" fill="none" stroke="{DIM}" stroke-width="1.4"/>')
    b.append(f'<circle cx="240" cy="124" r="6" fill="none" stroke="{DIM}" stroke-width="1.4"/>')
    # I cross-section
    for y in (150, 186):
        b.append(f'<rect x="86" y="{y}" width="60" height="7" fill="#9fb0c8"/>')
    b.append('<rect x="112" y="157" width="8" height="29" fill="#9fb0c8"/>')
    b.append(f'<text x="196" y="176" font-family="monospace" font-size="13" fill="#f4a43c" font-weight="bold">{tag}</text>')
    b.append(f'<text x="140" y="52" font-family="monospace" font-size="10" fill="{DIM}" text-anchor="middle">built-up I \u00b7 F2\u2013F5 \u00b7 min mass</text>')
    return _svg("".join(b))

_RC_THUMBS["asd_beam"] = lambda: _thumb_ibeam("ASD")
_RC_THUMBS["lrfd_beam"] = lambda: _thumb_ibeam("LRFD")
