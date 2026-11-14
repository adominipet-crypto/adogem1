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
stage_survivors = {f"stage{i}": 0 for i in range(1, 11)}
stats = {"★": 0, "★(Short)": 0, "normal_detect": 0}
selected_stocks = {}
GLOBAL_LATEST_DATE = None
MIN_PRICE = 1.0  # 低位ペニー株排除のための最低株価閾値 (1.0 HKD未満をスキップ)

# --- スキャン対象：香港メインボード全域（超大型・主力・中小型を網羅するフルユニバース） ---
CHINA_TARGET_SYMBOLS = []

# 1. 0001.HK から 3999.HK までの主要メインボード番号帯を網羅
# （実在する連続・主要コードをカバー）
for i in range(1, 4000):
    CHINA_TARGET_SYMBOLS.append(f"{i:04d}.HK")

# 2. 6000番台・8000番台・9000番台の主要テック、新興、高配当、大型銘柄
extra_hk_ranges = [
    range(6000, 6100),  # 主要な香港上場ETFや大型・準大手
    range(6800, 6900),
    range(9600, 10000)  # 代表的なハイテク・新興企業（テンセント系、アリババ系、美団など）
]

for r in extra_hk_ranges:
    for i in r:
        sym = f"{i:04d}.HK"
        if sym not in CHINA_TARGET_SYMBOLS:
            CHINA_TARGET_SYMBOLS.append(sym)

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
    
    if c.iloc[idx] <= ma60.iloc[idx]:
        return "SKIP"
    stage_survivors["stage3"] += 1
    
    if v.iloc[idx] < 60000:
        return "SKIP"
    stage_survivors["stage4"] += 1
    
    if c.iloc[idx] <= ma5.iloc[idx]:
        return "SKIP"
    stage_survivors["stage5"] += 1
    
    if not any(c.iloc[i] > ma20.iloc[i] and c.iloc[i-1] <= ma20.iloc[i-1] for i in range(idx - 6, idx + 1) if i >= 1):
        return "SKIP"
    stage_survivors["stage6"] += 1
    
    is_full_ppp = (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0))
    is_short_ppp = (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx])
    ppp = "★ " if is_full_ppp else ("★(Short) " if is_short_ppp else "")
    
    date_str = df.index[idx].strftime("%Y-%m-%d")
    currency = "HKD" if symbol.endswith(".HK") else "CNY"
    
    conditions = [
        (c.iloc[prev_idx] < ma5.iloc[prev_idx], "stage7"),
        (ma60.iloc[idx] > ma60.iloc[prev_idx], "stage8"),
        (ma100.iloc[idx] > ma100.iloc[prev_idx], "stage9"),
        (o.iloc[idx] < c.iloc[idx], "stage10")
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
        time.sleep(0.3)  # フルメインボード規模に対応する安定ウェイト
        
    newline = "\n"
    final_list_str = newline.join([
        f"  {s['ppp_label']}■ {code} | {s['price']} {s['currency']} ({s['date'][5:]})"
        for code, s in sorted(selected_stocks.items())
    ])
    
    conditions_text = (
        "【条件一覧（adoGEM共通ロジック）】\n"
        "1. 全データ取得成功\n2. 最低株価フィルタ(>=1.0 HKD)\n3. 日足MA60上抜け\n4. 出来高6万株以上\n5. 下半身(終値>MA5)\n"
        "6. MA20上抜け後7日以内\n7. 溜め(前日終値<MA5)\n8. 右肩上がり(MA60)\n"
        "9. 長期トレンド(MA100上昇)\n10. 当日陽線(始値<終値)"
    )

    body = (
        f"サバイバル投資家adoGEM【香港株 週次レポート】\n"
        f"データ対象日(完全一致): {GLOBAL_LATEST_DATE}\n"
        f"スキャン対象数: {len(CHINA_TARGET_SYMBOLS)}銘柄\n\n"
        f"【各ステージ生存数】\n" +
        newline.join([
            f"{i+1}.{label}: {stage_survivors[f'stage{i+1}']}"
            for i, label in enumerate(["取得", "株価>=1.0", "日足60", "出来高", "下半身", "日足MA20上抜け", "溜め", "右肩", "長期T", "当日陽線"])
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
