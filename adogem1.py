import os, sys, time, datetime, gspread, json, requests, smtplib
import pandas as pd
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
GCP_SA_KEY = os.environ.get('GCP_SA_KEY')

# --- グローバル変数 ---
pass_counts = {i: 0 for i in range(1, 13)}
report_qualified_details = []

# --- データ取得 ---
def get_stock_data_from_web(symbol):
    time.sleep(0.3)
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=2y&interval=1d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code != 200: return None
        result = res.json().get("chart", {}).get("result", [])
        if not result: return None
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        df = pd.DataFrame({
            "Close": quotes.get("close", []),
            "Open": quotes.get("open", []),
            "High": quotes.get("high", []),
            "Volume": quotes.get("volume", [])
        }, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        return df.dropna().sort_index()
    except: return None

# --- 判定ロジック（移植済み） ---
def analyze_stock(code, df):
    global pass_counts, report_qualified_details
    
    # 【修正】今日ではなく「データの最終日」をターゲットにする（週末や夜間対策）
    idx = len(df) - 1
    if idx < 100: return # データ不足
    prev_idx = idx - 1
    
    c = df['Close']; o = df['Open']; h = df['High']; v = df['Volume']
    ma5 = c.rolling(5).mean(); ma60 = c.rolling(60).mean(); ma100 = c.rolling(100).mean()
    ma24_m = c.rolling(24*20).mean() # 月足相当
    
    # 1. 取得成功はメイン側で判定済みなのでスキップ
    pass_counts[1] += 1
    
    # 2. 月足60 (簡易的にMA24*20で計算)
    if c.iloc[idx] > ma24_m.iloc[idx]: pass_counts[2] += 1
    else: return
    
    # 3. 出来高
    if v.iloc[idx] >= 50000: pass_counts[3] += 1
    else: return
    
    # 4. 下半身
    if c.iloc[idx] > ma5.iloc[idx]: pass_counts[4] += 1
    else: return
    
    # 5. 溜め
    if c.iloc[prev_idx] < ma5.iloc[prev_idx]: pass_counts[5] += 1
    else: return
    
    # 6. 右肩上がり (直近のMA60が上昇中)
    if ma60.iloc[idx] > ma60.iloc[prev_idx]: pass_counts[6] += 1
    else: return
    
    # 7. 長期T (MA100上昇中)
    if ma100.iloc[idx] > ma100.iloc[prev_idx]: pass_counts[7] += 1
    else: return
    
    # 8. 上ヒゲ回避
    upper = h.iloc[idx] - max(o.iloc[idx], c.iloc[idx])
    body = abs(c.iloc[idx] - o.iloc[idx])
    if body == 0 or (upper <= (body * 1.5)): pass_counts[8] += 1
    else: return
    
    # 9. 天井圏回避
    if abs(c.iloc[idx] - ma100.iloc[idx]) / ma100.iloc[idx] >= 0.03: pass_counts[9] += 1
    else: return
    
    # 10. 新高値
    if ma5.iloc[idx] >= ma5.rolling(20).max().iloc[idx]: pass_counts[10] += 1
    else: return
    
    # 11. 週足60 (簡易的にMA5*5で計算)
    ma60_w = c.rolling(60*5).mean()
    if c.iloc[idx] > ma60_w.iloc[idx]: pass_counts[11] += 1
    else: return
    
    # 12. 天井維持
    if (c.iloc[idx] / ma24_m.iloc[idx] <= 1.2):
        pass_counts[12] += 1
        # 結果記録
        pct = ((c.iloc[idx] - c.iloc[prev_idx]) / c.iloc[prev_idx]) * 100
        mark = "◎" if pct >= 2.0 else "◯"
        report_qualified_details.append(f"{mark} | {code} | {int(c.iloc[idx])}円")

# --- メイン処理 ---
def main():
    start_r = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_r = int(sys.argv[2]) if len(sys.argv) > 2 else 10001
    
    for code in range(start_r, end_r):
        if 1300 <= code <= 1600: continue
        df = get_stock_data_from_web(str(code))
        if df is not None:
            analyze_stock(str(code), df)
        if code % 500 == 0: print(f"進捗: {code}番目処理中...")

    # メール送信
    msg = MIMEText(f"--- 検証完了 ---\n生存数: {pass_counts}\n{report_qualified_details}")
    msg['Subject'] = f"【検証レポート】{datetime.date.today()}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())

if __name__ == "__main__":
    main()
