"""Synthetic acoustic/UV PD monitor prototype. NOT validated PD measurement or IEC-certified."""
import argparse, json, math, sqlite3, threading, time, ssl
from pathlib import Path
from datetime import datetime, timezone, timedelta
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse
import numpy as np
from scipy.signal import butter, sosfiltfilt, hilbert
from sklearn.ensemble import RandomForestClassifier

ROOT=Path(__file__).resolve().parent
DB=ROOT/'monitor.sqlite3'
SENSORS=['AE-T1','AE-T2','AE-B1','AE-B2']
RINGS=4
FS=100_000
DURATION=.20

def features(w,fs=FS):
    w=np.asarray(w,dtype=float)
    peak=float(np.max(np.abs(w)))+1e-12
    rms=float(np.sqrt(np.mean(w*w)))+1e-12
    env=np.abs(hilbert(w))
    mask=env>0.25*env.max()
    dur=float(mask.sum()/fs)
    rise=float((np.argmax(env)-np.argmax(env>0.1*env.max()))/fs)
    p=np.abs(np.fft.rfft(w*np.hanning(len(w))))**2
    freq=np.fft.rfftfreq(len(w),1/fs)
    p=p/(p.sum()+1e-12)
    centroid=float((freq*p).sum())
    bandwidth=float(np.sqrt(((freq-centroid)**2*p).sum()))
    entropy=float(-(p*np.log(p+1e-15)).sum())
    high=float(p[freq>20000].sum())
    return [peak,rms,peak/rms,dur,max(0,rise),centroid,bandwidth,entropy,high]

def pulse(rng,kind,n=512,fs=FS):
    t=np.arange(n)/fs
    center=.0017
    if kind=='pd':
        f=rng.uniform(19_000,36_000);decay=rng.uniform(.00022,.00065)
        s=np.where(t>=center,np.exp(-(t-center)/decay)*np.sin(2*np.pi*f*(t-center)),0.)
    elif kind=='impact':
        f=rng.uniform(4_000,15_000);decay=rng.uniform(.0005,.0018)
        s=np.where(t>=center,np.exp(-(t-center)/decay)*np.sin(2*np.pi*f*(t-center)),0.)
    else:
        f=rng.uniform(400,2_000)
        s=np.sin(2*np.pi*f*t)*np.exp(-((t-center)/.0013)**2)
    return s

def train_classifier(seed=20):
    rng=np.random.default_rng(seed); X=[]; y=[]
    for k in ('pd','impact','vibration'):
        for _ in range(170):
            amp=rng.uniform(.25,1.5)
            noise=rng.normal(0,rng.uniform(.015,.12),512)
            X.append(features(amp*pulse(rng,k)+noise));y.append(1 if k=='pd' else 0)
    clf=RandomForestClassifier(n_estimators=110,min_samples_leaf=3,random_state=seed,n_jobs=-1)
    clf.fit(X,y)
    return clf

