from services.telegram_runtime import (
    build_market_alert_message,
    normalize_chat_ids,
    resolve_telegram_text,
    split_text_chunks,
)


class _FakeSnapshot:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return dict(self._payload)


def test_normalize_chat_ids_merges_and_deduplicates():
    assert normalize_chat_ids('123, 456', '456;789', None, 'abc') == [123, 456, 789]


def test_split_text_chunks_preserves_full_text():
    text = 'A' * 3900 + '\n\n' + 'B' * 3900 + '\n\n' + 'C' * 50
    chunks = split_text_chunks(text, limit=3800)
    assert len(chunks) >= 3
    assert ''.join(chunk.replace('\n\n', '') for chunk in chunks).startswith('A' * 3800)
    rebuilt = '\n\n'.join(chunks)
    assert 'A' * 200 in rebuilt
    assert 'B' * 200 in rebuilt
    assert rebuilt.endswith('C' * 50)
    assert all(len(chunk) <= 3800 for chunk in chunks)


def test_resolve_telegram_text_maps_slash_commands():
    assert resolve_telegram_text('/market') == 'BTC 1H'
    assert resolve_telegram_text('/entry') == '⚡ ЧТО ДЕЛАТЬ СЕЙЧАС'
    assert resolve_telegram_text('/exit') == 'BTC SMART EXIT'
    assert resolve_telegram_text('ОТЛАДКА') == 'DEBUG EXPORT'


def test_build_market_alert_message_includes_action_guidance():
    snap = _FakeSnapshot(
        {
            'price': 71234.5,
            'decision': {
                'direction_text': 'LONG',
                'action_text': 'ENTER LONG',
                'manager_action_text': 'PARTIAL EXIT',
                'risk_level': 'MEDIUM',
                'confidence_pct': 71.2,
                'entry_reason': 'reclaim confirmed',
                'invalidation': 'return below reclaim level',
            },
        }
    )
    text = build_market_alert_message(snap, '1h', 'Новый переход сценария')
    assert 'BTCUSDT [1H]' in text
    assert 'Новый переход сценария' in text
    assert 'ТРЕЙДЕРСКОЕ ДЕЙСТВИЕ' in text
    assert 'фиксировать часть' in text or 'разгружать ступенчато' in text
