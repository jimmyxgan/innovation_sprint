"""Regression tests for scripted demo baseline, provenance, and fixed 16:9 HMI."""
import sqlite3,tempfile
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
import app

def main():
    with tempfile.TemporaryDirectory() as t:
        with patch.object(app,'DB',Path(t)/'test.sqlite3'):
            app.init_db()
            assert app.status()['condition']['state']=='INSUFFICIENT DATA'
            assert app.seed_demo_baseline()==7
            with sqlite3.connect(app.DB) as db:
                db.row_factory=sqlite3.Row
                c=app.daily_condition(db,datetime.now(timezone.utc))
                assert db.execute('SELECT COUNT(*) FROM events').fetchone()[0]==0
                assert db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]==0
            assert c['state']=='WARNING',c
            assert len(c['days'])==7
            assert abs(c['baseline_pd_per_hour_illustrative']-35/24)<1e-6
            assert all(d['candidates']>=d['pd'] for d in c['days'])
            assert 'SCRIPTED' in c['provenance']
    html=(Path(__file__).parent/'dashboard.html').read_text()
    assert '1920px!important' in html and '1080px!important' in html
    assert 'Math.min(window.innerWidth/1920,window.innerHeight/1080)' in html
    assert 'w.sensor' in html and 'pd_per_hour' in html
    print('PASS: seven-day baseline, honest provenance, sensor waveform label, 16:9')
if __name__=='__main__':main()
