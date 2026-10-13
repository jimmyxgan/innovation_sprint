"""Synthetic PD monitoring HMI. Not a certified station gateway.
[CHALLENGE] Trench Innovation Sprint 2026 pp.10-12: secure, time-stamped trend,
calibration and maintenance decision. This app models the edge READOUT only.
[IEC62478] IEC TS 62478:2016 acoustic PD measurement / sensitivity checks.
[IEC61850] IEC 61850 station integration is SPECIFIED in STANDARDS_MATRIX.md,
not implemented by this local HTTP demonstration.
"""
import argparse,io,json,sqlite3,threading,time
from datetime import datetime,timezone,timedelta
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
import numpy as np
from physics import FS,SENSORS,make_window
from processing import train_rf,observations,fuse
ROOT=Path(__file__).resolve().parent
DB=ROOT/'monitor.sqlite3'
LATEST_WAVE={}
LOCK=threading.Lock()

def init_db():
    with sqlite3.connect(DB) as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('''CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_uid TEXT UNIQUE,timestamp TEXT NOT NULL,classification TEXT,pd_score REAL,
        gap INTEGER,sector INTEGER,location_score REAL,uv_inner INTEGER,uv_outer INTEGER,
        peak REAL,sensor_count INTEGER,amplitudes_json TEXT,detected_json TEXT,
        time_quality TEXT,synthetic INTEGER,source TEXT,sequence INTEGER)''')
        # CREATE TABLE IF NOT EXISTS does not upgrade databases from earlier demos.
        columns={row[1] for row in db.execute('PRAGMA table_info(events)')}
        for name,kind in [('event_uid','TEXT'),('source','TEXT'),('sequence','INTEGER')]:
            if name not in columns:
                db.execute(f'ALTER TABLE events ADD COLUMN {name} {kind}')
        # Keep historical events identifiable without inventing acquisition metadata.
        db.execute("UPDATE events SET event_uid='legacy-' || id WHERE event_uid IS NULL")
        db.execute('CREATE UNIQUE INDEX IF NOT EXISTS events_uid ON events(event_uid)')
        db.execute('CREATE INDEX IF NOT EXISTS events_time ON events(timestamp)')
        db.execute('''CREATE TABLE IF NOT EXISTS outbox(event_uid TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0)''')
        db.commit()

def add_event(row):
    """Atomic event+outbox insert, store-and-forward demonstration.
    [ASSUMPTION] SQLite WAL + transactional outbox for delivery resilience;
    real deployment requires disk integrity, retention, authenticated transport.
    """
    with sqlite3.connect(DB) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''INSERT OR IGNORE INTO events(event_uid,timestamp,classification,pd_score,
        gap,sector,location_score,uv_inner,uv_outer,peak,sensor_count,
        amplitudes_json,detected_json,time_quality,synthetic,source,sequence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (row['event_uid'],row['timestamp'],row['classification'],row['pd_score'],
        row['gap'],row['sector'],row['location_score'],row['uv_inner'],row['uv_outer'],
        row['peak'],row['sensor_count'],json.dumps(row['amplitudes']),
        json.dumps(row['detected']),row['time_quality'],1,row['source'],row['sequence']))
        db.execute('INSERT OR IGNORE INTO outbox(event_uid,payload_json) VALUES (?,?)',
                   (row['event_uid'],json.dumps({k:v for k,v in row.items() if k!='waveforms'})))
        db.commit()

