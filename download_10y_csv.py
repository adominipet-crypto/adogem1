import os
import time
import io
import pandas as pd
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 環境設定（GCP_SA_KEYを廃止し、OAuth用の3つに変更）
CLIENT_ID = os.environ.get('CLIENT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('REFRESH_TOKEN')
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')

def authenticate_drive():
    # OAuth認証情報を作成
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build('drive', 'v3', credentials=creds)

def fetch_10y_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=10y&interval=1d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if res.status_code != 200: return None
        # ... (中略：既存のfetch処理と同じでOKです)
        data = res.json().get("chart", {}).get("result", [])
        if not data: return None
        quotes = data[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = data[0].get("timestamp", [])
        df = pd.DataFrame(quotes, index=[datetime.fromtimestamp(ts).strftime('%Y-%m-%d') for ts in timestamps])
        df.index.name = "Date"
        return df.dropna()
    except: return None

# 以下、upload_csv_to_drive と main 関数...
# (main関数内の if not GCP_SA_KEY を if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN に変更してください)
