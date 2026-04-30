from __future__ import annotations

import copy
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

from .intervention_rules import RULE_TYPES, InterventionRule
from .managed_runner import ManagedGridSimRunner, ManagedRunConfig
from .regime_classifier import RegimeClassifier


def _expand_dict_ranges(node: Any) -> list[Any]:
    if isinstance(node, dict):
        if set(node.keys()) == {"_range"}:
            return list(node["_range"])
        expanded_values = {key: _expand_dict_ranges(value) for key, value in node.items()}
        keys = list(expanded_values.keys())
        dict_combos: list[dict[str, Any]] = []
        for product in itertools.product(*(expanded_values[key] for key in keys)):
            dict_combos.append({key: value for key, value in zip(keys, product)})
        return dict_combos
    if isinstance(node, list):
        items = [_expand_dict_ranges(item) for item in node]
        list_combos: list[Any] = []
        for product in itertools.product(*items):
            list_combos.append(list(product))
        return list_combos
    return [node]


class SweepEngine:
    def __init__(
        self,
        bars: list[Any],
        base_bot_config: dict[str, Any] | None,
        sweep_yaml_path: Path,
        parallelism: int = 4,
        runner: ManagedGridSimRunner | None = None,
    ) -> None:
        self.bars = bars
        self.base_bot_config = base_bot_config
        self.sweep_yaml_path = sweep_yaml_path
        self.parallelism = parallelism
        self.runner = runner or ManagedGridSimRunner()

    def expand_to_runs(self) -> list[ManagedRunConfig]:
        spec = yaml.safe_load(self.sweep_yaml_path.read_text(encoding="utf-8"))
        rule_specs = spec.get("intervention_rules", [])
        rule_variants = [_expand_dict_ranges(rule_spec) for rule_spec in rule_specs]
        if not rule_variants:
            rule_variants = [[None]]
        runs: list[ManagedRunConfig] = []
        for idx, selected_rules in enumerate(itertools.product(*rule_variants)):
            rules = [self._build_rule(item) for item in selected_rules if item]
            configs = copy.deepcopy(spec.get("base_bot_configs", []))
            if self.base_bot_config is not None and not configs:
                configs = [copy.deepcopy(self.base_bot_config)]
            classifier = RegimeClassifier(**spec.get("regime_classifier_params", {}))
            runs.append(
                ManagedRunConfig(
                    bot_configs=configs,
                    bars=self.bars,
                    intervention_rules=rules,
                    regime_classifier=classifier,
                    run_id=f"{spec.get('sweep_id', 'sweep')}_{idx:04d}",
                    strict_mode=False,
                )
            )
        return runs

    def execute_all(self, runs: list[ManagedRunConfig]) -> list[Any]:
        results: list[Any] = []
        with ThreadPoolExecutor(max_workers=max(1, self.parallelism)) as pool:
            future_map = {pool.submit(self.runner.run, run): run.run_id for run in runs}
            for future in as_completed(future_map):
                try:
                    results.append(future.result())
                except Exception as exc:
                    results.append(exc)
        return results

    def _build_rule(self, raw_rule: dict[str, Any]) -> InterventionRule:
        rule_type = raw_rule["rule_type"]
        cls = RULE_TYPES[rule_type]
        params = dict(raw_rule.get("params", {}))
        params["affected_bots"] = raw_rule.get("affected_bots", [])
        return cls(**params)