def process(x,clf,base_time,sequence,truth=None,source='synthetic'):
    obs=observations(x,clf);clusters=fuse(obs)
    for j,e in enumerate(clusters):
        # [ASSUMPTION] In demo only, UTC is based on software wall clock;
        # field implementation requires acquisition hardware PTP (IEC/IEEE 61850-9-3).
        stamp=(base_time+timedelta(seconds=e['sample']/FS)).isoformat(timespec='milliseconds')
        e.update(event_uid=f'{sequence:010d}-{j:03d}',timestamp=stamp,
                 uv_inner=0,uv_outer=0,time_quality='SIMULATED_CLOCK',
                 source=source,sequence=sequence)
        # UV is explicitly NOT synthesized from acoustic truth: no false corroboration.
        add_event(e)
    with LOCK:
        if clusters:
            LATEST_WAVE.clear()
            LATEST_WAVE.update({'event_uid':clusters[-1]['event_uid'],
                                'fs':FS,'samples':{str(i):w.tolist() for i,w in clusters[-1]['waveforms'].items()}})
    return len(clusters)

def load_comsol_npz(path):
    """Interface for COMSOL/team simulation output.
    NPZ keys: signals (16,n_samples), fs (100000), optional sensor_ids.
    NO fabricated transfer functions or acoustic calibration are inferred.
    """
    d=np.load(path,allow_pickle=False)
    x=np.asarray(d['signals'],float);fs=int(d['fs'])
    if x.ndim!=2 or x.shape[0]!=16 or x.shape[1]<512:raise ValueError('Expected signals shape (16, N>=512)')
    if fs!=FS:raise ValueError(f'Expected fs={FS}; resample externally with anti-alias filtering')
    if 'sensor_ids' in d and list(d['sensor_ids'].astype(str))!=SENSORS:
        raise ValueError('sensor_ids order does not match SENSORS')
    return x

def generator(stop,clf,period,scenario,comsol=None):
    rng=np.random.default_rng(20261013);sequence=int(time.time());step=0
    while not stop.is_set():
        x=load_comsol_npz(comsol) if comsol else make_window(rng,scenario,min(step/100,1))[0]
        process(x,clf,datetime.now(timezone.utc),sequence,source='comsol_input' if comsol else 'synthetic')
        sequence+=1;step+=1;stop.wait(period)

