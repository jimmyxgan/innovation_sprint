"""Offline queue and recovery demo, NOT an encrypted IEC 61850 transport.
[CHALLENGE] Trench 2026 p.11: integrity-protected communication and station output.
[ASSUMPTION] Transactional outbox with idempotent UID is an engineering pattern;
actual authenticated station acknowledgements and key management are pending.
"""
import argparse,sqlite3
from app import DB,init_db

def run(connected=False):
    init_db()
    with sqlite3.connect(DB) as db:
        db.row_factory=sqlite3.Row
        pending=db.execute('SELECT event_uid FROM outbox WHERE delivered=0 ORDER BY rowid LIMIT 100').fetchall()
        print('Queued before:',len(pending),'Connected:',connected)
        for r in pending:
            uid=r['event_uid'];db.execute('UPDATE outbox SET attempts=attempts+1 WHERE event_uid=?',(uid,))
            if connected:
                # DEMO ACK ONLY: real network delivery / cryptographic auth NOT implemented.
                db.execute('UPDATE outbox SET delivered=1 WHERE event_uid=?',(uid,))
        db.commit()
        print('Queued after:',db.execute('SELECT COUNT(*) FROM outbox WHERE delivered=0').fetchone()[0])
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--connected',action='store_true');run(p.parse_args().connected)
