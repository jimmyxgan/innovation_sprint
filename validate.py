"""Reproducible synthetic benchmark; NOT field sensitivity qualification.
[IEC62478] IEC TS 62478:2016 requires sensitivity/measurement checks.
[ASSUMPTION] All ground truth labels are from the synthetic generator, not real PD.
Detection probability=TP/(TP+FN); false alarms per hour=FP/simulated hours.
[Reference] Standard binary detection performance definitions (signal detection theory).
"""
import argparse,csv,json
from pathlib import Path
import numpy as np
from physics import FS,N,make_window
from processing import train_rf,observations,fuse

def run(samples=12,seed=1337,out='validation'):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    rf,info=train_rf(seed=42,scenario='nominal',examples_per_class=130)
    rng=np.random.default_rng(seed)
    rows=[];loc=[]
    # Entire test scenarios unseen in training; no pulse-level random split.
    for scenario in ['nominal','high_noise','sensor_shift','spectral_shift']:
        for method,clf in [('Conventional',None),('Conventional + RF',rf)]:
            tp=fn=fp=tn=0;correct=resolved=total_pd=0
            for j in range(samples):
                kind='pd' if j%2==0 else ('impact' if j%4==1 else 'vibration')
                region=(int(rng.integers(4)),int(rng.integers(4)))
                x,truth=make_window(rng,scenario,force_kind=kind,force_region=region)
                events=fuse(observations(x,clf))
                # Conservative conventional baseline: any detected transient is a candidate.
                # RF alarm only when PD-like; uncertain remains in candidate trend.
                alarm=any(e['classification']=='PD-like' for e in events) if clf else bool(events)
                if kind=='pd':
                    total_pd+=1;tp+=int(alarm);fn+=int(not alarm)
                    localized=[e for e in events if e['gap'] is not None]
                    if localized:
                        resolved+=1
                        correct+=int(any((e['gap'],e['sector'])==(region[0]+1,region[1]+1) for e in localized))
                else:fp+=int(alarm);tn+=int(not alarm)
            # Each window represents N/FS simulated seconds; no claim of operating hours.
            sim_hours=(samples/2)*(N/FS)/3600
            rows.append({'scenario':scenario,'method':method,'PD_recall':round(tp/max(1,tp+fn),4),
                         'false_alarms_per_sim_hour':round(fp/max(sim_hours,1e-9),2),
                         'TP':tp,'FN':fn,'FP':fp,'TN':tn,
                         'localization_correct_per_pd':round(correct/max(1,total_pd),4),
                         'localization_resolved_per_pd':round(resolved/max(1,total_pd),4)})
    with (out/'metrics.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (out/'metrics.json').open('w') as f:json.dump({'training':info,'results':rows},f,indent=2)
    try:
        import matplotlib;matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots(figsize=(10,5))
        sc=['nominal','high_noise','sensor_shift','spectral_shift'];xx=np.arange(4)
        for method,offset in [('Conventional',-.17),('Conventional + RF',.17)]:
            yy=[next(r for r in rows if r['scenario']==s and r['method']==method)['PD_recall'] for s in sc]
            ax.bar(xx+offset,yy,.34,label=method)
        ax.set_xticks(xx,sc);ax.set_ylim(0,1.05);ax.set_ylabel('Synthetic PD detection probability')
        ax.set_title('Detection benchmark — simulated signals only');ax.legend()
        fig.tight_layout();fig.savefig(out/'pd_recall.png',dpi=160);plt.close(fig)
        fig,ax=plt.subplots(figsize=(10,5))
        for method,offset in [('Conventional',-.17),('Conventional + RF',.17)]:
            yy=[next(r for r in rows if r['scenario']==s and r['method']==method)['false_alarms_per_sim_hour'] for s in sc]
            ax.bar(xx+offset,yy,.34,label=method)
        ax.set_xticks(xx,sc);ax.set_ylabel('False alarms / simulated hour')
        ax.set_title('Interference rejection — simulated signals only');ax.legend()
        fig.tight_layout();fig.savefig(out/'false_alarms.png',dpi=160);plt.close(fig)
    except ImportError:print('matplotlib missing; skipped plots')
    print('Training:',info)
    for r in rows:print(r)
    print('Saved',out.resolve())
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--samples',type=int,default=12);p.add_argument('--out',default='validation')
    a=p.parse_args();run(a.samples,out=a.out)
