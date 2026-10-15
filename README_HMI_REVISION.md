# HMI revision: unwrapped sensor-array map

The reactor's three **distinct accessible sensor domains** are shown as separate flat matrices, not as nested concentric circles or an ambiguous isometric model:

- OUTER WINDING: 8 azimuths x 4 heights = 32 contact AE sensors.
- INNER BORE: 8 azimuths x 4 heights = 32 contact AE sensors.
- EXTERNAL AIR: 8 azimuths x 2 heights = 16 airborne microphones.

The display lights responding sensors from **per-event simulated channel amplitudes**. It does **not** highlight an inferred PD source location. There are no sensors on intermediate winding surfaces or inside cooling ducts. Proposed mounting is illustrative and must be approved by the asset owner; no routing, material, or temperature qualification is established by this code.

The backend synthesizes 80 channels, with separate AE and microphone models. The historical seven-day chart retains clearly identified scripted baseline data, but today's bucket now adds actual live simulated classifications on each refresh. The assumed 24 h/day denominator is for demonstration only and **is not a validated event rate**. For field deployment, replace it with measured acquisition uptime.

The operator-facing event log shows PD-like events only; all candidates (including uncertain and interference) remain in SQLite for audit and ML validation. 'Likely PD activity' is a classification label, not verified PD or an IEC certification claim.

Run `python app.py --demo --reset-demo-db`, then open http://localhost:8765/ .
