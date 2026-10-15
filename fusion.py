"""Conservative diagnostic fusion. Scores are not calibrated probabilities by default."""
def decide(scores,quality_ok=True,sensor_ok=True,physical_consistency=None,low=.25,high=.75):
    if not sensor_ok:return {'state':'monitoring_degraded','reason':'Sensor health failure'}
    if not quality_ok:return {'state':'uncertain','reason':'Invalid or low-quality signal'}
    scores=[float(s) for s in scores if s is not None]
    if not scores:return {'state':'uncertain','reason':'No classifier evidence'}
    # A missing microphone is not a negative AE vote.
    score=max(scores)
    if physical_consistency is False:return {'state':'uncertain','reason':'Physical inconsistency; review required','score':score}
    state='pd_likely' if score>=high else 'interference_likely' if score<=low else 'uncertain'
    return {'state':state,'score':score,'reason':'Uncalibrated model score; prototype thresholds'}
