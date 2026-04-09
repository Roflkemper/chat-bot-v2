
def render(s):
    return f"""⚡ BTC [1h]

СТАТУС: {s['state']}
СТОРОНА: {s['side']}

ГЛУБИНА: {s['depth']}%
ДО КРАЯ: {s['distance']}$

КОНСЕНСУС:
{s['side']} | {s['confidence']}
"""
