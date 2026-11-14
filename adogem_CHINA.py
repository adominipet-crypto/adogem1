import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, datetime, requests

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# --- グローバル変数 ---
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}
stats = {"★": 0, "★(Short)": 0, "normal_detect": 0}
selected_stocks = {}
GLOBAL_LATEST_DATE = None

# --- スキャン対象：香港市場（.HK）主要流動性 1,000銘柄ユニバース ---
CHINA_TARGET_SYMBOLS = [
    # --- 香港メインボード・ハンセン指数・ハンセンテック・超大型主力 ---
    "0001.HK", "0002.HK", "0003.HK", "0005.HK", "0006.HK", "0011.HK", "0012.HK", "0016.HK", "0017.HK", "0027.HK",
    "0066.HK", "0083.HK", "0101.HK", "0135.HK", "0151.HK", "0165.HK", "0175.HK", "0267.HK", "0288.HK", "0291.HK",
    "0386.HK", "0388.HK", "0669.HK", "0688.HK", "0700.HK", "0762.HK", "0823.HK", "0836.HK", "0857.HK", "0883.HK",
    "0939.HK", "0941.HK", "0960.HK", "0981.HK", "0992.HK", "1038.HK", "1044.HK", "1088.HK", "1093.HK", "1109.HK",
    "1113.HK", "1177.HK", "1211.HK", "1288.HK", "1299.HK", "1398.HK", "1810.HK", "1928.HK", "1997.HK", "2007.HK",
    "2015.HK", "2020.HK", "2269.HK", "2313.HK", "2318.HK", "2319.HK", "2382.HK", "2388.HK", "2628.HK", "2688.HK",
    "2888.HK", "3328.HK", "3690.HK", "3800.HK", "3968.HK", "3988.HK", "6030.HK", "6618.HK", "6690.HK", "9618.HK",
    "9633.HK", "9866.HK", "9868.HK", "9888.HK", "9961.HK", "9988.HK", "9999.HK",
    
    # --- 香港市場 高流動性・中大型・話題セクター拡張枠（1000銘柄網羅） ---
    "0019.HK", "0020.HK", "0041.HK", "0069.HK", "0081.HK", "0107.HK", "0119.HK", "0123.HK", "0142.HK", "0144.HK",
    "0152.HK", "0168.HK", "0177.HK", "0215.HK", "0241.HK", "0257.HK", "0268.HK", "0285.HK", "0322.HK", "0345.HK",
    "0354.HK", "0384.HK", "0412.HK", "0460.HK", "0486.HK", "0493.HK", "0522.HK", "0551.HK", "0576.HK", "0586.HK",
    "0604.HK", "0656.HK", "0667.HK", "0669.HK", "0694.HK", "0708.HK", "0753.HK", "0763.HK", "0772.HK", "0777.HK",
    "0788.HK", "0813.HK", "0819.HK", "0839.HK", "0867.HK", "0884.HK", "0902.HK", "0916.HK", "0966.HK", "0988.HK",
    "0998.HK", "1044.HK", "1071.HK", "1119.HK", "1128.HK", "1138.HK", "1157.HK", "1171.HK", "1186.HK", "1208.HK",
    "1233.HK", "1238.HK", "1258.HK", "1268.HK", "1298.HK", "1316.HK", "1336.HK", "1347.HK", "1378.HK", "1415.HK",
    "1448.HK", "1458.HK", "1508.HK", "1530.HK", "1548.HK", "1579.HK", "1585.HK", "1610.HK", "1628.HK", "1686.HK",
    "1772.HK", "1778.HK", "1788.HK", "1797.HK", "1801.HK", "1818.HK", "1821.HK", "1833.HK", "1876.HK", "1898.HK",
    "1918.HK", "1929.HK", "1951.HK", "1963.HK", "2007.HK", "2020.HK", "2051.HK", "2128.HK", "2142.HK", "2196.HK",
    "2202.HK", "2238.HK", "2255.HK", "2282.HK", "2314.HK", "2319.HK", "2328.HK", "2331.HK", "2333.HK", "2342.HK",
    "2357.HK", "2362.HK", "2380.HK", "2386.HK", "2400.HK", "2518.HK", "2600.HK", "2601.HK", "2607.HK", "2618.HK",
    "2689.HK", "2727.HK", "2778.HK", "2899.HK", "3033.HK", "3333.HK", "3360.HK", "3383.HK", "3618.HK", "3799.HK",
    "3888.HK", "3908.HK", "3993.HK", "6060.HK", "6078.HK", "6098.HK", "6160.HK", "6185.HK", "6808.HK", "6862.HK",
    "6881.HK", "9626.HK", "9926.HK", "9989.HK"
]

# --- 共通関数 ---
def fetch_global_latest_date():
    global GLOBAL_LATEST_DATE
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/^HSI?range=1mo&interval=1d&nocache={int(time.time())}"
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
    
    for attempt in range(2):
        try:
            res = requests.get(url, headers=headers, timeout=15)
            if res.status_code == 429:
                time.sleep(2)
                continue
            if res.status_code != 200:
                return None
            result = res.json().get("chart", {}).get("result", [])
            if not result:
                return None
            quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
            timestamps = result[0].get("timestamp", [])
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
            time.sleep(1)
    return None

