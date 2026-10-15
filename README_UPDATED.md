# Integrated dual-modality acoustic PD prototype

**Baseline:** Previous `innovation_sprint_updated_package.zip` supplied in this conversation, not a verified checkout of the current GitHub HEAD.

## Start the integrated dashboard

```bash
pip install -r requirements.txt
python app.py --demo --reset-demo-db
# Open http://localhost:8765/
```

The integrated mode is now the **default**. It simulates 16 legacy AE channels at 250 kHz and four illustrative airborne microphones at 62.5 kHz, processes each modality independently, runs separate synthetic-trained RF classifiers, and stores decision evidence in SQLite. The HMI shows RF scores, modality IDs, sensor quality and unresolved localization. The existing dashboard layout, seven-day synthetic history, waveform display, event log and outbox are retained.

Use `python app.py --legacy --demo --reset-demo-db` to run the original AE-only processing pipeline. `--comsol-npz` currently invokes the original AE-only import path, not a new dual-modality COMSOL integration. `--no-ml` returns uncertain decisions in integrated mode instead of claiming PD detection.

## Test

```bash
python -m unittest tests_updated test_integration -v
python test_demo_cadence.py
python test_trends.py
python validate.py  # legacy synthetic benchmark; NOT an integrated model validation
```

## Important boundaries

- **Synthetic only:** PD and interference waveforms, channel attenuation, sensor positions and noise are illustrative, not calibrated against a reactor.
- **AE high frequency:** Original 100 kHz legacy signals are upsampled, then a separate synthetic high-frequency component is added. Upsampling does not restore lost spectral information.
- **Location:** No gap/sector estimate is asserted in integrated mode. The legacy 16-node map is explicitly illustrative. Four microphone channels are represented in event evidence, not as physically approved mounts.
- **Scores:** RF outputs are uncalibrated scores, not calibrated probabilities or verified risk levels.
- **Feature extraction:** `features.py` currently uses multiscale FFT energy bands as a wavelet *surrogate*, **not** actual wavelet coefficients. A wavelet implementation and feature ablation remain future improvements.
- **Temporal features:** `sequence_features()` exists but is not yet used to trigger a maintenance advisory. Existing trend logic is retained.
- **Fusion:** Candidate association uses an illustrative time window, not calibrated propagation. No microphone response is required to confirm an AE event.
- **Security:** HTTP on localhost and SQLite transactional outbox remain demonstration-only. No IEC 61850/PTP/TLS gateway is implemented.
- **Validation:** Integrated smoke tests cover data flow, not independent PD accuracy, false-alarm rate, field generalization or ISO/IEC conformity.

The demo is **not** an IEC-certified, field-validated PD monitoring device.
