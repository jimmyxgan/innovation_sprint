"""Explicit modality metadata. Positions are placeholders, NOT approved installation drawings."""
from dataclasses import dataclass
from typing import Tuple
@dataclass(frozen=True)
class SensorConfig:
    sensor_id: str
    modality: str
    sample_rate: int
    passband_hz: Tuple[float,float]
    band_edges_hz: Tuple[float,...]
    position: tuple = ()
    calibrated: bool = False

def default_configs():
    # 100 kHz AE sampling cannot resolve >50 kHz; use >=250 kHz for 100 kHz AE band.
    return {
        'ae':SensorConfig('AE-example','ae',250_000,(20_000,100_000),(20_000,50_000,75_000,100_000)),
        'mic':SensorConfig('MIC-example','mic',62_500,(500,20_000),(500,5_000,10_000,14_000,20_000)),
    }
