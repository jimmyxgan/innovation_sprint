"""Integrated dual-modality demonstration pipeline; all signals are synthetic.
No field sensitivity, calibration, source localization, or IEC certification is claimed.
"""
from dataclasses import replace
import numpy as np
from scipy.signal import resample_poly
from sensors import default_configs
from signal_processing import candidates, preprocess
from features import extract_event_features, sequence_features
from ml_classifier import train, predict
from conventional import evaluate_event
from fusion import decide
from physics import FS, SENSORS, make_window, pulse
AZIMUTHS=8
AE_LEVELS=5
MIC_LEVELS=2
AE_IDS=[f"AE-{surface}-Z{z+1}-A{a+1}" for surface in ("IN","OUT") for z in range(AE_LEVELS) for a in range(AZIMUTHS)]

CONFIGS=default_configs()
# Four illustrative microphone positions; not mounting approvals.
MIC_IDS=[f'MIC-Z{z+1}-A{a+1}' for z in range(MIC_LEVELS) for a in range(AZIMUTHS)]
CHANNELS=AE_IDS+MIC_IDS

def event_wave(rng, modality, kind, config, size=1024):
    fs=config.sample_rate
    t=np.arange(size)/fs
    if modality=='ae':
        f=rng.uniform(35e3,85e3) if kind=='pd' else rng.uniform(22e3,96e3)
        tau=rng.uniform(.00012,.00065) if kind=='pd' else rng.uniform(.0004,.0015)
    else:
        f=rng.choice([rng.uniform(5e3,10e3),rng.uniform(14e3,19e3)]) if kind=='pd' else rng.uniform(2e3,19e3)
        tau=rng.uniform(.0003,.0018) if kind=='pd' else rng.uniform(.001,.004)
    onset=.0006
    d=np.maximum(0,t-onset)
    wave=np.sin(2*np.pi*f*d)*np.exp(-d/tau)*(t>=onset)
    if modality=='mic' and kind=='pd':
        wave+=.3*np.sin(2*np.pi*7e3*d)*np.exp(-d/(tau*1.5))*(t>=onset)
    return wave

def train_models(seed=42, samples_per_class=180):
    rng=np.random.default_rng(seed)
    bundles={}
    for key,config in CONFIGS.items():
        xs=[];ys=[]
        for label,kind in [(1,'pd'),(0,'impact'),(0,'vibration')]:
            for _ in range(samples_per_class):
                x=event_wave(rng,key,kind,config)
                x=rng.uniform(.1,.9)*x+rng.normal(0,rng.uniform(.003,.04),len(x))
                xs.append(x);ys.append(label)
        bundles[key]=train(xs,ys,config,seed)
        bundles[key]['training_origin']='synthetic damped oscillators only; no field validation'
    return bundles

