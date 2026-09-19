# -*- coding: utf-8 -*-
"""
app.py -- Flask server for the structural-optimization GUI.

Routes
------
GET  /                       landing page (problem thumbnails)
GET  /problem/<key>          problem workspace
GET  /api/problems           metadata for all problems
GET  /api/problem/<key>      metadata + base geometry for one problem
POST /api/optimize/<key>     start an optimization job (GA params in body)
GET  /api/progress/<job>     poll progress of a running job
POST /api/cancel/<job>       cancel a running job
GET  /api/result/<job>       full result payload once finished
"""
import threading
import uuid
import time
from flask import Flask, jsonify, request, render_template, abort

import os

import engine as E
import thumbs

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Embedding support.
# To embed this app inside another site (e.g. a Wix page via an iframe),
# set the environment variable EMBED_ALLOW to the site that is allowed to
# frame it, for example:
#     EMBED_ALLOW="https://www.your-wix-site.com"
# Leave it unset to keep the default (only same-origin framing).
# Set EMBED_ALLOW="*" to allow any site to frame it (simplest, least strict).
# ---------------------------------------------------------------------------
EMBED_ALLOW = os.environ.get("EMBED_ALLOW", "").strip()


@app.after_request
def _allow_embedding(resp):
    if EMBED_ALLOW == "*":
        # Allow framing from anywhere; do not send X-Frame-Options.
        resp.headers["Content-Security-Policy"] = "frame-ancestors *;"
    elif EMBED_ALLOW:
        resp.headers["Content-Security-Policy"] = f"frame-ancestors 'self' {EMBED_ALLOW};"
        resp.headers.pop("X-Frame-Options", None)
    return resp

# In-memory job store: job_id -> dict(status, gen, n_gen, best_obj, ...)
JOBS = {}
JOBS_LOCK = threading.Lock()


def _meta_list():
    out = []
    order = ["10bar", "25bar", "72bar", "10frame", "25frame", "mrf3",
             "10bar_freq", "72bar_freq", "6frame_freq",
             "rc_beam", "rc_column", "rc_footing", "rc_frame3", "asd_beam", "lrfd_beam"]
    for k in order:
        m = dict(E.META[k]); m["key"] = k
        m["name"] = E.PROBLEMS[k].name
        m["thumb"] = thumbs.build_thumb(k)
        out.append(m)
    return out


@app.route("/")
def index():
    return render_template("index.html", problems=_meta_list())


@app.route("/problem/<key>")
def problem_page(key):
    if key not in E.PROBLEMS:
        abort(404)
    m = dict(E.META[key]); m["key"] = key
    m["name"] = E.PROBLEMS[key].name
    p0 = E.PROBLEMS[key]()
    routes = E.routes_for(p0.material)
    m["material"] = p0.material
    metal_ok = m.get("family") in ("static", "frequency") and key != "mrf3"
    return render_template("problem.html", meta=m, steel_routes=routes,
                           default_route=p0.steel_route,
                           materials=(E.MATERIALS if metal_ok else None))


@app.route("/api/problems")
def api_problems():
    return jsonify(_meta_list())


@app.route("/api/problem/<key>")
def api_problem(key):
    if key not in E.PROBLEMS:
        abort(404)
    p = E.PROBLEMS[key]()
    m = dict(E.META[key]); m["key"] = key; m["name"] = p.name
    m["bounds"] = list(p.bounds)
    m["n_vars"] = p.n_vars
    m["group_labels"] = p.group_labels
    # base model at mid-bounds, just for an initial view
    mid = [(p.bounds[0] + p.bounds[1]) / 2] * p.n_vars
    m["base_model"] = p.model_3d(mid)
    return jsonify(m)


