"""Task 28: ER sanity for display.

ER = avg_views / subscribers * 100. For tiny or brand-new channels a few
views from outside subscribers give absurd values (2200%, 654%). Such values
are not shown: callers get None and display «мало даних».
"""
ER_MAX_PLAUSIBLE = 100.0
ER_MIN_SUBSCRIBERS = 50
ER_NO_DATA = "мало даних"


def reliable_er(er, subscribers=None):
    """Return ER as float if trustworthy, else None («мало даних»)."""
    if er is None or isinstance(er, bool):
        return None
    try:
        f = float(er)
    except (TypeError, ValueError):
        return None
    if f != f or f < 0 or f > ER_MAX_PLAUSIBLE:
        return None
    if subscribers is not None:
        try:
            if int(subscribers) < ER_MIN_SUBSCRIBERS:
                return None
        except (TypeError, ValueError):
            pass
    return f
