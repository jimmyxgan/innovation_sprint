"""Reproducible, modality-specific event features for Random Forest.
Wavelet subband energies are implemented with a short-time FFT octave-like filter bank
(no extra dependencies); these are *not* discrete wavelet transform coefficients.
"""
import numpy as np
from scipy.signal import hilbert
from scipy.stats import kurtosis

BASE_NAMES=('rms','crest_factor','kurtosis','rise_s','duration_s',
            'spectral_centroid_hz','spectral_bandwidth_hz','spectral_entropy')

def feature_names(config):
    edges=config.band_edges_hz
    return BASE_NAMES+tuple(f'energy_{int(a)}_{int(b)}hz' for a,b in zip(edges[:-1],edges[1:]))+('multiscale_energy_low','multiscale_energy_mid','multiscale_energy_high')

def extract_event_features(w,config):
    w=np.asarray(w,dtype=float)
    if w.ndim!=1 or len(w)<32: raise ValueError('Expected 1D event waveform >=32 samples')
    fs=config.sample_rate
    x=w-np.mean(w)
    env=np.abs(hilbert(x));mx=max(float(env.max()),1e-12)
    rms=float(np.sqrt(np.mean(x*x)))
    peak=float(np.max(np.abs(x)))
    onset=np.flatnonzero(env>=.1*mx)
    rise=(max(0,int(np.argmax(env))-int(onset[0]))/fs) if len(onset) else 0.
    duration=float(np.sum(env>=.25*mx)/fs)
    power=np.abs(np.fft.rfft(x*np.hanning(len(x))))**2
    freq=np.fft.rfftfreq(len(x),1/fs)
    valid=(freq>=config.passband_hz[0])&(freq<=config.passband_hz[1])
    power=np.where(valid,power,0)
    power=power/(power.sum()+1e-18)
    centroid=float((freq*power).sum())
    bandwidth=float(np.sqrt(np.sum((freq-centroid)**2*power)))
    entropy=float(-np.sum(power*np.log(power+1e-18)))
    edges=config.band_edges_hz
    bands=[float(power[(freq>=a)&(freq<(b if b<edges[-1] else b+1))].sum()) for a,b in zip(edges[:-1],edges[1:])]
    # Three logarithmically-spaced energy summaries capture transient spectral scale.
    lo,hi=config.passband_hz
    breaks=np.geomspace(lo,hi,4)
    scales=[float(power[(freq>=a)&(freq<(b if i<2 else b+1))].sum()) for i,(a,b) in enumerate(zip(breaks[:-1],breaks[1:]))]
    result=[rms,peak/max(rms,1e-12),float(kurtosis(x,fisher=True,bias=False)) if np.std(x)>1e-12 else 0.,rise,duration,centroid,bandwidth,entropy]+bands+scales
    return np.nan_to_num(result,nan=0.,posinf=0.,neginf=0.).tolist()

def sequence_features(times_s,band_ratios,phase_radians=None,window_s=None):
    """Temporal corroboration; not single-event RF input. Phase optional."""
    t=np.sort(np.asarray(times_s,float)); dt=np.diff(t)
    span=float(window_s) if window_s is not None else (float(t[-1]-t[0]) if len(t)>1 else 0.)
    phases=np.asarray(phase_radians,float) if phase_radians is not None else np.array([])
    return {'repetition_rate_hz':float(len(t)/span) if span>0 else 0.,
            'interval_cv':float(np.std(dt)/np.mean(dt)) if len(dt)>1 and np.mean(dt)>0 else None,
            'phase_concentration':float(np.abs(np.mean(np.exp(1j*phases)))) if len(phases)>1 else None,
            'band_ratio_variance':float(np.var(band_ratios,ddof=1)) if len(band_ratios)>1 else None}
