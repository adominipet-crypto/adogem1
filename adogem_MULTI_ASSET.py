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

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# --- 指数・先物・為替 ワイド統合リスト（75件） ---
# category: "INDEX" | "FUTURE" | "FX"
# group: 日本語グループ名
WIDE_MARKET_WATCHLIST = [
    # 1. 主要指数・ボラティリティ指数（14件）
    {"symbol": "^GSPC", "name": "S&P 500 Index", "moomoo": "S&P 500 / SPX", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^IXIC", "name": "NASDAQ Composite", "moomoo": "NASDAQ / IXIC", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^DJI", "name": "Dow Jones Industrial Average", "moomoo": "Dow / DJI", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^RUT", "name": "Russell 2000 Index", "moomoo": "Russell 2000 / RUT", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^NDX", "name": "NASDAQ-100 Index", "moomoo": "NASDAQ 100 / NDX", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^NYA", "name": "NYSE Composite Index", "moomoo": "NYSE Composite", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^SOX", "name": "PHLX Semiconductor Index", "moomoo": "SOX / Semiconductor", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^VIX", "name": "CBOE Volatility Index", "moomoo": "VIX", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^VXN", "name": "NASDAQ-100 Volatility Index", "moomoo": "VXN", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^RVX", "name": "Russell 2000 Volatility Index", "moomoo": "RVX", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^N225", "name": "Nikkei 225", "moomoo": "Nikkei 225", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^HSI", "name": "Hang Seng Index", "moomoo": "Hang Seng / HSI", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^FTSE", "name": "FTSE 100 Index", "moomoo": "FTSE 100", "category": "INDEX", "group": "指数・ボラティリティ"},
    {"symbol": "^GDAXI", "name": "DAX Performance Index", "moomoo": "DAX", "category": "INDEX", "group": "指数・ボラティリティ"},

    # 2. 株価指数先物（8件）
    {"symbol": "ES=F", "name": "E-mini S&P 500 Futures", "moomoo": "E-mini S&P 500", "category": "FUTURE", "group": "株価指数先物"},
    {"symbol": "NQ=F", "name": "E-mini NASDAQ-100 Futures", "moomoo": "E-mini NASDAQ 100", "category": "FUTURE", "group": "株価指数先物"},
    {"symbol": "YM=F", "name": "E-mini Dow Futures", "moomoo": "E-mini Dow", "category": "FUTURE", "group": "株価指数先物"},
    {"symbol": "RTY=F", "name": "E-mini Russell 2000 Futures", "moomoo": "E-mini Russell 2000", "category": "FUTURE", "group": "株価指数先物"},
    {"symbol": "NKD=F", "name": "Nikkei 225 USD Futures", "moomoo": "Nikkei Futures", "category": "FUTURE", "group": "株価指数先物"},
    {"symbol": "FDAX=F", "name": "DAX Futures", "moomoo": "DAX Futures", "category": "FUTURE", "group": "株価指数先物"},
    {"symbol": "FESX=F", "name": "Euro Stoxx 50 Futures", "moomoo": "Euro Stoxx 50", "category": "FUTURE", "group": "株価指数先物"},
    {"symbol": "HSI=F", "name": "Hang Seng Index Futures", "moomoo": "Hang Seng Futures", "category": "FUTURE", "group": "株価指数先物"},

    # 3. 農産物・畜産先物（14件）
    {"symbol": "ZS=F", "name": "Soybeans Futures", "moomoo": "Soybeans", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "ZC=F", "name": "Corn Futures", "moomoo": "Corn", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "ZW=F", "name": "Chicago SRW Wheat Futures", "moomoo": "SRW Wheat", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "KE=F", "name": "KC HRW Wheat Futures", "moomoo": "HRW Wheat", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "ZO=F", "name": "Oats Futures", "moomoo": "Oats", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "ZR=F", "name": "Rough Rice Futures", "moomoo": "Rough Rice", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "ZM=F", "name": "Soybean Meal Futures", "moomoo": "Soybean Meal", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "ZL=F", "name": "Soybean Oil Futures", "moomoo": "Soybean Oil", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "KC=F", "name": "Coffee C Futures", "moomoo": "Coffee", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "SB=F", "name": "Sugar No. 11 Futures", "moomoo": "Sugar", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "CC=F", "name": "Cocoa Futures", "moomoo": "Cocoa", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "CT=F", "name": "Cotton No. 2 Futures", "moomoo": "Cotton", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "LE=F", "name": "Live Cattle Futures", "moomoo": "Live Cattle", "category": "FUTURE", "group": "農産物・畜産先物"},
    {"symbol": "HE=F", "name": "Lean Hogs Futures", "moomoo": "Lean Hogs", "category": "FUTURE", "group": "農産物・畜産先物"},

    # 4. エネルギー・金属・金利先物（15件）
    {"symbol": "CL=F", "name": "WTI Crude Oil Futures", "moomoo": "WTI Crude Oil", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "BZ=F", "name": "Brent Crude Oil Futures", "moomoo": "Brent Crude Oil", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "NG=F", "name": "Henry Hub Natural Gas Futures", "moomoo": "Natural Gas", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "RB=F", "name": "RBOB Gasoline Futures", "moomoo": "RBOB Gasoline", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "HO=F", "name": "NY Harbor ULSD Heating Oil Futures", "moomoo": "Heating Oil", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "GC=F", "name": "Gold Futures", "moomoo": "Gold", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "SI=F", "name": "Silver Futures", "moomoo": "Silver", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "PL=F", "name": "Platinum Futures", "moomoo": "Platinum", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "PA=F", "name": "Palladium Futures", "moomoo": "Palladium", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "HG=F", "name": "Copper Futures", "moomoo": "Copper", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "ALI=F", "name": "Aluminum Futures", "moomoo": "Aluminum", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "ZB=F", "name": "U.S. Treasury Bond Futures (30Y)", "moomoo": "30Y T-Bond", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "ZN=F", "name": "10-Year T-Note Futures", "moomoo": "10Y T-Note", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "ZF=F", "name": "5-Year T-Note Futures", "moomoo": "5Y T-Note", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},
    {"symbol": "ZT=F", "name": "2-Year T-Note Futures", "moomoo": "2Y T-Note", "category": "FUTURE", "group": "エネルギー・金属・金利先物"},

    # 5. 為替・ドル指数（24件）
    {"symbol": "DX-Y.NYB", "name": "US Dollar Index (DXY)", "moomoo": "DXY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDJPY=X", "name": "USD/JPY", "moomoo": "USDJPY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "EURUSD=X", "name": "EUR/USD", "moomoo": "EURUSD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "GBPUSD=X", "name": "GBP/USD", "moomoo": "GBPUSD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDCHF=X", "name": "USD/CHF", "moomoo": "USDCHF", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDCAD=X", "name": "USD/CAD", "moomoo": "USDCAD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "AUDUSD=X", "name": "AUD/USD", "moomoo": "AUDUSD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "NZDUSD=X", "name": "NZD/USD", "moomoo": "NZDUSD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "EURJPY=X", "name": "EUR/JPY", "moomoo": "EURJPY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "GBPJPY=X", "name": "GBP/JPY", "moomoo": "GBPJPY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "AUDJPY=X", "name": "AUD/JPY", "moomoo": "AUDJPY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "NZDJPY=X", "name": "NZD/JPY", "moomoo": "NZDJPY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "CADJPY=X", "name": "CAD/JPY", "moomoo": "CADJPY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "CHFJPY=X", "name": "CHF/JPY", "moomoo": "CHFJPY", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "EURGBP=X", "name": "EUR/GBP", "moomoo": "EURGBP", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "EURAUD=X", "name": "EUR/AUD", "moomoo": "EURAUD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "AUDNZD=X", "name": "AUD/NZD", "moomoo": "AUDNZD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDCNH=X", "name": "USD/CNH", "moomoo": "USDCNH", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDHKD=X", "name": "USD/HKD", "moomoo": "USDHKD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDSGD=X", "name": "USD/SGD", "moomoo": "USDSGD", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDKRW=X", "name": "USD/KRW", "moomoo": "USDKRW", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDMXN=X", "name": "USD/MXN", "moomoo": "USDMXN", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDZAR=X", "name": "USD/ZAR", "moomoo": "USDZAR", "category": "FX", "group": "為替・ドル指数"},
    {"symbol": "USDTRY=X", "name": "USD/TRY", "moomoo": "USDTRY", "category": "FX", "group": "為替・ドル指数"},
]

