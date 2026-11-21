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

# --- グローバル変数 ---
stage_survivors = {f"stage{i}": 0 for i in range(1, 11)}
stats = {"★": 0, "★(Short)": 0, "normal_detect": 0}
selected_stocks = {}
GLOBAL_LATEST_DATE = None

# 米国株の低位ペニー株排除の最低株価閾値（$5.00 未満をペニー株として除外）
MIN_PRICE = 5.0

# ゆっくり取得するための待機時間（秒）。全銘柄対象のため 429 制限回避を優先
REQUEST_SLEEP_SEC = 0.6

# 動作確認や時間短縮したい場合は整数を指定（例: 200）、全件スキャンする場合は None
MAX_SCAN_LIMIT = None

# 取得失敗時のフォールバック用ティッカー
FALLBACK_US_SYMBOLS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
    "AVGO", "JPM", "LLY", "V", "UNH", "XOM", "COST", "MA", "PG", "HD",
    "JNJ", "ABBV", "BAC", "CRM", "NFLX", "AMD", "KO", "MRK", "CVX", "PEP"
]


def fetch_us_target_symbols():
    """SECの company_tickers.json から米国上場銘柄ティッカーを取得する"""
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {
        "User-Agent": "adoGEM-Screener/1.0 (contact@example.com)",
        "Accept-Encoding": "gzip, deflate",
    }
    try:
        res = requests.get(url, headers=headers, timeout=20)
        res.raise_for_status()
        data = res.json()

        symbols = []
        seen = set()
        for _, entry in data.items():
            raw_ticker = str(entry.get("ticker", "")).strip().upper()
            if not raw_ticker:
                continue

            if any(ch in raw_ticker for ch in ["^", "/", "$"]):
                continue
            if len(raw_ticker) > 5 and raw_ticker.endswith(("W", "WS", "U", "R")):
                continue

            yf_symbol = raw_ticker.replace(".", "-")
            if yf_symbol not in seen:
                seen.add(yf_symbol)
                symbols.append(yf_symbol)

        if symbols:
            if MAX_SCAN_LIMIT:
                return symbols[:MAX_SCAN_LIMIT]
            return symbols
    except Exception as e:
        print(f"SECティッカー一覧の取得に失敗したためフォールバックを使用します: {e}")

    return FALLBACK_US_SYMBOLS[:MAX_SCAN_LIMIT] if MAX_SCAN_LIMIT else FALLBACK_US_SYMBOLS


def fetch_global_latest_date():
    """S&P 500 (^GSPC) の最新取引日を基準日として取得"""
    global GLOBAL_LATEST_DATE
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?range=1mo&interval=1d&nocache={int(time.time())}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        timestamps = res.json().get("chart", {}).get("result", [])[0].get("timestamp", [])
        GLOBAL_LATEST_DATE = datetime.datetime.fromtimestamp(timestamps[-1]).date()
    except Exception:
        now = datetime.datetime.now()
        target = now.date() - datetime.timedelta(days=1)
        while target.weekday() >= 5:
            target -= datetime.timedelta(days=1)
        GLOBAL_LATEST_DATE = target


def get_stock_data_fallback(symbol, force_check_date=True):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5y&interval=1d&nocache={int(time.time())}"

    for attempt in range(3):
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 429:
                wait_sec = 5 * (attempt + 1)
                time.sleep(wait_sec)
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
                "Volume": quotes.get("volume", [])
            }, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])

            df = df.dropna().sort_index()
            if df.empty:
                return None

            if force_check_date and GLOBAL_LATEST_DATE and df.index[-1].date() != GLOBAL_LATEST_DATE:
                return None

            return df
        except Exception:
            time.sleep(1.5)
    return None


def get_market_index_evaluation_line():
    lines = ["【主要指数の状況（米国）】"]
    indices = [
        ("^GSPC", "S&P 500", "pt"),
        ("^IXIC", "NASDAQ総合", "pt"),
        ("^DJI", "NYダウ", "pt"),
    ]
    for idx_code, idx_name, unit in indices:
        try:
            encoded_code = idx_code.replace("^", "%5E")
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_code}?range=5d&interval=1d"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            data = res.json()["chart"]["result"][0]
            close = data["indicators"]["quote"][0]["close"]
            ts = data["timestamp"]
            df = pd.DataFrame(
                {"Close": close},
                index=[datetime.datetime.fromtimestamp(t).date() for t in ts]
            ).dropna()

            curr_val, prev_val = df.iloc[-1]["Close"], df.iloc[-2]["Close"]
            curr_date, prev_date = df.index[-1], df.index[-2]
            pct = ((curr_val - prev_val) / prev_val) * 100
            mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
            lines.append(
                f"  {mark} | {idx_name} | {prev_val:.2f}{unit} ({prev_date.strftime('%m-%d')}) "
                f"→ {curr_val:.2f}{unit} ({curr_date.strftime('%m-%d')}) ({pct:+.2f}%)"
            )
        except Exception as e:
            lines.append(f"  {idx_name} 取得エラー: {e}")
    return "\n".join(lines)