def init_db():
    with sqlite3.connect(DB) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS events (
          id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT NOT NULL,
          sensor TEXT, amplitude REAL, dominant_khz REAL, snr_db REAL,
          classification TEXT, pd_score REAL, ring INTEGER, ring_confidence REAL,
          uv_observed INTEGER, time_quality TEXT, waveform TEXT, synthetic INTEGER DEFAULT 1)''')
        db.execute('CREATE INDEX IF NOT EXISTS idx_events_time ON events(timestamp)')
        db.commit()

def detect_candidates(x,fs=FS):
    sos=butter(4,[15_000,42_000],btype='bandpass',fs=fs,output='sos')
    filtered=sosfiltfilt(sos,x)
    env=np.abs(hilbert(filtered))
    # Robust estimate: lower 65% envelope, avoids contamination from transient bursts.
    quiet=env[env<=np.quantile(env,.65)]
    med=np.median(quiet);mad=np.median(np.abs(quiet-med))
    threshold=max(med+8*1.4826*mad,.035)
    peaks=np.flatnonzero((env[1:-1]>env[:-2])&(env[1:-1]>=env[2:])&(env[1:-1]>threshold))+1
    chosen=[]; last=-10**9
    for p in peaks:
        if p-last>=int(.004*fs):chosen.append(int(p));last=p
    return filtered,env,threshold,chosen

def simulate_window(rng,step):
    n=int(FS*DURATION)
    t=np.arange(n)/FS
    # Region 2 develops increasing synthetic activity; other sources possible.
    true_ring=2 if rng.random()<.85 else int(rng.integers(1,5))
    rate=1+min(step/24,5)
    n_pulses=int(rng.poisson(rate))
    x=np.zeros((len(SENSORS),n))
    for si in range(len(SENSORS)):
        x[si]=rng.normal(0,.018,n)+.009*np.sin(2*np.pi*120*t+si*.5)
    # Arbitrary demonstration response matrix, NOT a calibrated reactor propagation model.
    gain=np.array([[.95,.55,.30,.18],[.60,.92,.53,.25],[.25,.52,.95,.58],[.17,.30,.61,.94]])
    ground=[]
    for _ in range(n_pulses):
        start=int(rng.integers(700,n-900)); kind='pd' if rng.random()<.77 else 'impact'
        base=pulse(rng,kind,512)
        amp=rng.uniform(.20,.65)*(1+.12*min(step/24,5))
        for si in range(4):
            delay=si*3+(true_ring-1)*2
            idx=start+delay
            x[si,idx:idx+512]+=base*amp*gain[si,true_ring-1]
        ground.append({'sample':start,'kind':kind,'ring':true_ring})
    return x,ground,gain

def process_window(rng,clf,step):
    x,ground,gain=simulate_window(rng,step)
    observations=[]; processed=[]
    for si,sensor in enumerate(SENSORS):
        filtered,env,threshold,peaks=detect_candidates(x[si])
        processed.append((filtered,env,threshold,peaks))
        for p in peaks:
            lo=max(0,p-180);hi=min(len(filtered),p+332)
            seg=filtered[lo:hi]
            if len(seg)<512:seg=np.pad(seg,(0,512-len(seg)))
            feat=features(seg)
            score=float(clf.predict_proba([feat])[0,1])
            cls='PD-like' if score>=.75 else ('Interference-like' if score<=.25 else 'Uncertain')
            snr=20*np.log10(max(feat[0],1e-8)/max(threshold,1e-8))
            observations.append({'sensor':sensor,'sample':p,'amplitude':round(feat[0],4),
                'dominant_khz':round(float(np.fft.rfftfreq(512,1/FS)[np.argmax(np.abs(np.fft.rfft(seg)))])/1000,2),
                'snr_db':round(float(snr),1),'classification':cls,'pd_score':round(score,3),
                'waveform':np.round(seg[::8],4).tolist()})
    # Cluster detections in a 1 ms window across acoustic channels.
    observations.sort(key=lambda o:o['sample']); clusters=[]
    for o in observations:
        if not clusters or o['sample']-clusters[-1][0]['sample']>100:clusters.append([o])
        else:clusters[-1].append(o)
    now=datetime.now(timezone.utc)
    rows=[]
    for ci,cluster in enumerate(clusters):
        amplitudes={o['sensor']:o['amplitude'] for o in cluster}
        measured=np.array([amplitudes.get(s,0) for s in SENSORS])
        # Confidence from amplitude template matching; only illustrative synthetic calibration.
        norm=np.linalg.norm(measured)
        if norm<1e-9: continue
        sims=np.array([np.dot(measured,gain[:,r])/(norm*np.linalg.norm(gain[:,r])) for r in range(4)])
        best=int(np.argmax(sims)); order=np.sort(sims)
        margin=float(order[-1]-order[-2]); confidence=float(np.clip(margin*6,0,.95))
        estimated_ring=best+1 if len(amplitudes)>=2 and confidence>=.18 else None
        # Synthetic UV detection only for an externally visible fraction of discharges.
        uv=bool(rng.random()<.22 and any(o['classification']=='PD-like' for o in cluster))
        for o in cluster:
            stamp=(now+timedelta(microseconds=int(o['sample']/FS*1e6))).isoformat(timespec='milliseconds')
            rows.append((stamp,o['sensor'],o['amplitude'],o['dominant_khz'],o['snr_db'],o['classification'],o['pd_score'],estimated_ring,round(confidence,3),int(uv),'SIMULATED_SYNC',json.dumps(o['waveform']),1))
    with sqlite3.connect(DB) as db:
        db.executemany('''INSERT INTO events(timestamp,sensor,amplitude,dominant_khz,snr_db,classification,pd_score,ring,ring_confidence,uv_observed,time_quality,waveform,synthetic) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',rows)
        db.execute('DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 3000)')
        db.commit()
    return len(rows)