GROUP_ORDER = [
    "指数・ボラティリティ",
    "株価指数先物",
    "農産物・畜産先物",
    "エネルギー・金属・金利先物",
    "為替・ドル指数",
]

REQUEST_SLEEP_SEC = 0.5


def fetch_series_df(symbol):
    """Yahoo Finance v8 chart API から日足データを取得"""
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
    if category == "FX":
        if val >= 100:
            return f"{val:.2f}"
        if val >= 10:
            return f"{val:.3f}"
        return f"{val:.4f}"
    return f"{val:.2f}"


def evaluate_series(item):
    """出来高条件を除いた7条件＋PPP判定（指数・先物・為替向け）"""
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
    ppp = "★" if is_full_ppp else ("★(Short)" if is_short_ppp else "")

    price_str = format_price(curr_val, category)
    ppp_line = (
        f"  {ppp} {name} ({symbol}) [moomoo: {moomoo_key}] | "
        f"{price_str} ({pct:+.2f}%) [{date_str[5:]}]"
    )

    return {
        "symbol": symbol,
        "name": name,
        "moomoo": moomoo_key,
        "category": category,
        "group": group,
        "status": "OK",
        "ppp_line": ppp_line,
        "passed": passed,
        "ppp": ppp,
        "pct": pct,
        "price_str": price_str,
        "date": date_str,
    }


