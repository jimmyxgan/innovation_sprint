"""Conventional candidate detector, optional Random Forest, conservative fusion.

REFERENCES:
[IEC62478] IEC TS 62478:2016, acoustic measurements and PD location/sensitivity.
[SciPy] scipy.signal butter/sosfiltfilt/hilbert/find_peaks documentation.
[RF] Breiman, L. (2001), Random Forests, Machine Learning 45:5-32,
 https://doi.org/10.1023/A:1010933404324
[ROBUST] Hampel, F.R. (1974), The Influence Curve and Its Role in Robust
 Estimation, JASA 69(346):383-393. Median/MAD robustness motivation.
[ASSUMPTION] All numerical thresholds, cluster widths, templates and event
 classes are prototype engineering choices, not mandated by IEC.
"""
import numpy as np
from scipy.signal import sosfiltfilt,hilbert,find_peaks
from sklearn.ensemble import RandomForestClassifier
from physics import FS,SOS,template,pulse

def extract_features(w):
    w=np.asarray(w,float); env=np.abs(hilbert(w)); peak=np.max(np.abs(w))+1e-12
    rms=np.sqrt(np.mean(w*w))+1e-12
    mask=env>.25*max(env.max(),1e-12)  # [ASSUMPTION] 25% envelope duration
    power=np.abs(np.fft.rfft(w*np.hanning(len(w))))**2
    freq=np.fft.rfftfreq(len(w),1/FS); power/=power.sum()+1e-12
    c=float((freq*power).sum()); bw=float(np.sqrt((((freq-c)**2)*power).sum()))
    onset=int(np.argmax(env>.1*max(env.max(),1e-12)))
    rise=max(0,(int(np.argmax(env))-onset)/FS)
    # [ASSUMPTION] features standard DSP descriptors; not IEC-prescribed PD labels.
    return [float(peak),float(rms),float(peak/rms),float(mask.sum()/FS),rise,
            c,bw,float(-(power*np.log(power+1e-15)).sum()),float(power[freq>20e3].sum())]

def detect(x,noise_multiplier=8.0):
    # [IEC62478] frequency filtering and pulse detection are compatible with acoustic methods;
    # [ASSUMPTION] 4th order, 14-43 kHz band and threshold coefficients are design choices.
    y=sosfiltfilt(SOS,x); env=np.abs(hilbert(y))
    quiet=env[env<=np.quantile(env,.65)]
    med=np.median(quiet); mad=np.median(np.abs(quiet-med))
    # [ROBUST] 1.4826*MAD estimates Gaussian sigma; [ASSUMPTION] k=8, floor=.025 V.
    threshold=max(float(med+noise_multiplier*1.4826*mad),.025)
    peaks,_=find_peaks(env,height=threshold,distance=int(.003*FS),prominence=.5*threshold)
    return y,env,threshold,peaks

def train_rf(seed=42,scenario='nominal',examples_per_class=220):
    """Train on DETECTED windows, not pristine isolated signals.
    [ASSUMPTION] Synthetic generator, class priors and augmentation are not field labels.
    """
    from physics import sensor_transfer
    rng=np.random.default_rng(seed); X=[];Y=[]
    # Training uses short acquisition buffers and the SAME detector as inference.
    # [ASSUMPTION] noise levels and perturbations below are not measured reactor data.
    for kind in ['pd','impact','vibration']:
        for _ in range(examples_per_class):
            n=4096;t=np.arange(n)/FS
            noise=rng.uniform(.008,.045) if scenario=='nominal' else rng.uniform(.02,.08)
            raw=rng.normal(0,noise,n)+rng.uniform(.003,.012)*np.sin(2*np.pi*120*t)
            w=pulse(rng,kind)
            if rng.random()<.25:w=sensor_transfer(w,cutoff=rng.uniform(24e3,43e3))
            start=1500;raw[start:start+len(w)]+=rng.uniform(.2,.8)*w
            filtered,env,th,peaks=detect(raw)
            if len(peaks)==0:continue
            p=min(peaks,key=lambda q:abs(int(q)-(start+100)))
            if abs(int(p)-(start+100))>250:continue
            lo=int(p)-110
            if lo<0 or lo+512>len(filtered):continue
            X.append(extract_features(filtered[lo:lo+512]));Y.append(int(kind=='pd'))
    if len(set(Y))<2: raise RuntimeError('Synthetic training failed to capture both classes')
    clf=RandomForestClassifier(n_estimators=120,min_samples_leaf=4,
                               class_weight='balanced',random_state=seed,n_jobs=1)
    clf.fit(X,Y)
    return clf,{'samples':len(Y),'pd':sum(Y),'interference':len(Y)-sum(Y)}

def observations(x,clf=None):
    obs=[]
    for i in range(x.shape[0]):
        y,env,th,peaks=detect(x[i])
        for p in peaks:
            lo=int(p)-110
            if lo<0 or lo+512>len(y):continue
            w=y[lo:lo+512]; feat=extract_features(w)
            score=float(clf.predict_proba([feat])[0,1]) if clf is not None else None
            obs.append({'sample':int(p),'sensor_index':i,'amplitude':feat[0],
                        'pd_score':score,'waveform':w})
    return obs

def fuse(obs,tolerance_samples=130):
    """[ASSUMPTION] 1.3 ms coincidence grouping; must be replaced by calibrated
    maximum acoustic travel-time and verified for multiple simultaneous sources.
    """
    clusters=[]
    for o in sorted(obs,key=lambda a:a['sample']):
        if not clusters or o['sample']-clusters[-1][-1]['sample']>tolerance_samples:
            clusters.append([o])
        else:clusters[-1].append(o)
    out=[]
    for cluster in clusters:
        by={}
        for o in cluster:
            i=o['sensor_index']
            if i not in by or o['amplitude']>by[i]['amplitude']:by[i]=o
        amps=np.array([by[i]['amplitude'] if i in by else 0 for i in range(16)])
        scores=[o['pd_score'] for o in by.values() if o['pd_score'] is not None]
        score=float(np.median(scores)) if scores else None
        cls=('Candidate / no ML' if score is None else
             'PD-like' if score>=.75 else 'Interference-like' if score<=.25 else 'Uncertain')
        g,s,margin=localize(amps)
        out.append({'sample':int(np.median([o['sample'] for o in by.values()])),
                    'classification':cls,'pd_score':score,'gap':g,'sector':s,
                    'location_score':margin,'amplitudes':amps.tolist(),
                    'detected':[i in by for i in range(16)],'sensor_count':len(by),
                    'peak':float(max(amps)), 'waveforms':{i:o['waveform'] for i,o in by.items()}})
    return out

def localize(amps):
    amps=np.asarray(amps,float)
    if np.count_nonzero(amps)<3 or np.linalg.norm(amps)==0:return None,None,0.
    scores=[]
    for g in range(4):
        for s in range(4):
            expected,_=template(g,s)
            scores.append(float(np.dot(amps,expected)/(np.linalg.norm(amps)*np.linalg.norm(expected))))
    ranking=np.argsort(scores);best=int(ranking[-1]);runner=int(ranking[-2]);margin=scores[best]-scores[runner]
    # [ASSUMPTION] .72 cosine score and .005 margin are NOT confidence probabilities.
    if scores[best]<.72 or margin<.005:return None,None,float(max(0,margin))
    return best//4+1,best%4+1,float(margin)
