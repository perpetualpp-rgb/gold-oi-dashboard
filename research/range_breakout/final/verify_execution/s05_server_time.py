"""(d) Server-time / DST pitfalls. A typical MT5 gold server runs at NY+7h (GMT+2 winter / GMT+3 US summer).
London 00:00 is server 02:00 except in the US/EU DST-mismatch weeks (2nd Sun Mar .. last Sun Mar, last Sun
Oct .. 1st Sun Nov), when it is server 03:00. Scenarios for an EA that hard-codes server hours:
  A  NY+7 server, hard-coded 02:00/07:00/14:00/22:00 server  -> London hours shifted -1h on mismatch days
  B  fixed GMT+2 server (no DST), hard-coded 02/07/14/22   -> shifted +1h during London summer time (BST)
  C  MT5 Strategy Tester: TimeGMT() == TimeCurrent() (server time), so an EA that derives London time
     from TimeGMT() treats server time as GMT: its London clock runs ahead of the real one by the server's
     GMT offset -> sessions land 2h early (GMT+2 periods) or 3h early (GMT+3), i.e. the range starts at
     22:00/21:00 London and contains the daily halt.
Each scenario = per day, the trade of the primary run with the shifted session (same filters)."""
from xcommon import *
D = data()
days = D["days"].index
p = params("primary")


def shifted(h):
    return params("primary", range_start=p.range_start + h, range_end=p.range_end + h,
                  entry_end=p.entry_end + h, exit_time=p.exit_time + h)

runs = {h: E.run(shifted(h), end=E.VAL_END, D=D) for h in (-3, -2, -1, 0, 1)}
# London-midnight -> server offset per day (server = NY + 7h)
noon = days + pd.Timedelta(hours=12)
lon_off = np.array([pd.Timestamp(d).tz_localize("Europe/London").utcoffset().total_seconds() / 3600 for d in noon])
ny_off = np.array([pd.Timestamp(d).tz_localize("America/New_York").utcoffset().total_seconds() / 3600 for d in noon])
srv_minus_lon = (ny_off + 7) - lon_off
print("server-London offset counts (IS+VAL days):", pd.Series(srv_minus_lon).value_counts().to_dict())
mism = srv_minus_lon != 2
bst = lon_off == 1


def splice(shift_by_day):
    out = []
    for h in np.unique(shift_by_day):
        t = runs[int(h)]
        sel = shift_by_day[t.day.values] == h
        out.append(t[sel])
    return pd.concat(out).sort_values("day")


def summ(t):
    r = {}
    for per, sel in (("IS", t.date <= E.IS_END), ("VAL", t.date > E.IS_END), ("ALL", t.date > "2000")):
        x = t[sel].R
        r[per] = dict(n=len(x), avg_R=round(x.mean(), 4))
    return r

res = {"offset_counts": pd.Series(srv_minus_lon).value_counts().to_dict(),
       "mismatch_days": int(mism.sum()), "engine": summ(runs[0])}
A = splice(np.where(mism, -1, 0)); res["A_hardcoded_NY+7"] = summ(A)
B = splice(np.where(bst, 1, 0)); res["B_fixed_GMT+2"] = summ(B)
C = splice(-(ny_off + 7).astype(int)); res["C_tester_TimeGMT"] = summ(C)
ref = runs[0]
res["A_changed_trades"] = dict(mism_days_with_trade_engine=int(mism[ref.day].sum()),
                               mism_days_with_trade_A=int(mism[A.day].sum()),
                               engine_R_on_mism=round(ref[mism[ref.day]].R.sum(), 2),
                               A_R_on_mism=round(A[mism[A.day]].R.sum(), 2))
for h, t in runs.items():
    res[f"all_days_shift_{h}h"] = summ(t)
print(json.dumps(res, indent=1, default=str))
json.dump(res, open("s05_server_time.json", "w"), indent=1, default=str)
