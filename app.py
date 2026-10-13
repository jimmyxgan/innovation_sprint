"""Synthetic PD monitoring HMI. Not a certified station gateway.
[CHALLENGE] Trench Innovation Sprint 2026 pp.10-12: secure, time-stamped trend,
calibration and maintenance decision. This app models the edge READOUT only.
[IEC62478] IEC TS 62478:2016 acoustic PD measurement / sensitivity checks.
[IEC61850] IEC 61850 station integration is SPECIFIED in STANDARDS_MATRIX.md,
not implemented by this local HTTP demonstration.
"""
import argparse,io,json,sqlite3,threading,time,uuid
from contextlib import closing
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
WAVE_CACHE={}
LOCK=threading.Lock()

def init_db():
    with closing(sqlite3.connect(DB)) as db:
        db.execute('''CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_uid TEXT UNIQUE,timestamp TEXT NOT NULL,classification TEXT,pd_score REAL,
        gap INTEGER,sector INTEGER,location_score REAL,uv_inner INTEGER,uv_outer INTEGER,
        peak REAL,sensor_count INTEGER,amplitudes_json TEXT,detected_json TEXT,
        time_quality TEXT,synthetic INTEGER,source TEXT,sequence INTEGER)''')
        db.execute('CREATE INDEX IF NOT EXISTS events_time ON events(timestamp)')
        db.execute('''CREATE TABLE IF NOT EXISTS outbox(event_uid TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,delivered INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0)''')
        db.execute('''CREATE TABLE IF NOT EXISTS demo_daily (
            day TEXT PRIMARY KEY, pd INTEGER NOT NULL, candidates INTEGER NOT NULL,
            monitoring_hours REAL NOT NULL, provenance TEXT NOT NULL)''')
        db.commit()

