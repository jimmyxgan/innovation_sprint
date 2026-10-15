"""Independent physical diagnostics; NOT an ML veto."""
import numpy as np

def evaluate_event(w,noise_sigma,config):
    x=np.asarray(w,float)
    peak=float(np.max(np.abs(x))) if len(x) else 0.
    snr=peak/max(float(noise_sigma),1e-12)
    return {'peak_to_noise':snr,'signal_valid':bool(np.all(np.isfinite(x)) and len(x)>=32),
            'clipping_suspected':bool(np.count_nonzero(np.abs(x)>=.999*np.max(np.abs(x)))>max(5,len(x)*.05)) if peak else False,
            'modality':config.modality}

def association_window(distance_m,speed_m_s,timing_margin_s=.0002):
    if distance_m<0 or speed_m_s<=0:raise ValueError('Invalid propagation inputs')
    return float(distance_m/speed_m_s+timing_margin_s)
