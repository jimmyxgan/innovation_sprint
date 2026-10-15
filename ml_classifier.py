"""Separate, versioned RF models per modality; synthetic-only models are not field validated."""
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import confusion_matrix,precision_score,recall_score
from features import extract_event_features,feature_names

def train(waveforms,labels,config,seed=42):
    X=np.asarray([extract_event_features(w,config) for w in waveforms])
    y=np.asarray(labels,dtype=int)
    if len(np.unique(y))<2:raise ValueError('Need PD and non-PD examples')
    model=RandomForestClassifier(n_estimators=120,min_samples_leaf=4,class_weight='balanced',random_state=seed,n_jobs=1)
    model.fit(X,y)
    return {'model':model,'modality':config.modality,'feature_names':feature_names(config),
            'sample_rate':config.sample_rate,'passband_hz':config.passband_hz,'band_edges_hz':config.band_edges_hz,
            'training_origin':'provided waveforms; provenance must be supplied'}

def predict(bundle,w,config):
    if bundle['modality']!=config.modality or bundle['sample_rate']!=config.sample_rate or tuple(bundle['band_edges_hz'])!=tuple(config.band_edges_hz):
        raise ValueError('Model/config mismatch')
    x=extract_event_features(w,config)
    m=bundle['model']; classes=list(m.classes_)
    return float(m.predict_proba([x])[0,classes.index(1)]) if 1 in classes else 0.
