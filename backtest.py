"""
backtest.py  --  A beginner-friendly strategy backtester for Nifty 50 & Bank Nifty.

WHAT THIS DOES
--------------
1. Downloads REAL historical daily prices (free, from Yahoo Finance).
2. Runs a simple, understandable strategy on that history.
3. Prints an HONEST scorecard: month-by-month returns, win rate, worst month,
   and the biggest drawdown (peak-to-valley loss).
4. Saves a chart (equity_curve.png) so you can SEE the good and bad periods.

WHY THIS MATTERS
----------------
Your goal is 3-4% per month. This tool lets you check whether ANY strategy
actually delivers that on real past data -- INCLUDING the painful months that
tip-sellers on YouTube/Telegram never show you.

NOTE: This is EDUCATION, not financial advice. Past results do NOT guarantee
future results. No real money is involved -- this is pure paper testing.
"""

import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")  # save charts to file, no popup window needed
import matplotlib.pyplot as plt


# ---------------------------------------------------------------------------
# 1. CONFIGURATION  -- change these to experiment
# ---------------------------------------------------------------------------
INDICES = {
    "Nifty 50":   "^NSEI",     # Yahoo Finance ticker for Nifty 50
    "Bank Nifty": "^NSEBANK",  # Yahoo Finance ticker for Bank Nifty
}
YEARS_OF_HISTORY = 10          # how far back to test
FAST_EMA = 20                  # short-term trend line
SLOW_EMA = 50                  # long-term trend line
COST_PER_TRADE_PCT = 0.05      # rough brokerage + slippage per trade, in %
MONTHLY_TARGET_PCT = 3.0       # your stated goal, for comparison


# ---------------------------------------------------------------------------
# 2. THE STRATEGY  -- a simple trend-following rule
#    "Be invested when the fast average is above the slow average, else sit in cash."
#    This is one of the oldest, simplest strategies. We use it as a starting point
#    you can UNDERSTAND, not because it is the best.
# ---------------------------------------------------------------------------
def generate_signals(prices: pd.DataFrame) -> pd.Series:
    fast = prices["Close"].ewm(span=FAST_EMA, adjust=False).mean()
    slow = prices["Close"].ewm(span=SLOW_EMA, adjust=False).mean()
    # signal = 1 means "hold the index", 0 means "in cash"
    signal = (fast > slow).astype(int)
    return signal


# ---------------------------------------------------------------------------
# 3. THE BACKTEST ENGINE  -- turns signals into a day-by-day equity curve
# ---------------------------------------------------------------------------
def run_backtest(prices: pd.DataFrame) -> pd.DataFrame:
    df = prices.copy()
    df["signal"] = generate_signals(df)

    # We act on YESTERDAY's signal to avoid "cheating" (you can't trade on a
    # price you haven't seen yet). This is a crucial honesty rule in backtesting.
    df["position"] = df["signal"].shift(1).fillna(0)

    # daily % change of the index
    df["market_ret"] = df["Close"].pct_change().fillna(0)

    # our return = market return ONLY on days we were invested
    df["strat_ret"] = df["position"] * df["market_ret"]

    # subtract trading costs whenever we switch in or out
    trades = df["position"].diff().abs().fillna(0)
    df["strat_ret"] -= trades * (COST_PER_TRADE_PCT / 100.0)

    # build the growth-of-1-rupee curves
    df["strategy_equity"] = (1 + df["strat_ret"]).cumprod()
    df["buyhold_equity"] = (1 + df["market_ret"]).cumprod()
    return df


# ---------------------------------------------------------------------------
# 4. THE HONEST SCORECARD  -- metrics that reveal the real risk
# ---------------------------------------------------------------------------
def max_drawdown(equity: pd.Series) -> float:
    """Biggest peak-to-valley drop, in %. This is the pain you must survive."""
    running_peak = equity.cummax()
    drawdown = (equity / running_peak) - 1.0
    return drawdown.min() * 100.0


def monthly_returns(daily_ret: pd.Series) -> pd.Series:
    """Compound daily returns into calendar-month returns, in %."""
    monthly = (1 + daily_ret).resample("ME").prod() - 1
    return monthly * 100.0


