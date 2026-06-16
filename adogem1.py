import os, sys, time, datetime, gspread, json, requests, smtplib
import pandas as pd
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# --- グローバル変数 ---
pass_counts = {i: 0 for i in range(1, 13)}
report_qualified_details = []

# --- データ取得 ---
def get_stock_data_from_web(symbol):
    time.sleep(0.3)  # アクセス制限・負荷対策のスリープ
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
    except:
        return None

# --- 判定ロジック ---
def analyze_stock(code, df):
    global pass_counts, report_qualified_details
    
    idx = len(df) - 2 # 翌日判定のため、最新より1つ前を使用
    if idx < 100: return
    prev_idx = idx - 1
    
    c = df['Close']; o = df['Open']; h = df['High']; v = df['Volume']
    ma5 = c.rolling(5).mean(); ma60 = c.rolling(60).mean(); ma100 = c.rolling(100).mean()
    ma24_m = c.rolling(24*20).mean() 
    ma60_w = c.rolling(60*5).mean()

    # --- 12ステージ判定 ---
    pass_counts[1] += 1
    if c.iloc[idx] > ma60.iloc[idx]: pass_counts[2] += 1
    else: return
    if v.iloc[idx] >= 50000: pass_counts[3] += 1
    else: return
    if c.iloc[idx] > ma5.iloc[idx]: pass_counts[4] += 1
    else: return
    if c.iloc[prev_idx] < ma5.iloc[prev_idx]: pass_counts[5] += 1
    else: return
    if ma60.iloc[idx] > ma60.iloc[prev_idx]: pass_counts[6] += 1
    else: return
    if ma100.iloc[idx] > ma100.iloc[prev_idx]: pass_counts[7] += 1
    else: return
    upper = h.iloc[idx] - max(o.iloc[idx], c.iloc[idx]); body = abs(c.iloc[idx] - o.iloc[idx])
    if body == 0 or (upper <= (body * 1.5)): pass_counts[8] += 1
    else: return
    if abs(c.iloc[idx] - ma100.iloc[idx]) / ma100.iloc[idx] >= 0.03: pass_counts[9] += 1
    else: return
    if ma5.iloc[idx] >= ma5.rolling(20).max().iloc[idx]: pass_counts[10] += 1
    else: return
    if c.iloc[idx] > ma60_w.iloc[idx]: pass_counts[11] += 1
    else: return
    if (c.iloc[idx] / ma24_m.iloc[idx] <= 1.2):
        pass_counts[12] += 1
        # --- 判定結果リスト作成 ---
        curr_c = c.iloc[idx]; next_c = c.iloc[idx+1]
        pct = ((next_c - curr_c) / curr_c) * 100
        mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct >= -0.1 else "✕"
        date_str = df.index[idx].strftime("%m-%d")
        report_qualified_details.append(f"{mark} | {code} | {int(curr_c)}円 ({date_str}) → 1営業日 | {int(next_c)}円 ({pct:+.2f}%)")

# --- メール送信 ---
def send_email(report_text):
    msg = MIMEText(report_text, 'plain', 'utf-8')
    msg['Subject'] = f"【検証レポート】{datetime.date.today()}"
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())

# --- メメイン処理 ---
def main():
    start_r = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_r = int(sys.argv[2]) if len(sys.argv) > 2 else 10001
    
    print(f"処理開始: {start_r}〜{end_r}")
    
    for code in range(start_r, end_r):
        # データの有無に関わらず、確実に500件ごとにログを残す構造に変更
        if code % 500 == 0:
            print(f"【稼働確認】現在 {code} 番目を検証中...")
            
        if 1300 <= code <= 1600: continue # ETF/REIT除外
        
        df = get_stock_data_from_web(str(code))
        if df is not None: 
            analyze_stock(str(code), df)

    # --- レポート生成 ---
    report = f"--- {datetime.date.today()} 検証結果 ---\n\n【各ステージ生存数】\n"
    stages = ["取得", "月足60", "出来高", "下半身", "溜め", "右肩", "長期T", "上ヒゲ", "天井回避", "新高値", "週足60", "天井維持"]
    for i in range(1, 13):
        report += f"{i}.{stages[i-1]}: {pass_counts.get(i, 0)}件\n"
    
    report += "\n【確定の判定結果】\n" + ("\n".join(report_qualified_details) if report_qualified_details else "該当銘柄なし")
    
    # 長い固定テキストは複数行クォートで安全に結合（SyntaxError対策）
    condition_text = """

--------------------------------------------------
【条件一覧】
1. 全データ取得成功
2. 月足MA60クリア
3. 出来高5万株クリア
4. 下半身クリア
5. 溜めMA5クリア
6. 右肩上がり
7. 長期トレンド
8. 上ヒゲクリア
9. 天井圏MA100回避
10. 新高値MA5更新
11. 週足MA60クリア
12. 天井圏維持

【判定結果マーク基準】翌日終値
 ◎ ： +2.0%以上
 ◯ ： +0.1%〜+2.0%
 ▲ ： -0.1%〜+0.1%
 ✕ ： -0.1%未満"""
 
    report += condition_text
    
    send_email(report)
    print("全処理およびメール送信が正常に完了しました。")

if __name__ == "__main__":
    main()
