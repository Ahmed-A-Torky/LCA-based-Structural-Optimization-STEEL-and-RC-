# Capacity-building pathway

A six-module route through the studio for undergraduate courses, graduate
optimization classes and practitioner workshops. Every exercise is reproducible
with a fixed seed; expected outcomes quote the studio references so learners can
check themselves.

| # | Module | Problems | Learning outcomes | Exercise and expected outcome |
|---|---|---|---|---|
| 1 | Sizing under stress and displacement | 10-bar, 25-bar, 72-bar | Read a utilisation table; identify the governing limit state; relate area to stiffness | Run the 10-bar at 80x80 (seed 2): ~2359 kg, displacement governs. Halve the displacement limit in `engine.py` and predict the mass change before re-running. |
| 2 | Frames and drift | 10-member, 25-member frames | Combined axial-bending checks; drift as the binding serviceability state | Compare the 10-member frame optimum (3217 kg) against a hand estimate from the drift limit; explain the load scale note. |
| 3 | Code-checked steel design | 3-storey MRF, built-up beam ASD / LRFD | Discrete selection vs continuous sizing; LRFD interaction; classification of flanges and webs; LTB and bracing | (a) Verify W24x62/W10x60 is feasible at 93.6% beam utilisation. (b) Optimize the LRFD beam laterally unsupported (276.7 kg, LTB governs) then supported: governing state flips to yielding. (c) Set Cb = 1.14 and quantify the mass saving. (d) Explain why LRFD is 11.5% lighter than ASD though phi*Omega = 1.503. |
| 4 | Targets, not just limits | 10-bar, 72-bar, portal (frequency) | Non-monotonic constraints; penalty design; tolerance bands | Run the 10-bar frequency case: f1 = 13.86 Hz inside +/-1% at 2574 kg. Tighten `eqtol` to 0.005 and watch the mass approach the published 2637.85 kg. |
| 5 | Reinforced concrete and embodied carbon | RC beam, column, footing, frame | Doubly-reinforced strain compatibility; P-M interaction; SCWB; where carbon comes from | Optimize the beam (727.8 kg CO2, flexure at 100%, top steel at the hanger minimum). Optimize the column and explain why the compression face carries more steel at e/h = 0.20. |
| 6 | Carbon is a decision | RC members + steel routes | Objective choice changes the design, not only its score; supply-chain decarbonization | Re-run the beam under each steel route: 728 -> 321 kg CO2 with steel rising 136 -> 255 kg. Draw the six optimal sections and identify which limit state governs each. |

Suggested assessment: a short design memo per module (governing state, sensitivity
tried, what changed and why), plus one term project extending the engine — a new
constraint, section law or emission dataset — using the test suite as the
acceptance criterion.
