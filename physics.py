"""Explicitly illustrative acoustic test fixture, NOT a calibrated reactor model.

REFERENCES:
[IEC62478] IEC TS 62478:2016, clauses 5-6: acoustic PD measurement,
  propagation, sensor bandwidth/sensitivity and localization/sensitivity checks.
  https://webstore.iec.ch/en/publication/25740
[CHALLENGE] Trench 2026 Innovation Sprint, Track B and Ground Rules pp. 4,10-12.
  Physical propagation must be validated separately (e.g., COMSOL).
[ASSUMPTION] Numerical source frequency, decay, transfer-function shape,
  sound speed, distance law, noise level, and synthetic event rates below are
  DESIGN ASSUMPTIONS, not values prescribed by IEC or measured on this reactor.

Acoustic source: s(t)=A exp[-(t-t0)/tau] sin(2*pi*f*(t-t0)) H(t-t0)
  [ASSUMPTION] Standard damped oscillator test pulse, not a universal PD signature.
Sensor path: y_i(t)=gain_i * (h_i * s)(t-delay_i)+noise_i(t)
  [IEC62478] path and sensor responses matter; numerical h_i is [ASSUMPTION].
Distance amplitude: A_i=(d0+d_i)^(-alpha), [ASSUMPTION], not an IEC law.
"""
import numpy as np
from scipy.signal import butter, sosfilt, sosfiltfilt
FS=100_000
N=24_000
GAPS=4
SECTORS=4
SENSORS=[f'AE-G{g}-S{s}' for g in range(1,5) for s in range(1,5)]
RADII=np.array([1.,1.5,2.,2.5])  # [ASSUMPTION] normalized radii, NOT metres
DETECTION_BAND=(14_000,43_000)  # [ASSUMPTION] within broad acoustic range in IEC TS 62478, NOT prescribed band
SOS=butter(4, DETECTION_BAND, btype='bandpass',fs=FS,output='sos')

def sensor_xy(i):
    g,s=divmod(i,4); a=s*np.pi/2
    return RADII[g]*np.array([np.cos(a),np.sin(a)])

def source_xy(g,s,offset=0):
    a=s*np.pi/2+np.pi/4+offset
    return RADII[g]*np.array([np.cos(a),np.sin(a)])

def template(g,s,offset=0,alpha=1.7,scale=None):
    d=np.array([np.linalg.norm(source_xy(g,s,offset)-sensor_xy(i)) for i in range(16)])
    amp=(.28+d)**(-alpha)  # [ASSUMPTION] distance attenuation with regularization
    if scale is not None: amp*=scale
    return amp/np.max(amp),d

def pulse(rng,kind,length=512):
    t=np.arange(length)/FS; t0=.001
    # [ASSUMPTION] example ultrasonic ranges selected for overlapping classes;
    # IEC TS 62478 discusses ~20-250 kHz acoustic PD, not these class-specific bounds.
    if kind=='pd': f,tau=rng.uniform(18e3,37e3),rng.uniform(.00018,.00065)
    elif kind=='impact': f,tau=rng.uniform(12e3,39e3),rng.uniform(.0003,.0014)
    else: f,tau=rng.uniform(8e3,28e3),rng.uniform(.0007,.002)
    dt=np.maximum(t-t0,0)
    return np.where(t>=t0,np.exp(-dt/tau)*np.sin(2*np.pi*f*dt),0.)

def sensor_transfer(x,fs=FS,cutoff=42_000):
    # [ASSUMPTION] 2-pole low-pass surrogate for an analog interrogator response.
    # Replace with measured complex frequency response / manufacturer calibration.
    sos=butter(2,cutoff,btype='lowpass',fs=fs,output='sos')
    return sosfilt(sos,x)

def make_window(rng,scenario='nominal',deterioration=0.,force_kind=None,force_region=None):
    """Returns 16 x N synthetic VOLT-equivalent ADC signals + source ground truth.

    [ASSUMPTION] 120 Hz structural vibration represents 2 x 60 Hz mains excitation;
    mains frequency and coupling must be checked for the actual installation.
    Gaussian electronic noise and impact/PD occurrence rates are placeholders.
    """
    t=np.arange(N)/FS
    noise={'nominal':.012,'high_noise':.040,'sensor_shift':.022,'spectral_shift':.018}.get(scenario,.012)
    x=rng.normal(0,noise,(16,N))
    x+=rng.uniform(.004,.015)*np.sin(2*np.pi*120*t)[None,:]
    # [ASSUMPTION] accelerated synthetic deterioration; time in UI is NOT physical ageing.
    count=1 if force_kind is not None else rng.poisson(1.0+2.5*deterioration)
    truth=[]
    for _ in range(count):
        kind=force_kind or rng.choice(['pd','impact','vibration'],p=[.6,.28,.12])
        g,s=force_region if force_region is not None else (int(rng.integers(4)),int(rng.integers(4)))
        start=int(rng.integers(1500,N-1800))
        scale=rng.lognormal(0,.16 if scenario!='sensor_shift' else .48,16)
        amp,dist=template(g,s,rng.uniform(-.3,.3),rng.uniform(1.3,2.1),scale)
        wave=pulse(rng,kind)
        if scenario=='spectral_shift':
            # [ASSUMPTION] sensor/environment band-limitation shift, not a PD source property.
            wave=sensor_transfer(wave,cutoff=25_000)
        strength=rng.uniform(.20,.72)*(1+.35*deterioration)
        for i in range(16):
            # [ASSUMPTION] delay proportional to normalized distance; NOT measured velocity.
            delay=int(dist[i]*10+rng.normal(0,2))
            ix=start+max(delay,0)
            x[i,ix:ix+len(wave)]+=strength*amp[i]*wave
        truth.append({'kind':kind,'gap':g+1,'sector':s+1,'sample':start+100})
    # [ASSUMPTION] 12-bit bipolar ADC full scale +/-2 V, quantization step 4/4096 V.
    # No pC calibration is claimed: acoustic volts cannot be converted to apparent charge
    # without experimental correlation (IEC TS 62478 sensitivity-check principles).
    x=np.clip(x,-2,2)
    x=np.round(x/(4/4096))*(4/4096)
    return x,truth
