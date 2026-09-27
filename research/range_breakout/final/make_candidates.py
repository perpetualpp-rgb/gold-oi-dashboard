"""Write candidates.json (FREEZE). frozen_at is passed in by hand."""
import hashlib
import json
import os
import subprocess
import sys

from common import E, HERE, ROOT

FROZEN_AT = sys.argv[1]          # ISO date, by hand
spec = json.load(open(os.path.join(HERE, "grid_spec.json")))
sel = json.load(open(os.path.join(HERE, "selection.json")))
ev = json.load(open(os.path.join(HERE, "eval_results.json")))
dsr = json.load(open(os.path.join(HERE, "dsr.json")))


def P(d):
    return E.Params(**{k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()})


cands = {"primary": P(spec["configs"][sel["primary"]]).to_dict(),
         "fallback": P(spec["configs"][sel["fallback"]]).to_dict(),
         "baseline": E.Params().to_dict()}
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
dirty = subprocess.check_output(["git", "status", "--porcelain", "--", "engine.py", "test_engine.py"],
                                cwd=ROOT).decode().strip()
sha = {f: hashlib.sha256(open(os.path.join(ROOT, f), "rb").read()).hexdigest() for f in ("engine.py", "test_engine.py")}
stats = {}
for k in cands:
    e = ev[k]
    stats[k] = {per: e[per] for per in ("IS", "VAL", "IS_long", "IS_short", "VAL_long", "VAL_short")}
    stats[k]["IS_yrs_pos"] = e["IS_yrs_pos"]
    stats[k]["by_year"] = e["by_year"]
    stats[k]["cost_stress"] = e["cost_stress"]
    stats[k]["null_p_coin"] = {per: e["null_test"][per]["coin"]["p"] for per in ("IS", "VAL")}
    stats[k]["top_removed"] = {x: e[x] for x in e if "top" in x}
    stats[k]["dsr_V_1_over_T"] = {str(d["N"]): d["DSR"] for d in dsr[k]["V=1/T"]}
fb = {r["config"]: r["p_family"] for r in ev["family_bootstrap_IS"]["table"]}
for k, name in (("primary", sel["primary"]), ("fallback", sel["fallback"])):
    stats[k]["family_bootstrap_IS_p_family"] = fb[name]
out = {
    "frozen_at": FROZEN_AT,
    "engine_git_hash": head,
    "engine_worktree_dirty": bool(dirty),
    "engine_sha256": sha,
    "engine_note": "HEAD does not yet contain Params.atr_regime_n/atr_regime_max and load(until=); the frozen "
                   "engine is the working-tree engine.py with the sha256 above (commit it to pin the hash)",
    "grid_names": {"primary": sel["primary"], "fallback": sel["fallback"]},
    "candidates": cands,
    "selection_rule": json.dumps(spec["selection_rule"]),
    "selection_log": sel["log"],
    "is_val_stats": stats,
}
json.dump(out, open(os.path.join(HERE, "candidates.json"), "w"), indent=1)
print(json.dumps({k: out[k] for k in ("frozen_at", "engine_git_hash", "engine_worktree_dirty", "grid_names")}, indent=1))
