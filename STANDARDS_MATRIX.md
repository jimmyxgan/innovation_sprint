# Readout-chain standards traceability — engineering proposal (NOT certification)

Challenge source: Trench Innovation Sprint 2026 problem statement, pp. 10–12.

| Requirement | Prototype evidence | Deployment engineering still required |
|---|---|---|
| IEC TS 62478 acoustic PD | Synthetic acoustic conditioning, detection, sensitivity benchmark | Measured sensor transfer function, calibrated source tests, propagation verification, site noise and sensitivity check |
| IEC 60270 | Not used to infer pC from acoustic voltage | Reference electrical PD measurement for any experimentally claimed pC correlation |
| IEC/IEEE 61850-9-3 station time | UTC ISO event fields, sequence, `SIMULATED_CLOCK` time quality | PTP-capable acquisition hardware, grandmaster, measured sync error, loss-of-sync behavior |
| IEC 62351-3/-9 transport security | No cryptographic transport implemented | TLS profile and mutual authentication, certificates, trust anchors, key rotation/revocation, tested endpoints |
| IEC 62351-8 / IEC 62443-4-2 | Not implemented | RBAC and secure component capability evidence, threat model, provisioning, audit |
| IEC 61850 | JSON event model as internal schema only | Select a commercial IEC 61850 gateway and map data attributes/quality/alarm objects; interoperability test |
| IEC 60255-24 / IEEE C37.111 | Raw waveform snippets available in `/api/waveform` | COMTRADE exporter/reader validation and channel scaling/time quality; not necessary for HMI prototype |
| IEC 61000-6-5 | Not simulated in software | Vendor EMC immunity test reports for ground-potential interrogator, edge device and network equipment |
| Data reliability | SQLite WAL transactional outbox, event UID, simulated disconnect/reconnect | Authenticated receiver acknowledgements, durable retry queue, disk failure tests, retention/backups |
| Track B trend | Event-level 10-s demo trends, 1-hour rates, 48-hour aggregates | Load-normalized baseline and EWMA/CUSUM, long-term replay, alarm threshold commissioning |

The local web dashboard uses HTTP bound to `127.0.0.1` and is intended to be accessed via VS Code SSH forwarding. It is NOT an IEC 61850 endpoint or secure public web service.

**Deployment topology (proposed):**

Approved AE/UV sensors → qualified interrogator/ADC → PTP-disciplined edge processor → event DB + offline queue → industrial switch / mTLS secure link → IEC 61850 station gateway → maintenance HMI / COMTRADE archive.

**Sensor placement:** The four-sensors-per-air-gap arrangement is hypothetical; the team must obtain approval before claiming it meets the installation restrictions. Optical UV can corroborate exposed discharges only, not internal opaque insulation PD.
