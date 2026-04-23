from __future__ import annotations

import json, os

DEFAULT_WEIGHTS = {'regime':1.0,'liquidity':1.0,'pattern':1.0,'ml':1.0,'derivatives':1.0,'micro':0.7,'personal':0.8,'backtest':0.9}

class AdaptiveWeights:
    def __init__(self, path='state/adaptive_weights.json'):
        self.path = path
        self.state = self._load()

    def _load(self):
        if not os.path.exists(self.path):
            return {'global': DEFAULT_WEIGHTS.copy(), 'by_regime': {}, 'by_setup': {}}
        try:
            with open(self.path,'r',encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {'global': DEFAULT_WEIGHTS.copy(), 'by_regime': {}, 'by_setup': {}}

    def get_weights(self, regime_label, setup_type):
        result = DEFAULT_WEIGHTS.copy()
        result.update(self.state.get('global', {}))
        result.update(self.state.get('by_regime', {}).get(regime_label, {}))
        result.update(self.state.get('by_setup', {}).get(setup_type, {}))
        return result

    def update_component_weight(self, bucket, bucket_key, component, expectancy, observations):
        return None
