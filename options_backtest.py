"""
options_backtest.py  --  Testing the "3-4%/month" options-selling strategies
                         on Bank Nifty:  SHORT STRANGLE  and  IRON CONDOR.

THE BIG QUESTION
----------------
YouTube / Telegram "gurus" claim selling weekly options earns 3-4% a month
like clockwork. This script checks that claim against REAL Bank Nifty history.

HOW IT WORKS (and its honest limits)
------------------------------------
Free historical *options* prices for India don't exist. So we RECONSTRUCT each
week's option premiums from:
   - the REAL Bank Nifty weekly closing prices (Yahoo Finance), and
   - the REAL India VIX (the market's volatility gauge),
plugged into the Black-Scholes option-pricing model.

Each week we:
   1. "Sell" a strangle / iron condor at strikes ~1 standard deviation away.
   2. Hold to the next weekly expiry.
   3. Compute the exact profit or loss from where Bank Nifty actually closed.

LIMITS (be aware): model prices ignore the bid-ask spread and assume you can
always trade at fair value. Real fills are slightly worse. So REAL results
would be a bit WORSE than what you see here -- never better.

This is EDUCATION on paper. No real money, no advice.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
from math import log, sqrt, exp
from scipy.stats import norm  # for Black-Scholes; installed if needed below


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
TICKER = "^NSEBANK"
VIX_TICKER = "^INDIAVIX"
YEARS = 10
RISK_FREE = 0.065          # ~6.5% Indian risk-free rate
STRIKE_STEP = 100          # Bank Nifty strikes are 100 points apart
SD_SHORT = 1.0             # sell strikes ~1 std-dev out (~16 delta, common choice)
SD_WING = 2.0              # iron condor protective wings ~2 std-dev out
STRANGLE_MARGIN_FRAC = 0.12  # approx SPAN margin as a fraction of index notional
COST_POINTS_STRANGLE = 6   # rough brokerage+slippage per round trip, in points
COST_POINTS_CONDOR = 12    # 4 legs, so more cost
MONTHLY_TARGET_PCT = 3.0


# ---------------------------------------------------------------------------
# Black-Scholes option pricing
# ---------------------------------------------------------------------------
def bs_call(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(0.0, S - K)
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return S * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2)

def bs_put(S, K, T, r, sigma):
    if T <= 0 or sigma <= 0:
        return max(0.0, K - S)
    d1 = (log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * sqrt(T))
    d2 = d1 - sigma * sqrt(T)
    return K * exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)

def round_strike(x):
    return round(x / STRIKE_STEP) * STRIKE_STEP


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
def load_weekly():
    px = yf.download(TICKER, period=f"{YEARS}y", interval="1d",
                     progress=False, auto_adjust=True)
    if isinstance(px.columns, pd.MultiIndex):
        px.columns = px.columns.get_level_values(0)
    close = px["Close"].dropna()

    vix = yf.download(VIX_TICKER, period=f"{YEARS}y", interval="1d",
                      progress=False, auto_adjust=True)
    if not vix.empty:
        if isinstance(vix.columns, pd.MultiIndex):
            vix.columns = vix.columns.get_level_values(0)
        vix_close = vix["Close"].reindex(close.index).ffill()
        source = "India VIX"
    else:
        # fallback: 20-day realized volatility, annualized, expressed like VIX
        rv = close.pct_change().rolling(20).std() * sqrt(252) * 100
        vix_close = rv.ffill().bfill()
        source = "realized volatility (VIX unavailable)"

    # weekly expiry points (Thursday = historical Bank Nifty weekly expiry)
    weekly = pd.DataFrame({"close": close, "vix": vix_close})
    weekly_thu = weekly.resample("W-THU").last().dropna()
    return weekly_thu, source


# ---------------------------------------------------------------------------
# Simulate one week of a strategy
# ---------------------------------------------------------------------------
def simulate(weekly, strategy):
    rows = []
    idx = weekly.index
    for i in range(len(weekly) - 1):
        S0 = float(weekly["close"].iloc[i])
        S1 = float(weekly["close"].iloc[i + 1])   # where it actually closed at expiry
        iv = float(weekly["vix"].iloc[i]) / 100.0
        if iv <= 0 or np.isnan(iv):
            continue
        T = 7 / 365.0
        sd_week = iv * sqrt(T)                     # 1 std-dev move for the week (as a return)

        Kc = round_strike(S0 * exp(SD_SHORT * sd_week))
        Kp = round_strike(S0 * exp(-SD_SHORT * sd_week))

        if strategy == "strangle":
            credit = bs_call(S0, Kc, T, RISK_FREE, iv) + bs_put(S0, Kp, T, RISK_FREE, iv)
            payoff = credit - max(0.0, S1 - Kc) - max(0.0, Kp - S1) - COST_POINTS_STRANGLE
            capital = STRANGLE_MARGIN_FRAC * S0      # approx margin blocked
        else:  # iron condor
            Kc_l = round_strike(S0 * exp(SD_WING * sd_week))
            Kp_l = round_strike(S0 * exp(-SD_WING * sd_week))
            credit = bs_call(S0, Kc, T, RISK_FREE, iv) + bs_put(S0, Kp, T, RISK_FREE, iv)
            debit = bs_call(S0, Kc_l, T, RISK_FREE, iv) + bs_put(S0, Kp_l, T, RISK_FREE, iv)
            net_credit = credit - debit
            payoff = (net_credit
                      - max(0.0, S1 - Kc) - max(0.0, Kp - S1)     # short legs hurt us
                      + max(0.0, S1 - Kc_l) + max(0.0, Kp_l - S1) # long wings protect us
                      - COST_POINTS_CONDOR)
            width = max(Kc_l - Kc, Kp - Kp_l)
            capital = max(width - net_credit, 1.0)   # defined max loss = capital at risk

        rows.append({"date": idx[i + 1], "ret": payoff / capital})
    out = pd.DataFrame(rows).set_index("date")
    return out["ret"]


# ---------------------------------------------------------------------------
# Scorecard (weekly returns -> monthly)
# ---------------------------------------------------------------------------
def scorecard(name, weekly_ret):
    equity = (1 + weekly_ret).cumprod()
    monthly = ((1 + weekly_ret).resample("ME").prod() - 1) * 100
    n = len(monthly)

    years = (weekly_ret.index[-1] - weekly_ret.index[0]).days / 365.25
    cagr = (equity.iloc[-1] ** (1 / years) - 1) * 100
    running_peak = equity.cummax()
    mdd = ((equity / running_peak) - 1).min() * 100

    print(f"\n{'='*64}")
    print(f"  SCORECARD:  {name}  on Bank Nifty (weekly, ~1 SD short strikes)")
    print(f"{'='*64}")
    print(f"  Avg return / month   : {monthly.mean():8.2f} %   (your goal: {MONTHLY_TARGET_PCT:.1f}%)")
    print(f"  Median month         : {monthly.median():8.2f} %")
    print(f"  Months positive      : {(monthly>0).mean()*100:8.1f} %  of {n} months")
    print(f"  Best month           : {monthly.max():8.2f} %")
    print(f"  WORST month          : {monthly.min():8.2f} %   <- the tail risk they hide")
    print(f"  Worst single WEEK    : {weekly_ret.min()*100:8.2f} %")
    print(f"  Max drawdown         : {mdd:8.1f} %   <- biggest fall from a peak")
    print(f"  CAGR (per year)      : {cagr:8.1f} %")
    print(f"{'='*64}")

    winrate = (weekly_ret > 0).mean() * 100
    print(f"  NOTE: {winrate:.0f}% of individual weeks were profitable -- this is why it")
    print(f"        FEELS like easy money... until a big-move week erases many wins.\n")
    return monthly


def main():
    weekly, source = load_weekly()
    print(f"\nData: Bank Nifty weekly closes, volatility from {source}.")
    print(f"Period: {weekly.index[0].date()} to {weekly.index[-1].date()}, "
          f"{len(weekly)} weekly expiries.\n")
    print("Reminder: real fills are slightly worse than these model prices,")
    print("so treat these results as an OPTIMISTIC upper bound.\n")

    for strat, label in [("strangle", "SHORT STRANGLE (undefined risk)"),
                         ("condor", "IRON CONDOR (defined risk)")]:
        r = simulate(weekly, strat)
        scorecard(label, r)


if __name__ == "__main__":
    main()