def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None:
        return "SKIP"

    idx, prev_idx = len(df) - 1, len(df) - 2
    if idx < 100:
        return "SKIP"

    c, o, v = df['Close'], df['Open'], df['Volume']

    stage_survivors["stage1"] += 1

    # 最低株価フィルター（低位ペニー株の除外）
    if c.iloc[idx] < MIN_PRICE:
        return "SKIP"
    stage_survivors["stage2"] += 1

    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    ma100 = c.rolling(100).mean()
    ma300 = c.rolling(300).mean()

    if pd.isna(ma60.iloc[idx]) or c.iloc[idx] <= ma60.iloc[idx]:
        return "SKIP"
    stage_survivors["stage3"] += 1

    if v.iloc[idx] < 60000:
        return "SKIP"
    stage_survivors["stage4"] += 1

    if pd.isna(ma5.iloc[idx]) or c.iloc[idx] <= ma5.iloc[idx]:
        return "SKIP"
    stage_survivors["stage5"] += 1

    if not any(
        pd.notna(ma20.iloc[i]) and pd.notna(ma20.iloc[i - 1])
        and c.iloc[i] > ma20.iloc[i] and c.iloc[i - 1] <= ma20.iloc[i - 1]
        for i in range(max(1, idx - 6), idx + 1)
    ):
        return "SKIP"
    stage_survivors["stage6"] += 1

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

    date_str = df.index[idx].strftime("%Y-%m-%d")

    conditions = [
        (pd.notna(ma5.iloc[prev_idx]) and c.iloc[prev_idx] < ma5.iloc[prev_idx], "stage7"),
        (pd.notna(ma60.iloc[idx]) and pd.notna(ma60.iloc[prev_idx]) and ma60.iloc[idx] > ma60.iloc[prev_idx], "stage8"),
        (pd.notna(ma100.iloc[idx]) and pd.notna(ma100.iloc[prev_idx]) and ma100.iloc[idx] > ma100.iloc[prev_idx], "stage9"),
        (o.iloc[idx] < c.iloc[idx], "stage10")
    ]

    for cond, stage in conditions:
        if not cond:
            return "SKIP"
        stage_survivors[stage] += 1

    selected_stocks[symbol] = {
        "price": round(float(c.iloc[idx]), 2),
        "currency": "USD",
        "ppp_label": ppp,
        "date": date_str
    }

    if "★ " in ppp:
        stats["★"] += 1
    elif "★(Short) " in ppp:
        stats["★(Short)"] += 1
    else:
        stats["normal_detect"] += 1

    return "OK"


def send_gmail(subject, body):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        raise ValueError("環境変数 EMAIL_ADDRESS または EMAIL_PASSWORD が設定されていません。")

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()


def main():
    fetch_global_latest_date()
    us_symbols = fetch_us_target_symbols()

    for symbol in us_symbols:
        analyze_stock(symbol)
        time.sleep(REQUEST_SLEEP_SEC)

    newline = "\n"
    final_list_str = newline.join([
        f"  {s['ppp_label']}■ {code} | {s['price']} {s['currency']} ({s['date'][5:]})"
        for code, s in sorted(selected_stocks.items())
    ])

    conditions_text = (
        f"【条件一覧（adoGEM共通ロジック）】\n"
        f"1. 全データ取得成功\n2. 最低株価フィルタ(>={MIN_PRICE:.1f} USD)\n3. 日足MA60上抜け\n"
        f"4. 出来高6万株以上\n5. 下半身(終値>MA5)\n6. MA20上抜け後7日以内\n"
        f"7. 溜め(前日終値<MA5)\n8. 右肩上がり(MA60)\n9. 長期トレンド(MA100上昇)\n"
        f"10. 当日陽線(始値<終値)"
    )

    body = (
        f"サバイバル投資家adoGEM【米国株 週次レポート】\n"
        f"データ対象日(完全一致): {GLOBAL_LATEST_DATE}\n"
        f"スキャン対象数: {len(us_symbols)}銘柄\n\n"
        f"【各ステージ生存数】\n" +
        newline.join([
            f"{i+1}.{label}: {stage_survivors[f'stage{i+1}']}"
            for i, label in enumerate([
                "取得", f"株価>={MIN_PRICE:.1f}", "日足60", "出来高", "下半身",
                "日足MA20上抜け", "溜め", "右肩", "長期T", "当日陽線"
            ])
        ]) + "\n\n"
        f"★: {stats['★']} / Short: {stats['★(Short)']} / 通常: {stats['normal_detect']}\n\n"
        f"【完全合格一覧（週末配信候補）】\n{final_list_str or '  該当なし'}\n\n"
        f"{get_market_index_evaluation_line()}\n\n"
        f"{conditions_text}\n\n"
        f"--------------------------------------------------\n"
        f"【English Title / Description】\n"
        f"Crystal Clear at a Glance! Weekly US Stock Picks ({GLOBAL_LATEST_DATE.month}/{GLOBAL_LATEST_DATE.day} Close) [adoGEM Quant Screener]\n"
        f"Survival Logic by adoGEM, a Japanese Salaryman in His 50s (Weekly US Stock Picks)\n"
        f"--------------------------------------------------"
    )

    subject = f"🇺🇸📊 adoGEM 米国株 週次レポート ({GLOBAL_LATEST_DATE})"
    send_gmail(subject, body)
    print("米国株レポートのGmail送信が完了しました。")


if __name__ == "__main__":
    main()
