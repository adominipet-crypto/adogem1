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

# --- スプレッドシート関連（既存の関数をここに移植してください） ---
def record_to_spreadsheet():
    # ※ここにあなたの既存のシート1更新コードを記述してください
    pass

def update_sheet2_results():
    # ※ここにあなたの既存のシート2更新コードを記述してください
    pass

# --- データ取得・加工 ---
def get_stock_data_from_web(symbol):
    time.sleep(0.3) # API負荷軽減
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=5y&interval=1d"
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
    except Exception as e:
        return None

# --- 判定ロジック ---
def analyze_stock(code, df):
    global pass_counts, report_qualified_details
    target_dt = pd.to_datetime(datetime.datetime.now().strftime("%Y-%m-%d")).normalize()
    
    # 直近の日付が含まれるか確認
    if target_dt not in df.index:
        # 日付がない場合、最新の日付を使用するなどの調整が必要かもしれません
        return

    idx = df.index.get_loc(target_dt)
    if idx < 60: return # データ不足
    
    # 指標計算
    c = df['Close']
    ma5 = c.rolling(5).mean()
    ma60 = c.rolling(60).mean()
    ma100 = c.rolling(100).mean()
    
    # 判定 (※以前の条件ロジックをここに移植)
    # 例：
    if c.iloc[idx] > ma60.iloc[idx]: pass_counts[2] += 1
    # ... (他11ステージの条件を記述) ...

    # 合格した場合
    # report_qualified_details.append(f"...")

# --- メール送信 ---
def send_email(report_text):
    try:
        msg = MIMEText(report_text)
        msg['Subject'] = f"【検証レポート】{datetime.date.today()}"
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
        print("メール送信完了")
    except Exception as e:
        print(f"メール送信エラー: {e}")

# --- メイン処理 ---
def main():
    start_r = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_r = int(sys.argv[2]) if len(sys.argv) > 2 else 10001
    
    print(f"処理開始: {start_r}〜{end_r}")
    
    for code in range(start_r, end_r):
        if 1300 <= code <= 1600: continue # ETF/REIT除外
        
        df = get_stock_data_from_web(str(code))
        if df is None: continue
        
        analyze_stock(str(code), df)
        
        if code % 100 == 0:
            print(f"進捗: {code}番目処理中...")

    # --- レポート生成 ---
    report = f"--- {datetime.date.today()} 検証結果 ---\n\n【生存数】\n"
    for i in range(1, 13):
        report += f"{i}:{pass_counts[i]}件\n"
    report += "\n【結果】\n" + ("\n".join(report_qualified_details) if report_qualified_details else "該当なし")
    
    send_email(report)
    
    # スプレッドシート更新
    # record_to_spreadsheet()
    # update_sheet2_results()

if __name__ == "__main__":
    main()
