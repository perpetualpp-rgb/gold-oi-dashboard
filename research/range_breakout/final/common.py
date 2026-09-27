"""Shared setup for the COMBINE AND FREEZE stage. Data is loaded with engine.load(until=VAL_END), so
no holdout bar (London date >= 2024-01-01) is ever in memory for this stage."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, ".."))
for p in (ROOT, os.path.join(ROOT, "explore", "null_costs"), os.path.join(ROOT, "explore", "filters")):
    if p not in sys.path:
        sys.path.insert(0, p)
import engine as E  # noqa: E402


def data():
    D = E.load(until=E.VAL_END)
    assert D["index"].max().tz_convert("Europe/London").date().isoformat() <= E.VAL_END
    return D
