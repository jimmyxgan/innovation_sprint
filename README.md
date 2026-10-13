# Winding-Resolved PD Condition Monitor — Prototype

**Demonstration only.** This software generates synthetic acoustic/UV observations, not real partial-discharge measurements. The ring-response matrix, sensor positions, UV detections, timestamps and classifier training are illustrative. It has **not** been calibrated to a reactor, independently validated or certified to any IEC standard.

## Run

```bash
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8765/dashboard.html** in a browser. Press **F11** for a full-screen 16:9 presentation. The layout is optimized for 1920×1080 and scales proportionally. Stop the server with Ctrl+C.

To generate an SQLite dataset without launching the server:

```bash
python app.py --seed-only
```

## What is implemented

- Four synthetic acoustic channels, nominal 100 kHz sample rate, stochastic PD-like/impact signals and reactor vibration.
- SciPy bandpass filtering, Hilbert envelope, robust adaptive threshold and candidate-event detection.
- Physics-inspired time/frequency feature extraction and a scikit-learn Random Forest trained on **synthetic** waveforms.
- Three event labels: PD-like, interference-like, uncertain; all candidate records retained.
- Illustrative ring inference from an **arbitrary** amplitude-response matrix. Low-confidence and single-sensor events receive an unresolved location.
- Synthetic UV observations as auxiliary evidence. **No camera image processing or physical UV camera integration is implemented.**
- SQLite event records including timestamps, sensor ID, amplitude, dominant frequency, SNR, ML score, estimated ring, confidence, UV flag, and downsampled waveform snippet.
- Live HTTP/JSON endpoint and a responsive fixed-aspect-ratio browser HMI, including clickable reactor windings, trend charts, and an event log.

## Important engineering limitations

1. The classifier has **no field-validated accuracy**. Do not use its synthetic-data score as an actual PD probability.
2. The arbitrary acoustic gain matrix cannot establish ring-level localization. Proper localization requires approved sensor placement, propagation measurements, synchronized acquisition and validation with seeded defects.
3. The timestamps use the host UTC clock, labeled `SIMULATED_SYNC`; there is no hardware PTP implementation.
4. The built-in HTTP server binds to **127.0.0.1 only** and is **not a secure station gateway**. It must not be exposed to a network. There is no IEC 61850, TLS/mTLS, certificate management or COMTRADE implementation in this prototype.
5. The UV flags are synthetic and are not derived from UV frames. No claim of internal-PD UV visibility is made.
6. Historical charts are rolling **10-second demo bins**, not events/hour or true aging trends. They illustrate the interface, not a calibrated deterioration assessment.
7. Acoustic amplitude is an arbitrary filtered receiver unit, not IEC 60270 apparent charge (pC).

## Production path / standards traceability

- **PD measurement:** qualify acoustic sensor/interrogator and UV camera sensitivity, bandwidth, calibration and interference rejection, guided by IEC TS 62478 and relevant IEC 60270 principles.
- **Sensor deployment:** approved rim locations only; avoid cooling gaps; document electrical clearance, temperature, surge and EMC compatibility.
- **Security:** implement station-approved IEC 62351-compatible authenticated encrypted transport, role-based access, certificate/key lifecycle, buffering, and IEC 62443 security requirements.
- **Time:** acquisition-side timestamping using qualified IEC/IEEE 61850-9-3 station synchronization and explicit time-quality metadata.
- **Interoperability:** implement and test an IEC 61850 data model/gateway and, where appropriate, IEC 60255-24 COMTRADE exports.
- **EMC:** select and qualify equipment for applicable IEC 61000-6-5 requirements.
- **Validation:** independent ground-truth data, detection probability versus SNR, false alarms/hour, blind scenario holdout, localization confusion matrix, loss-of-sensor/clock/network tests, and uncertainty thresholds.

## Files

- `app.py` — synthetic acquisition, signal processing, classifier, ring estimation, database, and local HTTP server.
- `dashboard.html` — standalone browser HMI, populated from `/api/status`.
- `monitor.sqlite3` — generated event database after running the application.
