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

# --- スキャン対象：中国本土（上海.SS / 深セン.SZ）・香港（.HK）主要数百銘柄ユニバース ---
CHINA_TARGET_SYMBOLS = [
    # --- 香港メインボード・主要大型株 (.HK) ---
    "0001.HK", "0002.HK", "0003.HK", "0005.HK", "0006.HK", "0011.HK", "0012.HK", "0016.HK", "0017.HK", "0027.HK",
    "0066.HK", "0083.HK", "0101.HK", "0135.HK", "0151.HK", "0165.HK", "0175.HK", "0267.HK", "0288.HK", "0291.HK",
    "0386.HK", "0388.HK", "0669.HK", "0688.HK", "0700.HK", "0762.HK", "0823.HK", "0836.HK", "0857.HK", "0883.HK",
    "0939.HK", "0941.HK", "0960.HK", "0981.HK", "0992.HK", "1038.HK", "1044.HK", "1088.HK", "1093.HK", "1109.HK",
    "1113.HK", "1177.HK", "1211.HK", "1288.HK", "1299.HK", "1398.HK", "1810.HK", "1928.HK", "1997.HK", "2007.HK",
    "2015.HK", "2020.HK", "2269.HK", "2313.HK", "2318.HK", "2319.HK", "2382.HK", "2388.HK", "2628.HK", "2688.HK",
    "2888.HK", "3328.HK", "3690.HK", "3800.HK", "3968.HK", "3988.HK", "6030.HK", "6618.HK", "6690.HK", "9618.HK",
    "9633.HK", "9866.HK", "9868.HK", "9888.HK", "9961.HK", "9988.HK", "9999.HK",

    # --- 上海A株・主要優良株 (.SS) ---
    "600000.SS", "600009.SS", "600010.SS", "600015.SS", "600016.SS", "600018.SS", "600025.SS", "600028.SS", "600029.SS", "600030.SS",
    "600031.SS", "600036.SS", "600048.SS", "600050.SS", "600060.SS", "600104.SS", "600111.SS", "600115.SS", "600150.SS", "600176.SS",
    "600196.SS", "600276.SS", "600309.SS", "600332.SS", "600346.SS", "600362.SS", "600383.SS", "600406.SS", "600436.SS", "600438.SS",
    "600519.SS", "600547.SS", "600570.SS", "600585.SS", "600606.SS", "600660.SS", "600690.SS", "600741.SS", "600760.SS", "600809.SS",
    "600837.SS", "600886.SS", "600887.SS", "600900.SS", "600919.SS", "600926.SS", "600941.SS", "600989.SS", "601006.SS", "601012.SS",
    "601021.SS", "601066.SS", "601088.SS", "601111.SS", "601138.SS", "601166.SS", "601169.SS", "601186.SS", "601211.SS", "601225.SS",
    "601229.SS", "601238.SS", "601288.SS", "601318.SS", "601328.SS", "601336.SS", "601360.SS", "601390.SS", "601398.SS", "601601.SS",
    "601607.SS", "601618.SS", "601628.SS", "601633.SS", "601668.SS", "601688.SS", "601727.SS", "601728.SS", "601766.SS", "601800.SS",
    "601816.SS", "601818.SS", "601857.SS", "601888.SS", "601898.SS", "601899.SS", "601901.SS", "601919.SS", "601939.SS", "601985.SS",
    "601988.SS", "601989.SS", "601998.SS", "603259.SS", "603288.SS", "603501.SS", "603799.SS", "603986.SS", "688041.SS", "688111.SS",
    "688981.SS",

    # --- 深センA株・主要優良株 (.SZ) ---
    "000001.SZ", "000002.SZ", "000063.SZ", "000069.SZ", "000100.SZ", "000166.SZ", "000333.SZ", "000338.SZ", "000408.SZ", "000538.SZ",
    "000568.SZ", "000625.SZ", "000651.SZ", "000725.SZ", "000768.SZ", "000776.SZ", "000858.SZ", "000877.SZ", "000895.SZ", "000938.SZ",
    "000963.SZ", "002001.SZ", "002007.SZ", "002024.SZ", "002027.SZ", "002049.SZ", "002050.SZ", "002120.SZ", "002142.SZ", "002230.SZ",
    "002241.SZ", "002252.SZ", "002304.SZ", "002352.SZ", "002371.SZ", "002415.SZ", "002460.SZ", "002475.SZ", "002555.SZ", "002594.SZ",
    "002714.SZ", "002736.SZ", "002812.SZ", "300014.SZ", "300015.SZ", "300033.SZ", "300059.SZ", "300122.SZ", "300124.SZ", "300142.SZ",
    "300274.SZ", "300347.SZ", "300408.SZ", "300413.SZ", "300454.SZ", "300498.SZ", "300502.SZ", "300601.SZ", "300628.SZ", "300750.SZ",
    "300760.SZ", "300999.SZ"
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
        ("^HSI", "ハンセン指数(香港)", "pt"),
        ("000001.SS", "上海総合指数", "pt")
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
    
    next_day = GLOBAL_LATEST_DATE + datetime.timedelta(days=1)
    while next_day.weekday() >= 5:
        next_day += datetime.timedelta(days=1)
        
    for symbol in CHINA_TARGET_SYMBOLS:
        analyze_stock(symbol)
        time.sleep(0.3)  # APIレート制限回避のためのウェイト
        
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
        f"サバイバル投資家adoGEM【中国株・香港株 週次レポート】\n"
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
        f"【Bilibili / SNS 週末配信用テンプレート】\n"
        f"{next_day.month}/{next_day.day} 見るだけ！今週の注目中国株3選 ({GLOBAL_LATEST_DATE.month}/{GLOBAL_LATEST_DATE.day}引け基準)🔥\n"
        f"週末限定公開！\n"
        f"※個人の研究記録/投資は自己責任で\n"
        f"Survival Investor adoGEM\n"
        f"#中国株 #香港株 #adoGEM #A股 #港股 #テクニカル分析\n"
        f"----------------------\n"
        f"【Bilibili 中文版标题/简介】\n"
        f"看一眼就懂！本周精选中国股票 ({GLOBAL_LATEST_DATE.month}/{GLOBAL_LATEST_DATE.day} 收盘数据) 【adoGEM量化筛选】\n"
        f"50多岁日本上班族的adoGEM生存逻辑（A股/港股每周精选）\n"
        f"--------------------------------------------------"
    )
        
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"🇨🇳📊 adoGEM 中国株・香港株 週次レポート ({GLOBAL_LATEST_DATE})"
    msg.attach(MIMEText(body, 'plain'))
    
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(SENDER_EMAIL, SENDER_PASSWORD)
    server.send_message(msg)
    server.quit()
    print("中国株レポートのGmail送信が完了しました。")

if __name__ == "__main__":
    main()
