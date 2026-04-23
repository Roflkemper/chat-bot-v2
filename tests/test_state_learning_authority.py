import json
from pathlib import Path

from core.setup_stats import build_setup_learning_adjustment, build_setup_stats_context
from storage.personal_bot_learning import load_personal_bot_learning
from storage.trade_journal import final_close_trade, open_trade_journal


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')



def test_final_close_trade_persists_jsonl_and_updates_learning(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    open_trade_journal(
        side='LONG',
        symbol='BTCUSDT',
        timeframe='1h',
        entry_price=71000,
        decision_snapshot={'active_bot': 'ct_long', 'direction': 'LONG', 'action': 'BUY'},
        analysis_snapshot={'trade_style': 'range fade', 'setup_quality_label': 'A', 'best_bot': 'ct_long'},
    )

    state = final_close_trade(
        reason='tp2',
        exit_price=72500,
        result_pct=2.11,
        result_rr=2.4,
        close_context_snapshot={'decision': {'action': 'CLOSE'}},
    )

    journal_path = tmp_path / 'state' / 'trade_journal.jsonl'
    assert journal_path.exists()

    rows = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row['trade_id'] == state['trade_id']
    assert row['result_rr'] == 2.4
    assert row['active_bot'] == 'ct_long'
    assert row['setup_quality'] == 'A'

    learning = load_personal_bot_learning()
    ct_long = learning['bots']['ct_long']
    assert ct_long['closed_trades'] == 1
    assert ct_long['wins'] == 1
    assert ct_long['avg_rr'] == 2.4

    # closing the same already-closed journal again must not duplicate the jsonl row
    final_close_trade(reason='tp2', exit_price=72500, result_pct=2.11, result_rr=2.4)
    rows2 = [json.loads(line) for line in journal_path.read_text(encoding='utf-8').splitlines() if line.strip()]
    assert len(rows2) == 1



def test_setup_stats_tracks_recent_streak_and_penalizes_loss_sequence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    trade_rows = [
        {
            'trade_id': 't1',
            'closed': True,
            'side': 'LONG',
            'result_pct': -1.2,
            'result_rr': -1.0,
            'exit_reason_classifier': 'STOP_OR_INVALIDATION',
        },
        {
            'trade_id': 't2',
            'closed': True,
            'side': 'LONG',
            'result_pct': -0.9,
            'result_rr': -0.7,
            'exit_reason_classifier': 'STRUCTURE_BREAK',
        },
        {
            'trade_id': 't3',
            'closed': True,
            'side': 'LONG',
            'result_pct': -0.4,
            'result_rr': -0.3,
            'exit_reason_classifier': 'STOP_OR_INVALIDATION',
        },
    ]
    _write_jsonl(tmp_path / 'state' / 'trade_journal.jsonl', trade_rows)

    stats = build_setup_stats_context(
        analysis={'decision': {'direction': 'LONG'}},
        trade_journal_path='state/trade_journal.jsonl',
        decision_journal_path='state/decision_journal.jsonl',
    )
    assert stats['recent_streak_type'] == 'LOSS'
    assert stats['recent_loss_streak'] == 3
    assert stats['recent_top_exit_reason'] == 'STOP_OR_INVALIDATION'

    adj = build_setup_learning_adjustment(stats, {'decision': {'direction': 'LONG'}})
    assert adj['delta'] < 0
    joined = ' '.join(adj['reasons'])
    assert 'серия убыточных выходов' in joined
