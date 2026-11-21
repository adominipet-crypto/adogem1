import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import datetime
import requests

# --- Environment Settings ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# --- Wide Multi-Asset Watchlist (75 Instruments) ---
# category: "INDEX" | "FUTURE" | "FX"
# group: subgroup summary key for clean grouping in email
WIDE_MARKET_WATCHLIST = [
    # 1. Global Indices & Volatility (14)
    {"symbol": "^GSPC", "name": "S&P 500 Index", "moomoo": "S&P 500 / SPX", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^IXIC", "name": "NASDAQ Composite", "moomoo": "NASDAQ / IXIC", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^DJI", "name": "Dow Jones Industrial Average", "moomoo": "Dow / DJI", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^RUT", "name": "Russell 2000 Index", "moomoo": "Russell 2000 / RUT", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^NDX", "name": "NASDAQ-100 Index", "moomoo": "NASDAQ 100 / NDX", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^NYA", "name": "NYSE Composite Index", "moomoo": "NYSE Composite", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^SOX", "name": "PHLX Semiconductor Index", "moomoo": "SOX / Semiconductor", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^VIX", "name": "CBOE Volatility Index", "moomoo": "VIX", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^VXN", "name": "NASDAQ-100 Volatility Index", "moomoo": "VXN", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^RVX", "name": "Russell 2000 Volatility Index", "moomoo": "RVX", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^N225", "name": "Nikkei 225", "moomoo": "Nikkei 225", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^HSI", "name": "Hang Seng Index", "moomoo": "Hang Seng / HSI", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^FTSE", "name": "FTSE 100 Index", "moomoo": "FTSE 100", "category": "INDEX", "group": "Global & Volatility Indices"},
    {"symbol": "^GDAXI", "name": "DAX Performance Index", "moomoo": "DAX", "category": "INDEX", "group": "Global & Volatility Indices"},

    # 2. Equity Index Futures (8)
    {"symbol": "ES=F", "name": "E-mini S&P 500 Futures", "moomoo": "E-mini S&P 500", "category": "FUTURE", "group": "Equity Index Futures"},
    {"symbol": "NQ=F", "name": "E-mini NASDAQ-100 Futures", "moomoo": "E-mini NASDAQ 100", "category": "FUTURE", "group": "Equity Index Futures"},
    {"symbol": "YM=F", "name": "E-mini Dow Futures", "moomoo": "E-mini Dow", "category": "FUTURE", "group": "Equity Index Futures"},
    {"symbol": "RTY=F", "name": "E-mini Russell 2000 Futures", "moomoo": "E-mini Russell 2000", "category": "FUTURE", "group": "Equity Index Futures"},
    {"symbol": "NKD=F", "name": "Nikkei 225 USD Futures", "moomoo": "Nikkei Futures", "category": "FUTURE", "group": "Equity Index Futures"},
    {"symbol": "FDAX=F", "name": "DAX Futures", "moomoo": "DAX Futures", "category": "FUTURE", "group": "Equity Index Futures"},
    {"symbol": "FESX=F", "name": "Euro Stoxx 50 Futures", "moomoo": "Euro Stoxx 50", "category": "FUTURE", "group": "Equity Index Futures"},
    {"symbol": "HSI=F", "name": "Hang Seng Index Futures", "moomoo": "Hang Seng Futures", "category": "FUTURE", "group": "Equity Index Futures"},

    # 3. Agricultural & Livestock Futures (14)
    {"symbol": "ZS=F", "name": "Soybeans Futures", "moomoo": "Soybeans", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "ZC=F", "name": "Corn Futures", "moomoo": "Corn", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "ZW=F", "name": "Chicago SRW Wheat Futures", "moomoo": "SRW Wheat", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "KE=F", "name": "KC HRW Wheat Futures", "moomoo": "HRW Wheat", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "ZO=F", "name": "Oats Futures", "moomoo": "Oats", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "ZR=F", "name": "Rough Rice Futures", "moomoo": "Rough Rice", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "ZM=F", "name": "Soybean Meal Futures", "moomoo": "Soybean Meal", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "ZL=F", "name": "Soybean Oil Futures", "moomoo": "Soybean Oil", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "KC=F", "name": "Coffee C Futures", "moomoo": "Coffee", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "SB=F", "name": "Sugar No. 11 Futures", "moomoo": "Sugar", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "CC=F", "name": "Cocoa Futures", "moomoo": "Cocoa", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "CT=F", "name": "Cotton No. 2 Futures", "moomoo": "Cotton", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "LE=F", "name": "Live Cattle Futures", "moomoo": "Live Cattle", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},
    {"symbol": "HE=F", "name": "Lean Hogs Futures", "moomoo": "Lean Hogs", "category": "FUTURE", "group": "Agricultural & Livestock Futures"},

    # 4. Energy, Metals & Treasury Futures (15)
    {"symbol": "CL=F", "name": "WTI Crude Oil Futures", "moomoo": "WTI Crude Oil", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "BZ=F", "name": "Brent Crude Oil Futures", "moomoo": "Brent Crude Oil", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "NG=F", "name": "Henry Hub Natural Gas Futures", "moomoo": "Natural Gas", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "RB=F", "name": "RBOB Gasoline Futures", "moomoo": "RBOB Gasoline", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "HO=F", "name": "NY Harbor ULSD Heating Oil Futures", "moomoo": "Heating Oil", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "GC=F", "name": "Gold Futures", "moomoo": "Gold", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "SI=F", "name": "Silver Futures", "moomoo": "Silver", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "PL=F", "name": "Platinum Futures", "moomoo": "Platinum", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "PA=F", "name": "Palladium Futures", "moomoo": "Palladium", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "HG=F", "name": "Copper Futures", "moomoo": "Copper", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "ALI=F", "name": "Aluminum Futures", "moomoo": "Aluminum", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "ZB=F", "name": "U.S. Treasury Bond Futures (30Y)", "moomoo": "30Y T-Bond", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "ZN=F", "name": "10-Year T-Note Futures", "moomoo": "10Y T-Note", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "ZF=F", "name": "5-Year T-Note Futures", "moomoo": "5Y T-Note", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},
    {"symbol": "ZT=F", "name": "2-Year T-Note Futures", "moomoo": "2Y T-Note", "category": "FUTURE", "group": "Energy, Metals & Rates Futures"},

    # 5. Foreign Exchange / FX Pairs (24)
    {"symbol": "DX-Y.NYB", "name": "US Dollar Index (DXY)", "moomoo": "DXY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "moomoo": "USDJPY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "EURUSD=X", "name": "EUR/USD", "moomoo": "EURUSD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "moomoo": "GBPUSD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDCHF=X", "name": "USD/CHF", "moomoo": "USDCHF", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDCAD=X", "name": "USD/CAD", "moomoo": "USDCAD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "AUDUSD=X", "name": "AUD/USD", "moomoo": "AUDUSD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "NZDUSD=X", "name": "NZD/USD", "moomoo": "NZDUSD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "EURJPY=X", "name": "EUR/JPY", "moomoo": "EURJPY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "GBPJPY=X", "name": "GBP/JPY", "moomoo": "GBPJPY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "AUDJPY=X", "name": "AUD/JPY", "moomoo": "AUDJPY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "NZDJPY=X", "name": "NZD/JPY", "moomoo": "NZDJPY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "CADJPY=X", "name": "CAD/JPY", "moomoo": "CADJPY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "CHFJPY=X", "name": "CHF/JPY", "moomoo": "CHFJPY", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "EURGBP=X", "name": "EUR/GBP", "moomoo": "EURGBP", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "EURAUD=X", "name": "EUR/AUD", "moomoo": "EURAUD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "AUDNZD=X", "name": "AUD/NZD", "moomoo": "AUDNZD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDCNH=X", "name": "USD/CNH", "moomoo": "USDCNH", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDHKD=X", "name": "USD/HKD", "moomoo": "USDHKD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDSGD=X", "name": "USD/SGD", "moomoo": "USDSGD", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDKRW=X", "name": "USD/KRW", "moomoo": "USDKRW", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDMXN=X", "name": "USD/MXN", "moomoo": "USDMXN", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDZAR=X", "name": "USD/ZAR", "moomoo": "USDZAR", "category": "FX", "group": "FX Pairs & Dollar Index"},
    {"symbol": "USDTRY=X", "name": "USD/TRY", "moomoo": "USDTRY", "category": "FX", "group": "FX Pairs & Dollar Index"},
]

GROUP_ORDER = [
    "Global & Volatility Indices",
    "Equity Index Futures",
    "Agricultural & Livestock Futures",
    "Energy, Metals & Rates Futures",
    "FX Pairs & Dollar Index",
]

REQUEST_SLEEP_SEC = 0.5


def fetch_series_df(symbol):
    """Fetch daily OHLCV from Yahoo Finance v8 chart API."""
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    encoded_symbol = symbol.replace("^", "%5E").replace("=", "%3D")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}?range=5y&interval=1d&nocache={int(time.time())}"

    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 429:
                time.sleep(5 * (attempt + 1))
                continue
            if res.status_code != 200:
                return None

            result = res.json().get("chart", {}).get("result", [])
            if not result:
                return None

            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            timestamps = result[0].get("timestamp", [])
            if not timestamps:
                return None

            df = pd.DataFrame({
                "Close": quotes.get("close", []),
                "Open": quotes.get("open", []),
                "High": quotes.get("high", []),
                "Low": quotes.get("low", []),
                "Volume": quotes.get("volume", []),
            }, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])

            df = df.dropna(subset=["Close", "Open"]).sort_index()
            if df.empty:
                return None
            return df
        except Exception:
            time.sleep(1.5)
    return None