def _run_job(job_id, key, params):
    p = E.PROBLEMS[key]()
    if params.get("material"):
        p.set_material(str(params["material"]))
    if hasattr(p, "set_steel_route") and params.get("steel_route"):
        p.set_steel_route(str(params["steel_route"]))
    di = params.get("design") or {}
    if di and hasattr(p, "set_inputs"):
        try:
            p.set_inputs(M_kNm=di.get("M_kNm"), L_m=di.get("L_m"),
                         Lb_mode=di.get("Lb_mode"), Lb_m=di.get("Lb_m"),
                         Fy=di.get("Fy"), Cb=di.get("Cb"))
        except Exception:
            pass

    def progress(gen, best_obj, feasible, best_f1=None):
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if not j:
                return
            j["gen"] = gen
            j["best_obj"] = None if not feasible else float(best_obj)
            j["best_feasible"] = bool(feasible)
            if best_f1 is not None:
                j["best_f1"] = float(best_f1)
                j.setdefault("freq_history", []).append(float(best_f1))

    def should_stop():
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            return (not j) or j.get("cancel", False)

    try:
        res = E.run_ga(
            p,
            pop_size=int(params.get("pop_size", 80)),
            n_gen=int(params.get("n_gen", 80)),
            mutation=float(params.get("mutation", 0.15)),
            crossover=float(params.get("crossover", 0.7)),
            elite_frac=float(params.get("elite_frac", 0.04)),
            seed=params.get("seed"),
            progress=progress,
            should_stop=should_stop,
        )
        best_x = res["best_x"]
        ev = p.evaluate_full(best_x)
        model = p.model_3d(best_x)
        freq_target = None
        if getattr(p, "targets", None) and hasattr(p, "eqtol"):
            mode, tgt, sense = p.targets[0]
            freq_target = {"mode": mode, "value": tgt, "sense": sense,
                           "tol": p.eqtol, "unit": ev.get("unit", "Hz")}
        result = {
            "best_x": best_x,
            "best_obj": res["best_obj"],
            "feasible": res["feasible"],
            "history": res["history"],
            "history_feasible": res["history_feasible"],
            "freq_history": res.get("freq_history"),
            "scatter": list(getattr(p, "archive", []) or []),
            "material": getattr(p, "material_choice", "benchmark"),
            "freq_target": freq_target,
            "evaluations": res["evaluations"],
            "evaluation": ev,
            "model": model,
            "ref_mass": p.ref_mass,
            "group_labels": p.group_labels,
            "meta": {**E.META[key], "key": key, "name": p.name},
        }
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j:
                j["status"] = "cancelled" if j.get("cancel") else "done"
                j["result"] = result
    except Exception as exc:  # pragma: no cover
        import traceback
        traceback.print_exc()
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j:
                j["status"] = "error"
                j["error"] = str(exc)


@app.route("/api/optimize/<key>", methods=["POST"])
def api_optimize(key):
    if key not in E.PROBLEMS:
        abort(404)
    params = request.get_json(force=True, silent=True) or {}
    # clamp params to sane ranges to protect the server
    params["pop_size"] = max(8, min(400, int(params.get("pop_size", 80))))
    params["n_gen"] = max(5, min(600, int(params.get("n_gen", 80))))

    # Protect a public deployment: cap simultaneous running jobs and drop
    # finished jobs older than ~30 min so memory does not grow unbounded.
    MAX_RUNNING = int(os.environ.get("MAX_RUNNING_JOBS", "6"))
    now = time.time()
    with JOBS_LOCK:
        for jid in [j for j, v in JOBS.items()
                    if v.get("status") != "running" and now - v.get("started", now) > 1800]:
            JOBS.pop(jid, None)
        running = sum(1 for v in JOBS.values() if v.get("status") == "running")
        if running >= MAX_RUNNING:
            return jsonify({"error": "The server is busy running other "
                            "optimizations right now. Please try again in a moment."}), 429

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {
            "status": "running", "gen": 0,
            "n_gen": params["n_gen"], "pop_size": params["pop_size"],
            "best_obj": None, "best_feasible": False,
            "key": key, "cancel": False, "started": time.time(),
        }
    t = threading.Thread(target=_run_job, args=(job_id, key, params), daemon=True)
    t.start()
    return jsonify({"job": job_id, "n_gen": params["n_gen"],
                    "pop_size": params["pop_size"]})


@app.route("/api/progress/<job>")
def api_progress(job):
    with JOBS_LOCK:
        j = JOBS.get(job)
        if not j:
            abort(404)
        return jsonify({
            "status": j["status"], "gen": j["gen"], "n_gen": j["n_gen"],
            "best_obj": j["best_obj"], "best_feasible": j["best_feasible"],
            "best_f1": j.get("best_f1"),
        })


@app.route("/api/cancel/<job>", methods=["POST"])
def api_cancel(job):
    with JOBS_LOCK:
        j = JOBS.get(job)
        if not j:
            abort(404)
        j["cancel"] = True
    return jsonify({"ok": True})


@app.route("/api/result/<job>")
def api_result(job):
    with JOBS_LOCK:
        j = JOBS.get(job)
        if not j:
            abort(404)
        if j["status"] not in ("done", "cancelled"):
            return jsonify({"status": j["status"]}), 202
        return jsonify({"status": j["status"], **j.get("result", {})})


if __name__ == "__main__":
    # Hosts like Render/Railway/Heroku provide the port via $PORT.
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