def build_youtube_title(latest_date_str, passed_count):
    """YouTube貼り付け用の英文表題"""
    return f"Weekly Market Screener: Indices, Futures & FX ({latest_date_str})"


def send_gmail(subject, body):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        raise ValueError("EMAIL_ADDRESS または EMAIL_PASSWORD 環境変数が設定されていません。")

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

    ok_items = [r for r in results if r.get("status") == "OK"]
    error_items = [r for r in results if r.get("status") != "OK"]
    passed_items = [r for r in results if r.get("passed")]
    ppp_items = [r for r in results if r.get("ppp")]
    latest_dates = [r["date"] for r in ok_items if r.get("date")]
    latest_date_str = max(latest_dates) if latest_dates else str(datetime.date.today())

    index_count = sum(1 for r in results if r.get("category") == "INDEX")
    future_count = sum(1 for r in results if r.get("category") == "FUTURE")
    fx_count = sum(1 for r in results if r.get("category") == "FX")

    youtube_title = build_youtube_title(latest_date_str, len(passed_items))

    passed_str = (
        "\n".join([
            f"  {r['ppp'] + ' ' if r['ppp'] else ''}[合格] {r['name']} ({r['symbol']}) [moomoo: {r['moomoo']}] | "
            f"{r['price_str']} ({r['pct']:+.2f}%) [{r['date'][5:]}]"
            for r in passed_items
        ])
        or "  該当なし"
    )

    ppp_grouped_sections = []
    for grp in GROUP_ORDER:
        grp_lines = [r["ppp_line"] for r in ppp_items if r.get("group") == grp]
        if grp_lines:
            ppp_grouped_sections.append(
                f"  [{grp}（{len(grp_lines)}件）]\n" + "\n".join(grp_lines)
            )
    ppp_str = "\n\n".join(ppp_grouped_sections) if ppp_grouped_sections else "  該当なし"

    error_symbols_str = (
        ", ".join([r["symbol"] for r in error_items]) if error_items else "なし"
    )

    body = (
        f"【YouTube貼り付け用 英文表題】\n"
        f"{youtube_title}\n\n"
        f"========================================\n"
        f"adoGEM 週次マルチアセット・スクリーナー（指数・先物・為替）\n"
        f"最新日足基準日: {latest_date_str}\n"
        f"対象内訳: 全{len(WIDE_MARKET_WATCHLIST)}銘柄 "
        f"（指数: {index_count} / 先物: {future_count} / 為替: {fx_count}）\n"
        f"取得銘柄数: {len(ok_items)}/{len(WIDE_MARKET_WATCHLIST)}銘柄取得 "
        f"（取得不可/不足: {len(error_items)}銘柄 → {error_symbols_str}）\n"
        f"テクニカル条件 合格数: {len(passed_items)}銘柄\n"
        f"★ / ★(Short) 該当数: {len(ppp_items)}銘柄\n\n"
        f"=== 合格銘柄一覧 ===\n{passed_str}\n\n"
        f"=== ★ / ★(Short) 銘柄一覧 ===\n{ppp_str}\n\n"
        f"=== スクリーニング条件・凡例 ===\n"
        f"  [合格条件（7項目・出来高条件は除外）]\n"
        f"   1. 当日終値 > MA60\n"
        f"   2. 当日終値 > MA5\n"
        f"   3. 7日以内にMA20を上抜け（前日以下→当日超え）\n"
        f"   4. 前日終値 < 前日MA5（押し・ため）\n"
        f"   5. 当日MA60 > 前日MA60（MA60上向き）\n"
        f"   6. 当日MA100 > 前日MA100（MA100上向き）\n"
        f"   7. 当日陽線（当日終値 > 当日始値）\n"
        f"  [PPP（パーフェクトオーダー）判定]\n"
        f"   ★       : MA5 > MA20 > MA60 > MA100 > MA300\n"
        f"   ★(Short): MA5 > MA20 > MA60 > MA100\n\n"
        f"※ 指数・先物・為替は出来高条件を除外して判定しています。\n"
        f"※ 50代サラリーマン adoGEM サバイバルロジック"
    )

    subject = f"adoGEM マルチアセット [{latest_date_str}] ({len(passed_items)}件合格)"
    send_gmail(subject, body)
    print("マルチアセット（取得銘柄数＋条件＋合格/★のみ）レポートメールを送信しました。")


if __name__ == "__main__":
    main()