def format_price(val, category):
    """Format price precision based on asset category."""
    if category == "FX":
        if val >= 100:
            return f"{val:.2f}"
        if val >= 10:
            return f"{val:.3f}"
        return f"{val:.4f}"
    return f"{val:.2f}"


def evaluate_series(item):
    """Evaluate technical setup without volume filter (suitable for Indices, Futures, and FX)."""
    symbol = item["symbol"]
    name = item["name"]
    moomoo_key = item["moomoo"]
    category = item["category"]
    group = item["group"]

    df = fetch_series_df(symbol)
    if df is None or len(df) < 105:
        return {
            "symbol": symbol,
            "name": name,
            "moomoo": moomoo_key,
            "category": category,
            "group": group,
            "status": "ERROR",
            "label": f"  ? | {name} ({symbol}) [moomoo: {moomoo_key}] | Data unavailable/insufficient",
            "passed": False,
            "ppp": "",
        }

    idx, prev_idx = len(df) - 1, len(df) - 2
    c, o = df["Close"], df["Open"]

    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    ma100 = c.rolling(100).mean()
    ma300 = c.rolling(300).mean()

    curr_val = float(c.iloc[idx])
    prev_val = float(c.iloc[prev_idx])
    pct = ((curr_val - prev_val) / prev_val) * 100 if prev_val else 0.0
    date_str = df.index[idx].strftime("%Y-%m-%d")

    cond_ma60_above = pd.notna(ma60.iloc[idx]) and curr_val > ma60.iloc[idx]
    cond_shitaban = pd.notna(ma5.iloc[idx]) and curr_val > ma5.iloc[idx]
    cond_ma20_cross_7d = any(
        pd.notna(ma20.iloc[i]) and pd.notna(ma20.iloc[i - 1])
        and c.iloc[i] > ma20.iloc[i] and c.iloc[i - 1] <= ma20.iloc[i - 1]
        for i in range(max(1, idx - 6), idx + 1)
    )
    cond_tame = pd.notna(ma5.iloc[prev_idx]) and c.iloc[prev_idx] < ma5.iloc[prev_idx]
    cond_ma60_up = pd.notna(ma60.iloc[idx]) and pd.notna(ma60.iloc[prev_idx]) and ma60.iloc[idx] > ma60.iloc[prev_idx]
    cond_ma100_up = pd.notna(ma100.iloc[idx]) and pd.notna(ma100.iloc[prev_idx]) and ma100.iloc[idx] > ma100.iloc[prev_idx]
    cond_yosen = float(o.iloc[idx]) < curr_val

    passed = all([
        cond_ma60_above,
        cond_shitaban,
        cond_ma20_cross_7d,
        cond_tame,
        cond_ma60_up,
        cond_ma100_up,
        cond_yosen,
    ])

    is_full_ppp = (
        pd.notna(ma5.iloc[idx]) and pd.notna(ma20.iloc[idx]) and
        pd.notna(ma60.iloc[idx]) and pd.notna(ma100.iloc[idx]) and
        pd.notna(ma300.iloc[idx]) and
        (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > ma300.iloc[idx])
    )
    is_short_ppp = (
        pd.notna(ma5.iloc[idx]) and pd.notna(ma20.iloc[idx]) and
        pd.notna(ma60.iloc[idx]) and pd.notna(ma100.iloc[idx]) and
        (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx])
    )
    ppp = "★ " if is_full_ppp else ("★(Short) " if is_short_ppp else "")

    mark = "PASS" if passed else "----"
    price_str = format_price(curr_val, category)
    line = (
        f"  [{mark}] {ppp}{name} ({symbol}) [moomoo: {moomoo_key}] | "
        f"{price_str} ({pct:+.2f}%) [{date_str[5:]}]"
    )

    return {
        "symbol": symbol,
        "name": name,
        "moomoo": moomoo_key,
        "category": category,
        "group": group,
        "status": "OK",
        "label": line,
        "passed": passed,
        "ppp": ppp,
        "date": date_str,
    }


