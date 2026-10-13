# PD Monitor v6 — Presentation Demo

This is a **synthetic demonstration**, not a field-qualified partial-discharge detector or a secure IEC 61850 station endpoint. The physical propagation and PD pulse parameters in `physics.py` are illustrative assumptions; consult `STANDARDS_MATRIX.md` for the proposed deployment architecture.

## Start (recommended for the PowerPoint screenshot / video)

```bash
pip install -r requirements.txt
python app.py --demo --reset-demo-db --port 8765
```

Open `http://localhost:8765` (forward TCP 8765 in VS Code Remote SSH). The browser canvas stays 1920×1080 and letterboxes at other aspect ratios. The demo auto-generates **scripted, illustrative seven-day daily totals** and updates the live detector about every 0.65 seconds (processing time may add latency). The event log and latest PD-like waveform change as new events arrive. The seven-day line is daily history: it is **not** expected to shift appreciably every second.

**`--reset-demo-db` deletes this package's `monitor_v3.sqlite3` database.** Back it up first if you want to retain previous events. Use it when upgrading from v5 to prevent old accumulated synthetic events from crowding the log. After first run, omit `--reset-demo-db` to retain records.

Alternative:

```bash
python app.py --demo --port 8765
python app.py --port 8765                 # slower, without scripted baseline
python app.py --demo --period 1.0 --port 8765
python test_trends.py
python validate.py
```

`--seed-history` is a backwards-compatible alias for inserting the scripted baseline. `--no-ml` disables RF, preserving conventional detection; in that mode PD-like waveforms are not produced because no RF classification exists.

## What is simulated vs processed?

- **Scripted 7-day history**: seven explicit, synthetic daily totals for PD-like and all candidate events, assuming 24 h/day exposure; **not produced by the detector**. This is marked `SCRIPTED DEMO HISTORY` in the dashboard. The historical baseline is the mean of the first four completed days, the comparison is the next two completed days; today is shown but excluded from the comparison. Thresholds (2× WATCH, 3× WARNING) are *illustrative, not IEC limits*.
- **Live events**: generated through `make_window → detect → Random Forest → fuse → SQLite`, with event-level counts. `--demo` raises the synthetic injection rate and shortens the wall-clock wait, but does not claim a real-world PD occurrence rate.
- **Waveform**: the filtered 512-sample capture from the **strongest responding acoustic sensor** for the same latest PD-like event shown on the reactor map. The panel names the sensor (e.g. `AE-G4-S2`) prominently. Amplitude is in *uncalibrated relative units*, not pC.
- **Baseline reference line**: dashed orange at the average PD-like events per assumed monitoring hour from the first four historical days. The blue line shows each day's scripted PD-like events per assumed monitoring hour. Actual field rates require measured uptime and validated detector calibration.
- **Uncertain/unlocalized events**: preserved, not forced into a PD category or sector. UV channels remain placeholders with no fabricated corroboration.

## Engineering limitations

This Python prototype uses local HTTP, synthetic UTC quality, a toy acoustic attenuation model and a volatile waveform cache. It does **not** implement PTP time synchronization, IEC 61850, COMTRADE, mTLS, EMC qualification or field calibration. Refer to `STANDARDS_MATRIX.md` for the qualitative architecture and open qualification work.

## Version 7 presentation cadence
Launch with `python app.py --demo --reset-demo-db --port 8765`.
The application seeds an explicitly illustrative seven-day baseline, then injects
**one synthetic PD source approximately every 3 seconds** into each 0.24 s
16-channel acquisition window. RF classification remains independent: an injected
PD may be marked uncertain or interference-like. No labels are overridden.
The `--period 5` option changes the acquisition cadence to about 5 seconds.
Processing time adds to the interval. `--reset-demo-db` deletes local demo data.
The seven-day scripted trend remains independent of live events and represents
an illustrative elevated-condition history, not seven days of measurement.
