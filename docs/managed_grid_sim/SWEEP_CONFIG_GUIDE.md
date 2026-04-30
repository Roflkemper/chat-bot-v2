# Sweep Config Guide

Файлы в `configs/sweep/*.yaml` задают:

- `base_bot_configs`
- `intervention_rules`
- `regime_classifier_params`

Любой блок вида:

```yaml
param_name:
  _range: [1, 2, 3]
```

разворачивается в cartesian product.

CLI:

```bash
python tools/sweep_runner.py --config configs/sweep/p15_sweep.yaml --ohlcv frozen/sample.json --output tmp/sweep --dry-run
```
