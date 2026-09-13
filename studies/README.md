# Reproducibility studies

Every figure and table in the documentation and the manuscript is regenerated
by the scripts in this folder (fixed GA seeds). Outputs go to `studies/out/`
(override with `STUDIO_RUNS` / `STUDIO_FIGS`).

| Script | Produces |
|---|---|
| `make_figs.py` | per-problem geometry, cross-section and convergence figures (needs sample-run JSONs in `out/runs`) |
| `build_pdf.py` | the one-page-per-benchmark PDF documentation |
| `nl_study.py`, `nl_figs_v2.py` | cost-vs-carbon nonlinearity maps and factor sweeps for the frame beam and column sections |
| `val_figs.py`, `val_runs.py` | validation set: mechanics verification, Pareto fronts, regime map, utilization audit, multi-seed statistics, frame closure |
| `opt_sections.py` | the six optimal sections drawn to scale with practical bar schedules |
