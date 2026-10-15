import unittest
from datetime import datetime,timezone
import numpy as np
from integrated_pipeline import CONFIGS,train_models,make_dual_window,process_dual,MIC_IDS

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.models=train_models(seed=10,samples_per_class=35)
    def test_dual_modalities_and_nyquist(self):
        self.assertGreater(CONFIGS['ae'].sample_rate/2,CONFIGS['ae'].passband_hz[1])
        self.assertEqual(len(MIC_IDS),16)
        signals,truth=make_dual_window(np.random.default_rng(7),demo=True)
        self.assertEqual(signals['ae'].shape[0],80)
        self.assertEqual(signals['mic'].shape[0],16)
        self.assertTrue(truth)
        events,captures=process_dual(signals,self.models,datetime.now(timezone.utc),17)
        self.assertTrue(events)
        self.assertTrue(all(e['gap'] is None and e['sector'] is None for e in events))
        self.assertTrue(all('modalities' in e['evidence'] for e in events))
    def test_no_ml_is_uncertain(self):
        signals,_=make_dual_window(np.random.default_rng(9),demo=True)
        events,_=process_dual(signals,None,datetime.now(timezone.utc),18)
        self.assertTrue(events)
        self.assertTrue(all(e['classification']=='Uncertain' for e in events))
if __name__=='__main__':unittest.main()
