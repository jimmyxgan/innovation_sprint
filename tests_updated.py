import unittest
import numpy as np
from sensors import default_configs
from features import extract_event_features,feature_names,sequence_features
from signal_processing import candidates
from ml_classifier import train,predict
from fusion import decide

class UpdatedPipelineTests(unittest.TestCase):
    def test_features(self):
        for cfg in default_configs().values():
            t=np.arange(1024)/cfg.sample_rate
            x=np.sin(2*np.pi*(cfg.passband_hz[0]+cfg.passband_hz[1])/2*t)
            f=extract_event_features(x,cfg)
            self.assertEqual(len(f),len(feature_names(cfg)))
            self.assertTrue(np.all(np.isfinite(f)))
    def test_detection(self):
        cfg=default_configs()['mic'];rng=np.random.default_rng(1)
        x=rng.normal(0,.001,4096)
        t=np.arange(400)/cfg.sample_rate
        x[1500:1900]+=.5*np.exp(-t/.002)*np.sin(2*np.pi*7000*t)
        self.assertGreater(len(candidates(x,cfg)['peaks']),0)
    def test_model(self):
        cfg=default_configs()['mic'];rng=np.random.default_rng(3)
        t=np.arange(512)/cfg.sample_rate
        waves=[]; labels=[]
        for k in range(12):
            waves.append(np.sin(2*np.pi*(7000 if k<6 else 16000)*t)+rng.normal(0,.1,len(t)))
            labels.append(int(k>=6))
        model=train(waves,labels,cfg)
        self.assertTrue(0<=predict(model,waves[0],cfg)<=1)
    def test_fusion(self):
        self.assertEqual(decide([.9],sensor_ok=False)['state'],'monitoring_degraded')
        self.assertEqual(decide([.9])['state'],'pd_likely')
        self.assertIsNone(sequence_features([1],[])['phase_concentration'])
if __name__=='__main__':unittest.main()
