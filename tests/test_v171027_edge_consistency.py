from core.scenario_handoff import compute_scenario_weights
from renderers.renderer import render_full_report


def test_scenario_weights_shift_to_breakdown_when_edge_pressure_without_absorption():
    snapshot = {
        'block_pressure': 'AGAINST',
        'block_pressure_strength': 'LOW',
        'consensus_direction': 'SHORT',
        'active_block': 'LONG',
        'consensus_alignment_count': 2,
        'depth_label': 'EARLY',
        'block_depth_pct': 7.4,
        'range_position_pct': 3.7,
        'forecast': {
            'medium': {'phase': 'MARKUP'},
            'short': {'direction': 'SHORT'},
            'session': {'direction': 'SHORT'},
        },
        'hedge_state': 'ARM',
        'trigger_type': 'RECLAIM',
        'flip_prep_status': 'IDLE',
        'edge_distance_pct': 7.4,
        'absorption': {'is_active': False},
    }
    base_prob, alt_prob, _, alt_reasons = compute_scenario_weights(snapshot)
    assert alt_prob > base_prob
    assert any('пробоя' in reason for reason in alt_reasons)


def test_wait_trade_plan_is_marked_conditional_and_entry_hidden():
    snapshot = {
        'symbol': 'BTCUSDT',
        'tf': '1h',
        'timestamp': '14:23',
        'forecast': {
            'short': {'direction': 'SHORT', 'strength': 'MID', 'note': 'n/a'},
            'session': {'direction': 'SHORT', 'strength': 'HIGH', 'note': 'n/a'},
            'medium': {'direction': 'LONG', 'strength': 'HIGH', 'phase': 'MARKUP', 'note': 'n/a'},
        },
        'state': 'PRE_ACTIVATION',
        'active_block': 'LONG',
        'execution_side': 'LONG',
        'block_depth_pct': 7.4,
        'depth_label': 'EARLY',
        'range_position_pct': 3.7,
        'distance_to_lower_edge': 91.79,
        'distance_to_upper_edge': 2388.21,
        'edge_distance_pct': 7.4,
        'trigger_type': 'RECLAIM',
        'trigger_note': 'касание нижнего края и удержание выше',
        'trigger_blocked': True,
        'trigger_block_reason': 'forecast против активного блока',
        'action': 'WAIT',
        'entry_type': None,
        'context_label': 'WEAK',
        'context_score': 1,
        'consensus_direction': 'SHORT',
        'consensus_confidence': 'MID',
        'consensus_votes': '2/3',
        'warnings': [],
        'trade_plan_active': False,
        'trade_plan_mode': 'GRID MONITORING',
        'trade_plan_activation_note': 'условный — активируется при подтверждении сценария',
        'hedge_state': 'ARM',
        'hedge_arm_up': 74083.0,
        'hedge_arm_down': 71017.0,
        'grid_action': {
            'grid_regime': 'CAUTION',
            'bias_side': 'LONG',
            'structural_side': 'SHORT',
            'priority_side': 'LONG',
            'down_target': 71017.0,
            'up_target': 74083.0,
            'down_impulse_pct': 0.54,
            'up_impulse_pct': 3.76,
            'down_layers': 0,
            'up_layers': 3,
            'long_action': 'BOOST',
            'short_action': 'HOLD',
            'risk_lines': [],
            'review_level_up': 74083.0,
            'review_level_down': 71017.0,
        },
        'bias_score': -3,
        'bias_label': 'медвежье давление',
        'absorption': {'label': 'нет подтверждённого absorption снизу', 'bars_at_edge': 6, 'interpretation': 'продавец давит'},
        'flip_prep_status': 'IDLE',
        'current_action_lines': [
            '• руками: не входить — ждать подтверждение',
            '• LONG сетки: ДЕРЖАТЬ (НЕ УСИЛИВАТЬ у края)',
            '• SHORT сетки: ГОТОВЫ — активация при пробое 71310.0',
        ],
        'if_then_plan': ['▶ ПРОБОЙ: закрытие < 71310.00 (2 бара) → SHORT | цель 71017.00'],
        'top_signal': '⚠️ WAIT | пробой близко — 91.79$ до 71310.00',
        'scenario_alt_probability': 60,
        'scenario_alt_text': 'пробой и закрепление ниже 71310.00 → LONG блок инвалидируется, сценарий смещается в SHORT',
        'scenario_base_probability': 40,
        'scenario_base_text': 'отбой от нижнего края → LONG блок остаётся активным',
    }
    text = render_full_report(snapshot)
    assert '\nENTRY:\n' not in text
    assert '• ⏸️ ОЖИДАНИЕ — условный — активируется при подтверждении сценария' in text
    assert '• LONG сетки: ДЕРЖАТЬ (НЕ УСИЛИВАТЬ у края)' in text