def status():
    with sqlite3.connect(DB) as db:
        db.row_factory=sqlite3.Row
        recent=[dict(r) for r in db.execute('SELECT * FROM events ORDER BY id DESC LIMIT 100')]
        now=datetime.now(timezone.utc)
        # [ASSUMPTION] Demo accelerated-time visualization uses last 120 s;
        # operational rate is explicitly events/hour over rolling 1-hour windows.
        trends=[]
        for j in range(11,-1,-1):
            end=now-timedelta(seconds=j*10);start=end-timedelta(seconds=10)
            r=db.execute('''SELECT COUNT(*) AS n,
              SUM(CASE WHEN classification='PD-like' THEN 1 ELSE 0 END) AS pd,
              MAX(peak) AS peak FROM events WHERE timestamp>=? AND timestamp<?''',
              (start.isoformat(timespec='milliseconds'),end.isoformat(timespec='milliseconds'))).fetchone()
            trends.append({'label':end.strftime('%H:%M:%S'),'candidates':r['n'] or 0,
                           'pd':r['pd'] or 0,'peak':round(r['peak'] or 0,4)})
        hour=now-timedelta(hours=1)
        rates=db.execute('''SELECT COUNT(*) AS total,
            SUM(CASE WHEN classification='PD-like' THEN 1 ELSE 0 END) AS pd,
            SUM(CASE WHEN classification='Uncertain' THEN 1 ELSE 0 END) AS uncertain
            FROM events WHERE timestamp>=?''',(hour.isoformat(timespec='milliseconds'),)).fetchone()
        hourly=db.execute('''SELECT strftime('%Y-%m-%dT%H:00:00',timestamp) AS hour,
            COUNT(*) AS candidates, SUM(CASE WHEN classification='PD-like' THEN 1 ELSE 0 END) AS pd,
            MAX(peak) AS peak FROM events GROUP BY hour ORDER BY hour DESC LIMIT 48''').fetchall()
        queue=db.execute('SELECT COUNT(*) FROM outbox WHERE delivered=0').fetchone()[0]
        regions=[dict(r) for r in db.execute('''SELECT gap,sector,COUNT(*) AS n FROM events
            WHERE classification='PD-like' AND gap IS NOT NULL GROUP BY gap,sector ORDER BY n DESC''')]
    for r in recent:
        r['amplitudes']=json.loads(r.pop('amplitudes_json'))
        r['detected']=json.loads(r.pop('detected_json'))
    # HMI map highlights latest PD-like event, NOT interference.
    latest=next((r for r in recent if r['classification']=='PD-like'),None)
    if latest is None:latest=next((r for r in recent if r['classification']=='Uncertain'),None)
    # [ASSUMPTION] Alert thresholds are illustrative and must be set from baseline,
    # load, environment and approved maintenance policy; not an IEC PD limit.
    n_pd=int(rates['pd'] or 0);n_c=int(rates['total'] or 0)
    state='WATCH' if n_pd>=15 else 'NORMAL'
    if n_pd>=40:state='WARNING'
    if n_c>=80 and n_pd<15:state='REVIEW INTERFERENCE'
    advisory={'NORMAL':'Continue trending; no diagnostic claim from synthetic data.',
      'WATCH':'Review rising PD-like event activity; compare against baseline.',
      'WARNING':'Engineering review recommended; verify sensors and operating context.',
      'REVIEW INTERFERENCE':'High acoustic candidate activity; inspect interference/sensor health.'}[state]
    return {'synthetic':True,'generated_utc':now.isoformat(),'time_quality':'SIMULATED_CLOCK',
            'sensors':SENSORS,'uv_sensors':['UV-INNER','UV-OUTER'],
            'latest':latest,'events':recent[:60],'trends':trends,'regions':regions,
            'hourly':[dict(r) for r in reversed(hourly)],
            'stats':{'events':n_c,'pd':n_pd,'uncertain':int(rates['uncertain'] or 0)},
            'network_status':f'LOCAL HTTP · {queue} PENDING',
            'advisory':f'{state}: {advisory} Synthetic demo; not a field alarm.',
            'station':{'ptp':'NOT CONNECTED','iec61850':'NOT IMPLEMENTED','tls':'NOT IMPLEMENTED',
                       'outbox_pending':queue,'time_quality':'SIMULATED_CLOCK'}}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=='/':self.send_response(302);self.send_header('Location','/dashboard.html');self.end_headers();return
        if p in ['/api/status','/api/hourly','/api/waveform']:
            payload=status() if p=='/api/status' else status()['hourly'] if p=='/api/hourly' else dict(LATEST_WAVE)
            b=json.dumps(payload).encode();self.send_response(200);self.send_header('Content-Type','application/json')
            self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)))
            self.end_headers();self.wfile.write(b);return
        # Whitelist only public assets; no source/database/config exposure.
        if p not in ['/dashboard.html']:
            self.send_error(403);return
        super().do_GET()
    def log_message(self,*args):pass

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--period',type=float,default=2.5)
    p.add_argument('--scenario',choices=['nominal','high_noise','sensor_shift','spectral_shift'],default='nominal')
    p.add_argument('--comsol-npz',type=Path,default=None)
    p.add_argument('--seed-only',action='store_true')
    p.add_argument('--no-ml',action='store_true',help='Run conventional detection only')
    args=p.parse_args();init_db()
    clf=None if args.no_ml else train_rf()[0]
    rng=np.random.default_rng(8)
    for k in range(3):
        x=load_comsol_npz(args.comsol_npz) if args.comsol_npz else make_window(rng,args.scenario,.25*k)[0]
        process(x,clf,datetime.now(timezone.utc),int(time.time())+k)
    if args.seed_only:print('Seeded',DB);return
    stop=threading.Event()
    th=threading.Thread(target=generator,args=(stop,clf,args.period,args.scenario,args.comsol_npz),daemon=True)
    th.start();srv=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Open http://localhost:{args.port}/ via VS Code Ports forwarding',flush=True)
    try:srv.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();srv.server_close()
if __name__=='__main__':main()
