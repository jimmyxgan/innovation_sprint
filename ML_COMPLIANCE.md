# Machine-learning verification scope

This is a **synthetic demonstration**, not IEC certification or verified in-service PD detection.

## ISO/IEC TS 4213:2022 — Classification performance

- [ ] Maintain source/session/group IDs and provenance for all waveforms.
- [ ] Split by independent source family or acquisition session **before augmentation**.
- [ ] Report confusion matrix, PD recall, precision, and false positives per simulated hour.
- [ ] Fix acceptance criteria prior to testing; publish confidence intervals and failure cases.
- [ ] Compare nine-feature baseline with updated feature set using identical held-out groups.

## ISO/IEC 23894:2023 — AI risk management

| Risk | Mitigation / verification |
|---|---|
| Missed PD | Sensitivity tests; preserve uncertain states; no autonomous trip |
| False alarm | Negative classes including impacts, airflow and mechanical vibration |
| Out-of-distribution waveform | Flag uncertainty; test held-out conditions |
| Sensor dropout | Monitoring-degraded status; no silent substitution |
| Synthetic-to-real gap | Explicit demo labeling; require independent electrical-reference PD experiments |

IEC TS 62478:2016 is the **separate acoustic measurement reference**. Numerical bands, thresholds, and synthetic propagation are engineering assumptions, not IEC mandates.