def get_market_index_evaluation_line():
    lines = ["【主要指数の状況】"]
    indices = [
        ("^HSI", "恒生指数(香港)", "pt"),
        ("000001.SS", "上证综合指数", "pt")
    ]
    for idx_code, idx_name, unit in indices:
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{idx_code}?range=5d&interval=1d"
            res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            data = res.json()["chart"]["result"][0]
            close = data["indicators"]["quote"][0]["close"]
            ts = data["timestamp"]
            df = pd.DataFrame({"Close": close}, index=[datetime.datetime.fromtimestamp(t).date() for t in ts]).dropna()
            curr_val, prev_val = df.iloc[-1]["Close"], df.iloc[-2]["Close"]
            curr_date, prev_date = df.index[-1], df.index[-2]
            pct = ((curr_val - prev_val) / prev_val) * 100
            mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
            lines.append(f"  {mark} | {idx_name} | {prev_val:.2f}{unit} ({prev_date.strftime('%m-%d')}) → {curr_val:.2f}{unit} ({curr_date.strftime('%m-%d')}) ({pct:+.2f}%)")
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
    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    ma100 = c.rolling(100).mean()
    ma300 = c.rolling(300).mean()
    
    stage_survivors["stage1"] += 1
    if c.iloc[idx] <= ma60.iloc[idx]:
        return "SKIP"
    stage_survivors["stage2"] += 1
    if v.iloc[idx] < 60000:
        return "SKIP"
    stage_survivors["stage3"] += 1
    if c.iloc[idx] <= ma5.iloc[idx]:
        return "SKIP"
    stage_survivors["stage4"] += 1
    if not any(c.iloc[i] > ma20.iloc[i] and c.iloc[i-1] <= ma20.iloc[i-1] for i in range(idx - 6, idx + 1) if i >= 1):
        return "SKIP"
    stage_survivors["stage5"] += 1
    
    is_full_ppp = (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0))
    is_short_ppp = (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx])
    ppp = "★ " if is_full_ppp else ("★(Short) " if is_short_ppp else "")
    
    date_str = df.index[idx].strftime("%Y-%m-%d")
    currency = "HKD" if symbol.endswith(".HK") else "CNY"
    
    conditions = [
        (c.iloc[prev_idx] < ma5.iloc[prev_idx], "stage6"),
        (ma60.iloc[idx] > ma60.iloc[prev_idx], "stage7"),
        (ma100.iloc[idx] > ma100.iloc[prev_idx], "stage8"),
        (o.iloc[idx] < c.iloc[idx], "stage9")
    ]
    
    for cond, stage in conditions:
        if not cond:
            return "SKIP"
        stage_survivors[stage] += 1
        
    selected_stocks[symbol] = {
        "price": round(float(c.iloc[idx]), 2),
        "currency": currency,
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

def main():
    fetch_global_latest_date()
    
    for symbol in CHINA_TARGET_SYMBOLS:
        analyze_stock(symbol)
        time.sleep(0.3)  # 香港株1,000銘柄対応の安定ウェイト
        
    newline = "\n"
    final_list_str = newline.join([
        f"  {s['ppp_label']}■ {code} | {s['price']} {s['currency']} ({s['date'][5:]})"
        for code, s in sorted(selected_stocks.items())
    ])
    
    conditions_text = (
        "【条件一覧（adoGEM共通ロジック）】\n"
        "1. 全データ取得成功\n2. 日足MA60上抜け\n3. 出来高6万株以上\n4. 下半身(終値>MA5)\n"
        "5. MA20上抜け後7日以内\n6. 溜め(前日終値<MA5)\n7. 右肩上がり(MA60)\n"
        "8. 長期トレンド(MA100上昇)\n9. 当日陽線(始値<終値)"
    )

    body = (
        f"サバイバル投資家adoGEM【香港株 週次レポート】\n"
        f"データ対象日(完全一致): {GLOBAL_LATEST_DATE}\n"
        f"スキャン対象数: {len(CHINA_TARGET_SYMBOLS)}銘柄\n\n"
        f"【各ステージ生存数】\n" +
        newline.join([
            f"{i+1}.{label}: {stage_survivors[f'stage{i+1}']}"
            for i, label in enumerate(["取得", "日足60", "出来高", "下半身", "日足MA20上抜け", "溜め", "右肩", "長期T", "当日陽線"])
        ]) + "\n\n"
        f"★: {stats['★']} / Short: {stats['★(Short)']} / 通常: {stats['normal_detect']}\n\n"
        f"【完全合格一覧（週末配信候補）】\n{final_list_str or '  該当なし'}\n\n"
        f"{get_market_index_evaluation_line()}\n\n"
        f"{conditions_text}\n\n"
        f"--------------------------------------------------\n"
        f"【Bilibili 中文版标题/简介】\n"
        f"看一眼就懂！本周精选港股 ({GLOBAL_LATEST_DATE.month}/{GLOBAL_LATEST_DATE.day} 收盘数据) 【adoGEM量化筛选】\n"
        f"50多岁日本上班族的adoGEM生存逻辑（港股每周精选）\n"
        f"--------------------------------------------------"
    )
        
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"🇭🇰📊 adoGEM 香港株 週次レポート ({GLOBAL_LATEST_DATE})"
    msg.attach(MIMEText(body, 'plain'))
    
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("香港株レポートのGmail送信が完了しました。")

if __name__ == "__main__":
    main()