def add_event(row):
    """Atomic event+outbox insert, store-and-forward demonstration.
    [ASSUMPTION] SQLite WAL + transactional outbox for delivery resilience;
    real deployment requires disk integrity, retention, authenticated transport.
    """
    with closing(sqlite3.connect(DB)) as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('''INSERT OR IGNORE INTO events(event_uid,timestamp,classification,pd_score,
        gap,sector,location_score,uv_inner,uv_outer,peak,sensor_count,
        amplitudes_json,detected_json,time_quality,synthetic,source,sequence)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (row['event_uid'],row['timestamp'],row['classification'],row['pd_score'],
        row['gap'],row['sector'],row['location_score'],row['uv_inner'],row['uv_outer'],
        row['peak'],row['sensor_count'],json.dumps(row['amplitudes']),
        json.dumps(row['detected']),row['time_quality'],1,row['source'],row['sequence']))
        # Accelerated replay is not telemetry and must not enter the delivery queue.
        if row['source']!='synthetic_history':
            db.execute('INSERT OR IGNORE INTO outbox(event_uid,payload_json) VALUES (?,?)',
                       (row['event_uid'],json.dumps({k:v for k,v in row.items() if k!='waveforms'})))
        db.commit()

def process(x,clf,base_time,sequence,truth=None,source='synthetic'):
    obs,envs=observations(x,clf,return_envelopes=True);clusters=fuse(obs,spatial_env=envs)
    for j,e in enumerate(clusters):
        # [ASSUMPTION] In demo only, UTC is based on software wall clock;
        # field implementation requires acquisition hardware PTP (IEC/IEEE 61850-9-3).
        stamp=(base_time+timedelta(seconds=e['sample']/FS)).isoformat(timespec='milliseconds')
        e.update(event_uid=f'{source}-{sequence:010d}-{j:03d}',timestamp=stamp,
                 uv_inner=0,uv_outer=0,time_quality='SIMULATED_CLOCK',
                 source=source,sequence=sequence)
        # UV is explicitly NOT synthesized from acoustic truth: no false corroboration.
        add_event(e)
    # Keep short-lived event waveforms for the presentation. The waveform displayed
    # is associated with the SAME latest PD-like event selected for the reactor map.
    # [ASSUMPTION] Cache is volatile; operational waveform retention requires
    # persistent calibrated captures and a defined storage policy.
    with LOCK:
        for e in clusters:
            if e['classification']=='PD-like' and e['waveforms']:
                sensor=max(e['waveforms'],key=lambda i:float(np.max(np.abs(e['waveforms'][i]))))
                WAVE_CACHE[e['event_uid']]={'event_uid':e['event_uid'],
                    'fs':FS,'sensor':SENSORS[sensor],
                    'samples':e['waveforms'][sensor].tolist(),
                    'timestamp':e['timestamp'],'peak':float(np.max(np.abs(e['waveforms'][sensor])))}
        if len(WAVE_CACHE)>120:
            for uid in list(WAVE_CACHE)[:-120]:WAVE_CACHE.pop(uid,None)
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

def generator(stop,clf,period,scenario,comsol=None,demo=False):
    rng=np.random.default_rng(20261013);sequence=int(time.time());step=0
    while not stop.is_set():
        # DEMO POLICY [ASSUMPTION]: one injected PD source per acquisition cycle,
        # every ~3 seconds. This is a scripted presentation cadence, NOT an
        # experimentally established PD occurrence rate. The detector and RF
        # still determine how many observations/events are actually reported.
        x=(load_comsol_npz(comsol) if comsol else
           make_window(rng,scenario,.65,force_kind='pd')[0] if demo else
           make_window(rng,scenario,min(step/100,1))[0])
        process(x,clf,datetime.now(timezone.utc),sequence,source='comsol_input' if comsol else 'synthetic')
        sequence+=1;step+=1;stop.wait(period)

def daily_condition(db, now):
    """Seven-day condition indicator with explicit demonstration provenance.

    [CHALLENGE] Track B requests a trend and actionable maintenance decision.
    [ASSUMPTION] Four reference days and two comparison days; 2x/3x WATCH/WARNING
    are DEMO choices, NOT IEC 60270 or IEC TS 62478 acceptance criteria.
    Demonstration history is precomputed *illustrative* daily totals, not RF
    output or a field measurement. Never silently combine it with live telemetry.
    """
    end=now.date(); first=end-timedelta(days=6)
    demo=db.execute('SELECT COUNT(*) FROM demo_daily WHERE day>=? AND day<=?',
                    (first.isoformat(),end.isoformat())).fetchone()[0]>=6
    if demo:
        rows=db.execute('SELECT day,pd,candidates,monitoring_hours FROM demo_daily WHERE day>=? AND day<=?',
                        (first.isoformat(),end.isoformat())).fetchall()
        lookup={r['day']:dict(r) for r in rows}
    else:
        rows=db.execute("""SELECT substr(timestamp,1,10) AS day,
            COUNT(*) AS candidates,
            SUM(CASE WHEN classification='PD-like' THEN 1 ELSE 0 END) AS pd
            FROM events WHERE timestamp>=? AND timestamp<?
            GROUP BY substr(timestamp,1,10)""",
            (first.isoformat(),(end+timedelta(days=1)).isoformat())).fetchall()
        lookup={r['day']:dict(r) for r in rows}
    days=[]
    for k in range(7):
        day=(first+timedelta(days=k)).isoformat();r=lookup.get(day,{})
        hours=float(r.get('monitoring_hours') or (24 if demo else 0))
        pd=int(r.get('pd') or 0);candidates=int(r.get('candidates') or 0)
        days.append({'day':day,'label':day[5:],'pd':pd,'candidates':candidates,
                     'monitoring_hours':hours,
                     'pd_per_hour':pd/hours if hours>0 else None})
    reference=days[:4];recent=days[4:6]
    valid=all(d['monitoring_hours']>0 and d['candidates']>0 for d in reference+recent)
    base=(sum(d['pd_per_hour'] for d in reference)/4) if valid else None
    candidate_base=(sum(d['candidates']/d['monitoring_hours'] for d in reference)/4) if valid else None
    recent_rate=sum(d['pd_per_hour'] for d in recent)/2 if valid else None
    recent_candidates=sum(d['candidates']/d['monitoring_hours'] for d in recent)/2 if valid else None
    ratio=recent_rate/base if base and base>0 else None
    sustained=bool(valid and base and all(d['pd_per_hour']>base for d in recent))
    if not valid or not base or base<=0:state='INSUFFICIENT DATA'
    elif sustained and ratio>=3:state='WARNING'
    elif sustained and ratio>=2:state='WATCH'
    elif candidate_base and recent_candidates>=2*candidate_base:state='REVIEW INTERFERENCE'
    else:state='NORMAL'
    action={
      'INSUFFICIENT DATA':'Collect representative baseline monitoring exposure.',
      'NORMAL':'Continue monitoring and review sensor health.',
      'WATCH':'Persistent PD-like increase: review captures and schedule engineering assessment.',
      'WARNING':'Marked sustained PD-like increase: prioritize engineering review; verify with approved diagnostics.',
      'REVIEW INTERFERENCE':'Candidate activity increased: inspect acoustic interference and sensor health.'
    }[state]
    return {'days':days,'baseline_pd_per_hour_illustrative':base,
            'ratio':ratio,'state':state,'advisory':action,
            'provenance':'SCRIPTED DEMO HISTORY (not measured or RF classified)' if demo else 'OBSERVED EVENTS (exposure unknown)',
            'basis':'Illustrative 4-day reference / 2-day comparison; thresholds not field alarms',
            'day_coverage':'Demo history assumes 24 monitoring hours/day; not actual acquisition uptime.' if demo else 'Uptime unavailable: observed rates not validated.'}


def seed_demo_baseline(now=None):
    """Seed an explicit, reproducible presentation fixture (NOT classifier output).

    The scripted values are deliberately NOT passed off as observed RF events.
    [ASSUMPTION] Counts and 24 h/day exposure are invented to illustrate a
    deterioration trajectory. Replace with uptime-normalized field history.
    """
    now=now or datetime.now(timezone.utc)
    pd_counts=[32,36,34,38,82,138,176]
    candidate_counts=[110,118,115,123,185,245,292]
    with closing(sqlite3.connect(DB)) as db:
        db.execute('DELETE FROM demo_daily')
        for i,(pd,candidates) in enumerate(zip(pd_counts,candidate_counts)):
            day=(now.date()-timedelta(days=6-i)).isoformat()
            db.execute('INSERT INTO demo_daily VALUES (?,?,?,?,?)',
                       (day,pd,candidates,24.0,'SCRIPTED_ILLUSTRATIVE'))
        db.commit()
    return len(pd_counts)


def status():
    with closing(sqlite3.connect(DB)) as db:
        db.row_factory=sqlite3.Row
        recent=[dict(r) for r in db.execute("SELECT * FROM events WHERE source!='synthetic_history' ORDER BY timestamp DESC LIMIT 100")]
        now=datetime.now(timezone.utc)
        # [ASSUMPTION] Demo accelerated-time visualization uses last 120 s;
        # operational rate is explicitly events/hour over rolling 1-hour windows.
        trends=[]
        for j in range(11,-1,-1):
            end=now-timedelta(seconds=j*10);start=end-timedelta(seconds=10)
            r=db.execute('''SELECT COUNT(*) AS n,
              SUM(CASE WHEN classification='PD-like' THEN 1 ELSE 0 END) AS pd,
              MAX(peak) AS peak FROM events WHERE timestamp>=? AND timestamp<? AND source!='synthetic_history' ''',
              (start.isoformat(timespec='milliseconds'),end.isoformat(timespec='milliseconds'))).fetchone()
            trends.append({'label':end.strftime('%H:%M:%S'),'candidates':r['n'] or 0,
                           'pd':r['pd'] or 0,'peak':round(r['peak'] or 0,4)})
        hour=now-timedelta(hours=1)
        rates=db.execute('''SELECT COUNT(*) AS total,
            SUM(CASE WHEN classification='PD-like' THEN 1 ELSE 0 END) AS pd,
            SUM(CASE WHEN classification='Uncertain' THEN 1 ELSE 0 END) AS uncertain
            FROM events WHERE timestamp>=? AND source!='synthetic_history' ''',(hour.isoformat(timespec='milliseconds'),)).fetchone()
        hourly=db.execute('''SELECT strftime('%Y-%m-%dT%H:00:00',timestamp) AS hour,
            COUNT(*) AS candidates, SUM(CASE WHEN classification='PD-like' THEN 1 ELSE 0 END) AS pd,
            MAX(peak) AS peak FROM events GROUP BY hour ORDER BY hour DESC LIMIT 48''').fetchall()
        condition=daily_condition(db,now)
        queue=db.execute("SELECT COUNT(*) FROM outbox WHERE delivered=0 AND event_uid NOT LIKE 'synthetic_history-%'").fetchone()[0]
        score_rows=db.execute("SELECT pd_score FROM events WHERE source!='synthetic_history' AND pd_score IS NOT NULL ORDER BY timestamp DESC LIMIT 1000").fetchall()
        scores=[float(r[0]) for r in score_rows]
        score_hist=np.histogram(scores,bins=[0,.25,.4,.6,.75,1.00001])[0].tolist()
        regions=[dict(r) for r in db.execute('''SELECT gap,sector,COUNT(*) AS n FROM events
            WHERE classification='PD-like' AND gap IS NOT NULL GROUP BY gap,sector ORDER BY n DESC''')]
    for r in recent:
        r['amplitudes']=json.loads(r.pop('amplitudes_json'))
        r['detected']=json.loads(r.pop('detected_json'))
    # The waveform and sensor map MUST refer to the same most recent PD-like event.
    latest=next((r for r in recent if r['classification']=='PD-like'),None)
    if latest is None:latest=next((r for r in recent if r['classification']=='Uncertain'),None)
    n_pd=int(rates['pd'] or 0);n_c=int(rates['total'] or 0)
    state=condition['state']
    advisory=f"{condition['advisory']} Demo thresholds; not a field alarm."
    return {'synthetic':True,'generated_utc':now.isoformat(),'time_quality':'SIMULATED_CLOCK',
            'sensors':SENSORS,'uv_sensors':['UV-INNER','UV-OUTER'],
            'latest':latest,'events':recent[:60],'trends':trends,'regions':regions,'score_diagnostics':{'bins':['0-.25','.25-.40','.40-.60','.60-.75','.75-1'],'counts':score_hist,'n':len(scores)},
            'hourly':[dict(r) for r in reversed(hourly)],'condition':condition,
            'stats':{'events':n_c,'pd':n_pd,'uncertain':int(rates['uncertain'] or 0)},
            'network_status':f'LOCAL HTTP · {queue} PENDING',
            'advisory':f'{state}: {advisory}',
            'station':{'ptp':'NOT CONNECTED','iec61850':'NOT IMPLEMENTED','tls':'NOT IMPLEMENTED',
                       'outbox_pending':queue,'time_quality':'SIMULATED_CLOCK'}}

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*a,**kw):super().__init__(*a,directory=str(ROOT),**kw)
    def do_GET(self):
        p=urlparse(self.path).path
        if p=='/':self.send_response(302);self.send_header('Location','/dashboard.html');self.end_headers();return
        if p in ['/api/status','/api/hourly','/api/waveform']:
            if p=='/api/status': payload=status()
            elif p=='/api/hourly': payload=status()['hourly']
            else:
                current=status()['latest']
                uid=current['event_uid'] if current and current['classification']=='PD-like' else None
                with LOCK: payload=dict(WAVE_CACHE.get(uid,{}))
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
    p.add_argument('--period',type=float,default=None,help='Seconds between acquisition windows (demo default: 3.0)')
    p.add_argument('--demo',action='store_true',help='One injected synthetic PD approximately every 3 seconds, plus illustrative seven-day baseline')
    p.add_argument('--reset-demo-db',action='store_true',help='Delete ONLY this demo SQLite DB before running')
    p.add_argument('--scenario',choices=['nominal','high_noise','sensor_shift','spectral_shift'],default='nominal')
    p.add_argument('--comsol-npz',type=Path,default=None)
    p.add_argument('--seed-only',action='store_true')
    p.add_argument('--seed-history',action='store_true',help='Insert clearly labeled synthetic 7-day demo history once')
    p.add_argument('--no-ml',action='store_true',help='Run conventional detection only')
    args=p.parse_args()
    if args.reset_demo_db and DB.exists(): DB.unlink()
    if args.period is None:args.period=3.0 if args.demo else 2.5
    init_db()
    clf=None if args.no_ml else train_rf()[0]
    if args.demo or args.seed_history:
        print('Seeded SCRIPTED illustrative daily baseline:',seed_demo_baseline(),'days',flush=True)
    # --seed-history remains an alias for demo history for backward compatibility.
    rng=np.random.default_rng(8)
    if not args.demo:
        for k in range(3):
            x=load_comsol_npz(args.comsol_npz) if args.comsol_npz else make_window(rng,args.scenario,.25*k)[0]
            process(x,clf,datetime.now(timezone.utc),int(time.time())+k)
    # Demo skips startup burst: the first controlled PD arrives in the generator.
    if args.seed_only:print('Seeded',DB);return
    stop=threading.Event()
    th=threading.Thread(target=generator,args=(stop,clf,args.period,args.scenario,args.comsol_npz,args.demo),daemon=True)
    th.start();srv=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    print(f'Open http://localhost:{args.port}/ via VS Code Ports forwarding',flush=True)
    try:srv.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();srv.server_close()
if __name__=='__main__':main()