def scorecard(name: str, df: pd.DataFrame):
    strat_monthly = monthly_returns(df["strat_ret"])
    n_months = len(strat_monthly)

    total_return = (df["strategy_equity"].iloc[-1] - 1) * 100
    years = (df.index[-1] - df.index[0]).days / 365.25
    cagr = ((df["strategy_equity"].iloc[-1]) ** (1 / years) - 1) * 100

    avg_month = strat_monthly.mean()
    pct_positive = (strat_monthly > 0).mean() * 100
    pct_hit_target = (strat_monthly >= MONTHLY_TARGET_PCT).mean() * 100
    worst_month = strat_monthly.min()
    best_month = strat_monthly.max()
    mdd = max_drawdown(df["strategy_equity"])

    bh_total = (df["buyhold_equity"].iloc[-1] - 1) * 100

    print(f"\n{'='*62}")
    print(f"  SCORECARD:  {name}   (strategy: {FAST_EMA}/{SLOW_EMA} EMA trend)")
    print(f"{'='*62}")
    print(f"  Test period          : {df.index[0].date()}  to  {df.index[-1].date()}  (~{years:.1f} yrs)")
    print(f"  Total return (strat) : {total_return:8.1f} %")
    print(f"  Total return (B&H)   : {bh_total:8.1f} %   <- just buying & holding")
    print(f"  CAGR (per year)      : {cagr:8.1f} %")
    print(f"  {'-'*58}")
    print(f"  Avg return / month   : {avg_month:8.2f} %   (your goal: {MONTHLY_TARGET_PCT:.1f}%)")
    print(f"  Months that were +ve : {pct_positive:8.1f} %  of {n_months} months")
    print(f"  Months >= {MONTHLY_TARGET_PCT:.0f}% goal   : {pct_hit_target:8.1f} %  of {n_months} months")
    print(f"  BEST month           : {best_month:8.2f} %")
    print(f"  WORST month          : {worst_month:8.2f} %   <- could you stomach this?")
    print(f"  Max drawdown         : {mdd:8.1f} %   <- biggest drop from a peak")
    print(f"{'='*62}")

    # A plain-language verdict
    if avg_month >= MONTHLY_TARGET_PCT and pct_positive > 55:
        verdict = "Looks strong on paper -- but check the worst month & drawdown above."
    elif avg_month > 0:
        verdict = f"Profitable, but averages {avg_month:.2f}%/month, BELOW your {MONTHLY_TARGET_PCT:.0f}% goal."
    else:
        verdict = "This strategy LOST money over this period. Do not trade it live."
    print(f"  Verdict: {verdict}\n")

    return strat_monthly


# ---------------------------------------------------------------------------
# 5. MAIN  -- tie it all together
# ---------------------------------------------------------------------------
def main():
    fig, axes = plt.subplots(len(INDICES), 1, figsize=(11, 4 * len(INDICES)))
    if len(INDICES) == 1:
        axes = [axes]

    for ax, (name, ticker) in zip(axes, INDICES.items()):
        print(f"\nDownloading {name} ({ticker}) ...")
        prices = yf.download(ticker, period=f"{YEARS_OF_HISTORY}y",
                             interval="1d", progress=False, auto_adjust=True)
        if prices.empty:
            print(f"  !! No data for {ticker}. Skipping.")
            continue
        # yfinance sometimes returns multi-level columns; flatten them
        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(0)

        df = run_backtest(prices)
        scorecard(name, df)

        # plot strategy vs buy-and-hold
        ax.plot(df.index, df["strategy_equity"], label="Strategy", linewidth=1.6)
        ax.plot(df.index, df["buyhold_equity"], label="Buy & Hold",
                linewidth=1.2, alpha=0.7)
        ax.set_title(f"{name}: growth of Rs.1 invested")
        ax.set_ylabel("Rs. (starting from 1)")
        ax.legend()
        ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig("equity_curve.png", dpi=110)
    print("Chart saved to: equity_curve.png  (open it to SEE the ups and downs)\n")


if __name__ == "__main__":
    main()
