# event_watcher placeholder
def build_event_alerts(prev, curr):
    alerts = []
    if prev.get("impulse", {}).get("state") != curr.get("impulse", {}).get("state"):
        alerts.append("Импульс изменился")
    return alerts