def get_data():
    with sqlite3.connect(DB) as db:
        db.row_factory=sqlite3.Row
        rows=[dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 300')]
    now=datetime.now(timezone.utc)
    # Accelerated demo trend: 12 bins of 10-second live acquisition, labeled demo rate.
    trends=[]
    for j in range(11,-1,-1):
        start=now-timedelta(seconds=(j+1)*10);end=now-timedelta(seconds=j*10)
        subset=[r for r in rows if start.isoformat()<=r['timestamp']<end.isoformat()]
        pd=[r for r in subset if r['classification']=='PD-like']
        trends.append({'label':(start+timedelta(seconds=10)).strftime('%H:%M:%S'),
                       'candidates':len(subset),'pd':len(pd),
                       'intensity':round(float(np.percentile([r['amplitude'] for r in pd],95)),3) if pd else 0})
    pd=[r for r in rows if r['classification']=='PD-like']
    rings={str(i):{'events':sum(1 for r in pd if r['ring']==i),'mean_confidence':round(float(np.mean([r['ring_confidence'] for r in pd if r['ring']==i])),2) if any(r['ring']==i for r in pd) else 0} for i in range(1,5)}
    dominant=max(range(1,5),key=lambda i:rings[str(i)]['events']) if pd else None
    if dominant and rings[str(dominant)]['events']<3:dominant=None
    return {'synthetic':True,'generated_utc':now.isoformat(),'time_quality':'SIMULATED_SYNC',
            'events':rows[:80],'trends':trends,'rings':rings,'suspected_ring':dominant,
            'stats':{'candidates':len(rows),'pd':len(pd),'uncertain':sum(r['classification']=='Uncertain' for r in rows),
                     'uv':sum(r['uv_observed'] for r in rows)},'network_status':'LOCAL DEMO',
            'advisory':'Review persistent PD-like activity; localization is illustrative only.' if dominant else 'Collecting baseline; no validated location available.'}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(ROOT),**kwargs)
    def do_GET(self):
        if urlparse(self.path).path=='/api/status':
            b=json.dumps(get_data()).encode()
            self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
        else:super().do_GET()
    def log_message(self,fmt,*args):pass

def generator(stop,period):
    rng=np.random.default_rng(2026);clf=train_classifier();step=0
    while not stop.is_set():
        process_window(rng,clf,step);step+=1;stop.wait(period)

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=8765);p.add_argument('--period',type=float,default=2.5);p.add_argument('--seed-only',action='store_true');args=p.parse_args()
    init_db();rng=np.random.default_rng(2026);clf=train_classifier()
    for i in range(24):process_window(rng,clf,i*5)
    if args.seed_only:print('Database seeded:',DB);return
    stop=threading.Event();threading.Thread(target=generator,args=(stop,args.period),daemon=True).start()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Open http://127.0.0.1:{args.port}/dashboard.html  (Ctrl+C to stop)')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close()
if __name__=='__main__':main()
