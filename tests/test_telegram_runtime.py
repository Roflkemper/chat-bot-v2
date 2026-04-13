from services.telegram_runtime import normalize_chat_ids, split_text_chunks


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
