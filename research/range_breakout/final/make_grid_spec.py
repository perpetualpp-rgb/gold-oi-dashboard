"""Writes grid_spec.json (the pre-declared 24-config grid and the selection rule) BEFORE any grid run."""
import datetime
import itertools
import json
import os

from common import E

HERE = os.path.dirname(os.path.abspath(__file__))
FIXED = dict(entry_mode=0, buf_k=0.0, buf_atr=0.0, entry_end=12.0, exit_time=20.0, tp_r=0.0, max_trades=1,
             range_start=0.0)
configs = {}
for re_, mw, reg, (sref, sk) in itertools.product((5.0, 7.0), (0.30, 0.35, 0.40), (0, 20),
                                                  ((0, 1.0), (1, 0.75))):
    name = f"re{int(re_)}_w{int(round(mw * 100)):03d}_{'a20' if reg else 'nor'}_{'W1.00' if sref == 0 else 'A0.75'}"
    p = E.Params(**FIXED, range_end=re_, min_w_atr=mw, atr_regime_n=reg, atr_regime_max=1.0,
                 sl_ref=sref, sl_k=sk)
    configs[name] = p.to_dict()
assert len(configs) == 24
RULE = {
    "period": "IS 2014-01-01..2021-12-31 only for eligibility and score; VAL 2022-2023 is a veto only",
    "eligible": "IS trades_per_year >= 50 AND IS years (2014..2021) with sum R > 0 >= 6 of 8 AND IS avg_R(longs) > 0 "
                "AND IS avg_R(shorts) > 0",
    "score": "mean IS avg_R of the config and its min_w_atr neighbours with identical other settings "
             "(0.30 -> mean(0.30,0.35); 0.35 -> mean(0.30,0.35,0.40); 0.40 -> mean(0.35,0.40)); neighbours "
             "are used whether or not they are themselves eligible",
    "primary": "highest score among eligible configs; ties (equal to 1e-12) -> no regime filter first, then range_end 7",
    "fallback": "highest-scoring eligible config WITHOUT the ATR-regime filter; if the primary has no regime filter, "
                "highest-scoring eligible config with a different stop type (sl_ref) than the primary",
    "val_veto": "if a chosen config has VAL avg_R < 0, move to the next config by score in the same candidate set "
                "(and report it); fallback must differ from primary",
    "baseline": "engine.Params() default (range 0-7, SL 1x width, no filters) reported for reference",
}
spec = {"written_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "fixed": FIXED, "costs": "engine defaults (commission 0.07, slip 0.05, modelled spread)",
        "n_configs": len(configs), "configs": configs, "selection_rule": RULE,
        "note": "Grid and rule copied verbatim from the stage task; no configs may be added after results are seen."}
json.dump(spec, open(os.path.join(HERE, "grid_spec.json"), "w"), indent=1)
print(len(configs), "configs written")
