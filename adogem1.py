import warnings
warnings.simplefilter('ignore', FutureWarning)
import pandas as pd
import smtplib, os, sys, datetime, gspread, json, requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.service_account import Credentials

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
JQ_API_KEY = os.environ.get('JQ_REFRESH_TOKEN')

def fetch_all_stock_data_from_jquants():
    # ... (前回の取得ロジックとほぼ同じですが、失敗時にFalseではなく空の辞書を返すように変更)
    data_cache = {}
    last_date = None
    
    headers = {"x-api-key": JQ_API_KEY}
    # 契約期間内の最新日である 2026-04-13 を固定で指定して取得を試みる
    target_date = "2026-04-13" 
    url = f"https://api.jquants.com/v2/equities/bars/daily?date={target_date}"
    
    res = requests.get(url, headers=headers, timeout=30)
    if res.status_code == 200:
        data = res.json().get("data", [])
        for item in data:
            code = item.get("Code", "")
            if code:
                data_cache[code[:4]] = item
        return data_cache, datetime.date(2026, 4, 13)
    else:
        print(f"DEBUG: 過去データ取得も失敗しました: {res.text}")
        return {}, None

def run_logic():
    ALL_STOCK_DATA_CACHE, latest_date = fetch_all_stock_data_from_jquants()
    
    if not ALL_STOCK_DATA_CACHE:
        print("DEBUG: データの取得に失敗したため、スキャン処理をスキップします。")
        return

    # 以下、取得できたキャッシュデータを使用して既存のシート判定処理を実行
    # ... (run_logic内のスプレッドシート処理部分)
    print("DEBUG: 処理を完了しました。")

if __name__ == "__main__":
    run_logic()