def send_gmail(subject, body):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        raise ValueError("EMAIL_ADDRESS or EMAIL_PASSWORD environment variable is missing.")

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = SENDER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain", "utf-8"))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()


def main():
    results = []
    for item in WIDE_MARKET_WATCHLIST:
        results.append(evaluate_series(item))
        time.sleep(REQUEST_SLEEP_SEC)

    passed_items = [r for r in results if r.get("passed")]
    latest_dates = [r["date"] for r in results if r.get("date")]
    latest_date_str = max(latest_dates) if latest_dates else str(datetime.date.today())

    index_count = sum(1 for r in results if r.get("category") == "INDEX")
    future_count = sum(1 for r in results if r.get("category") == "FUTURE")
    fx_count = sum(1 for r in results if r.get("category") == "FX")

    passed_str = (
        "\n".join([
            f"  {r['ppp']}[PASS] {r['name']} ({r['symbol']}) [moomoo: {r['moomoo']}] [{r['date'][5:]}]"
            for r in passed_items
        ])
        or "  None"
    )

    grouped_sections = []
    for grp in GROUP_ORDER:
        grp_lines = [r["label"] for r in results if r.get("group") == grp]
        if grp_lines:
            grouped_sections.append(
                f"=== {grp} ({len(grp_lines)}) ===\n" + "\n".join(grp_lines)
            )

    body = (
        f"adoGEM Weekly Multi-Asset Screener — Indices, Futures & FX\n"
        f"Latest Daily Close Date: {latest_date_str}\n"
        f"Coverage Summary: {len(WIDE_MARKET_WATCHLIST)} instruments total "
        f"(Indices: {index_count} | Futures: {future_count} | FX: {fx_count})\n"
        f"Technical Filter Passed: {len(passed_items)}\n\n"
        f"=== PASSED SIGNALS ===\n{passed_str}\n\n"
        + "\n\n".join(grouped_sections)
        + "\n\n"
        f"Notes:\n"
        f"- Volume filter is excluded for non-equity instruments (Indices, Futures, FX).\n"
        f"- Rules: Close > MA60, Close > MA5, MA20 bullish cross within 7 days, "
        f"prior Close < MA5, rising MA60 & MA100, and bullish daily candle (Close > Open).\n"
        f"- Survival Logic by adoGEM, a Japanese Salaryman in His 50s."
    )

    subject = f"adoGEM Multi-Asset [{latest_date_str}] ({len(passed_items)} Pass)"
    send_gmail(subject, body)
    print("English multi-asset report email sent successfully.")


if __name__ == "__main__":
    main()
