# PD Monitor v3 — reliability-focused Python readout prototype

**Not certified; synthetic data; no measured reactor acoustic transfer function.**

This is a replacement for the v2 demo. It keeps the 16:9 HMI and 16 acoustic nodes, but separates physics (`physics.py`), signal processing (`processing.py`), application/storage (`app.py`), synthetic benchmark (`validate.py`) and offline delivery test (`outbox_demo.py`).

## Remote Linux + VS Code

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py --port 8765
```

In VS Code Remote SSH, forward port 8765 in the **Ports** panel. Open `http://localhost:8765/`. Server binds to localhost only.

### Benchmarks

```bash
python validate.py --samples 12
# creates validation/metrics.csv, metrics.json, pd_recall.png, false_alarms.png
python app.py --no-ml --seed-only  # conventional detector fallback
python outbox_demo.py              # offline: pending events remain queued
python outbox_demo.py --connected  # MOCK station acknowledgement only
```

**Interpretation warning:** `false_alarms_per_sim_hour` is based on accelerated, densely injected synthetic test events. It is NOT a realistic expected substation false alarm rate. The RF can perform worse under unseen spectral/sensor changes. Keep all candidate events and avoid safety claims. The model does not generate UV detections until a real UV input interface is provided.

### COMSOL interface

```python
import numpy as np
from physics import SENSORS, FS
# signals shape (16, N>=512), channels in SENSORS order; units: volts at ADC
np.savez('comsol_sensors.npz', signals=signals, fs=FS, sensor_ids=np.array(SENSORS))
```

Then run `python app.py --comsol-npz comsol_sensors.npz` to replay that fixed window. Data must already include the propagation and sensor transfer function (or measured sensor response). For other sample rates, perform calibrated anti-aliased resampling before import.

### API

- `/api/status` event-level recent log, hourly rates, status, station requirements
- `/api/hourly` historical aggregate
- `/api/waveform` latest event snippets (JSON, demonstration only)

**Event model:** 1 row per multi-sensor cluster; includes event UID, timestamp, source, sequence, time quality, classification, gap, sector, response similarity margin (not probability), amplitudes and detection flags. SQLite outbox is transactionally written but the delivery script simulates acknowledgement; it does not transmit over TLS.

### Literature and standards

- IEC TS 62478:2016, *Measurement of partial discharges by electromagnetic and acoustic methods*, https://webstore.iec.ch/en/publication/25740 . Supports acoustic PD detection, sensor response/sensitivity checks and localization considerations; does NOT specify our numerical signal parameters.
- IEC 60255-24:2013 / IEEE C37.111-2013 COMTRADE, https://www.theiteh.com/catalog/standards/iec/feae48a4-c2ca-4739-8f51-8b4e7785ca25/iec-60255-24-2013 . Standard for transient waveform export; not implemented here.
- Breiman (2001), *Random Forests*, https://doi.org/10.1023/A:1010933404324 . Basis of RF model.
- Hampel (1974), *The Influence Curve and Its Role in Robust Estimation*, JASA 69:383–393. Robust-statistics motivation for median/MAD.
- Trench Innovation Sprint 2026 Track B problem statement, pp. 4, 10–12, user-provided.

Every synthetic source characteristic, attenuation equation, transfer response and detection threshold is tagged `[ASSUMPTION]` in code. None are represented as experimentally established reactor values. See `STANDARDS_MATRIX.md` for the implementation versus specification boundary.