def make_dual_window(rng,scenario='nominal',deterioration=.5,demo=False):
    """96 independently synthesized channels at 8 azimuths, 5 AE heights on each
    accessible surface, and 2 external microphone heights. Not field-calibrated.
    Legacy source timing is reused, not its physically invalid gap-mounted sensors.
    """
    base,truth=make_window(rng,scenario,deterioration,force_kind='pd' if demo else None)
    ae_fs=CONFIGS['ae'].sample_rate;mic_fs=CONFIGS['mic'].sample_rate
    n_ae=round(base.shape[1]*ae_fs/FS);n_mic=round(base.shape[1]*mic_fs/FS)
    ae=rng.normal(0,.006 if scenario=='nominal' else .012,(len(AE_IDS),n_ae))
    mic=rng.normal(0,.008 if scenario=='nominal' else .018,(len(MIC_IDS),n_mic))
    for ev in truth:
        source_az=(ev['sector']-1)*2+rng.integers(0,2)
        source_z=int(rng.integers(AE_LEVELS))
        for i in range(len(AE_IDS)):
            surface=i//(AE_LEVELS*AZIMUTHS)
            z=(i//AZIMUTHS)%AE_LEVELS;az=i%AZIMUTHS
            angular=min((az-source_az)%AZIMUTHS,(source_az-az)%AZIMUTHS)
            gain=.42*np.exp(-.48*angular-.62*abs(z-source_z))*(.95 if surface==0 else .75)
            if gain<.025:continue
            w=event_wave(rng,'ae',ev['kind'],CONFIGS['ae'])
            ix=round(ev['sample']*ae_fs/FS)+int((angular*.00008+abs(z-source_z)*.00005)*ae_fs)
            hi=min(n_ae,ix+len(w))
            if hi>ix:ae[i,ix:hi]+=gain*w[:hi-ix]
        for i in range(len(MIC_IDS)):
            z=i//AZIMUTHS;az=i%AZIMUTHS
            angular=min((az-source_az)%AZIMUTHS,(source_az-az)%AZIMUTHS)
            gain=.25*np.exp(-.5*angular-.4*abs(z-source_z//2))
            if gain<.025:continue
            w=event_wave(rng,'mic',ev['kind'],CONFIGS['mic'])
            ix=round(ev['sample']*mic_fs/FS)+int((.00025+angular*.00012)*mic_fs)
            hi=min(n_mic,ix+len(w))
            if hi>ix:mic[i,ix:hi]+=gain*w[:hi-ix]
    return {'ae':ae,'mic':mic},truth

def process_dual(signals,bundles,base_time,sequence,source='synthetic'):
    """Return app-compatible event records and waveform captures.
    Candidate event association is illustrative and not a calibrated localization.
    """
    from datetime import timedelta
    observations=[]
    for key,arr in signals.items():
        config=CONFIGS[key]
        ids=AE_IDS if key=='ae' else MIC_IDS
        for i,x in enumerate(arr):
            result=candidates(x,config,mad_multiplier=9,min_separation_s=.008)
            for p in result['peaks'][:25]:
                width=1024
                a=max(0,int(p)-width//2);b=min(len(x),a+width)
                if b-a<64:continue
                w=result['filtered'][a:b]
                diag=evaluate_event(w,result['noise_sigma'],config)
                score=predict(bundles[key],w,config) if bundles else None
                observations.append({'time':float(p/config.sample_rate),'modality':key,'id':ids[i],
                                     'channel':i,'score':score,'diag':diag,'peak':float(np.max(np.abs(w))),
                                     'wave':w,'fs':config.sample_rate,'band_ratio':extract_event_features(w,config)[8]})
    observations.sort(key=lambda x:x['time'])
    clusters=[]
    # Time-only association tolerance is provisional; source location not inferred.
    for o in observations:
        if clusters and abs(o['time']-clusters[-1][-1]['time'])<.0025:clusters[-1].append(o)
        else:clusters.append([o])
    events=[];captures={}
    for j,cluster in enumerate(clusters):
        scores=[o['score'] for o in cluster if o['score'] is not None]
        valid=all(o['diag']['signal_valid'] and not o['diag']['clipping_suspected'] for o in cluster)
        decision=decide(scores,quality_ok=valid,physical_consistency=None)
        label={'pd_likely':'PD-like','interference_likely':'Interference','uncertain':'Uncertain',
               'monitoring_degraded':'Monitoring degraded'}[decision['state']]
        peak=max(o['peak'] for o in cluster)
        ae_amps=[0.]*len(AE_IDS);ae_detected=[False]*len(AE_IDS)
        mic_amps=[0.]*len(MIC_IDS);mic_detected=[False]*len(MIC_IDS)
        for o in cluster:
            if o['modality']=='ae':
                ae_amps[o['channel']]=max(ae_amps[o['channel']],o['peak']);ae_detected[o['channel']]=True
            else:
                mic_amps[o['channel']]=max(mic_amps[o['channel']],o['peak']);mic_detected[o['channel']]=True
        stamp=(base_time+timedelta(seconds=cluster[0]['time'])).isoformat(timespec='milliseconds')
        uid=f'{source}-{sequence:010d}-{j:03d}'
        modalities=sorted(set(o['modality'] for o in cluster))
        evidence={'modalities':modalities,'rf_scores':{k:round(max((o['score'] for o in cluster if o['modality']==k and o['score'] is not None),default=0),3) for k in modalities},
                  'quality_ok':valid,'decision_reason':decision['reason'],'sensor_ids':[o['id'] for o in cluster],
                  'model_origin':'synthetic-only RF','location_status':'unresolved',
                  'mic_amplitudes':mic_amps,'mic_detected':mic_detected}
        row=dict(event_uid=uid,timestamp=stamp,classification=label,pd_score=decision.get('score'),
                 gap=None,sector=None,location_score=None,uv_inner=0,uv_outer=0,peak=peak,
                 sensor_count=len(cluster),amplitudes=ae_amps,detected=ae_detected,
                 time_quality='SIMULATED_CLOCK',source=source,sequence=sequence,evidence=evidence)
        events.append(row)
        if label=='PD-like':
            best=max(cluster,key=lambda o:(o['score'] or 0)*o['peak'])
            captures[uid]={'event_uid':uid,'fs':best['fs'],'sensor':best['id'],'modality':best['modality'],
                           'samples':best['wave'].tolist(),'timestamp':stamp,'peak':best['peak']}
    return events,captures
