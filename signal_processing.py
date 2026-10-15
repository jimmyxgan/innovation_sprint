"""Modality-specific filtering and robust candidate detection."""
import numpy as np
from scipy.signal import butter,sosfiltfilt,hilbert,find_peaks

def preprocess(x, config):
    x=np.asarray(x,dtype=float)
    fs=config.sample_rate
    lo,hi=config.passband_hz
    if not 0 < lo < hi < fs/2: raise ValueError('Invalid passband / Nyquist violation')
    if len(x)<64: raise ValueError('Insufficient samples')
    y=sosfiltfilt(butter(4,[lo,hi],btype='bandpass',fs=fs,output='sos'),x)
    return y

def candidates(x,config,mad_multiplier=8.,min_separation_s=.003):
    y=preprocess(x,config)
    env=np.abs(hilbert(y))
    quiet=env[env<=np.quantile(env,.65)]
    med=np.median(quiet);mad=np.median(np.abs(quiet-med))
    threshold=float(med+mad_multiplier*1.4826*mad)
    threshold=max(threshold,1e-9)
    peaks,_=find_peaks(env,height=threshold,prominence=threshold*.5,
                       distance=max(1,int(min_separation_s*config.sample_rate)))
    return {'filtered':y,'envelope':env,'threshold':threshold,'peaks':peaks,
            'noise_sigma':float(1.4826*mad)}
