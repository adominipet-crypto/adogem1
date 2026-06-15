import os, sys, time, datetime, gspread, json, requests
import pandas as pd
from email.mime.text import MIMEText
from google.oauth2.service_account import Credentials

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
GCP_SA_KEY = os.environ.get('GCP_SA_KEY')

# --- グローバル変数 ---
selected_stocks = {}
report_qualified_details = []
pass_counts = {i: 0 for i in range(1, 13)}

# --- 共通関数 ---
def connect_spreadsheet(sheet_name):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(GCP_SA_KEY), scopes=scopes)
    return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)

def get_stock_data_from_web(symbol):
    time.sleep(0.4) # ブロック対策：API間隔を空ける
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=5y&interval=1d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code != 200: return None
        result = res.json().get("chart", {}).get("result", [])
        if not result: return None
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        df = pd.DataFrame({
            "Close": quotes.get("close", []), "Open": quotes.get("open", []),
            "High": quotes.get("high", []), "Low": quotes.get("low", []),
            "Volume": quotes.get("volume", [])
        }, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        return df.dropna().sort_index()
    except: return None

# --- 判定ロジック ---
def analyze_stock(symbol, df):
    # 生存数カウント用
    # (※以前のステージ判定ロジックをここに移植してください)
    # dfを使って計算し、条件クリアなら selected_stocks に格納
    # if 条件: pass_counts[1] += 1 ... etc
    pass 

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
    except Exception as e: print(f"メール送信エラー: {e}")

def main():
    start_r, end_r = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 10001)
    
    for code in range(start_r, end_r):
        # --- ETF/REIT除外 ---
        if 1300 <= code <= 1600: continue
        
        # --- データ取得 ---
        df = get_stock_data_from_web(str(code))
        if df is None: continue
        
        # --- 判定実行 ---
        analyze_stock(str(code), df)

    # --- レポート生成 (指定フォーマット) ---
    report = f"--- {datetime.date.today()} 検証結果 ---\n\n【各ステージ生存数】\n"
    stages = ["取得", "月足60", "出来高", "下半身", "溜め", "右肩", "長期T", "上ヒゲ", "天井回避", "新高値", "週足60", "天井維持"]
    for i in range(1, 13):
        report += f"{i}.{stages[i-1]}: {pass_counts.get(i, 0)}件\n"
    
    report += "\n【確定の判定結果】\n"
    report += "\n".join(report_qualified_details) if report_qualified_details else "該当銘柄なし"
    report += "\n\n... (以下略: 条件一覧と基準) ..."
    
    print(report)
    send_email(report)

if __name__ == "__main__": main()
