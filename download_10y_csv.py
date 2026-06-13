import os
import time
import json
import requests
import io
import pandas as pd
from datetime import datetime
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 環境設定
GCP_SA_KEY = os.environ.get('GCP_SA_KEY')
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')

def authenticate_drive():
    creds = Credentials.from_service_account_info(json.loads(GCP_SA_KEY), scopes=['https://www.googleapis.com/auth/drive'])
    return build('drive', 'v3', credentials=creds)

def fetch_10y_data(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=10y&interval=1d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if res.status_code != 200: return None
        data = res.json().get("chart", {}).get("result", [])
        if not data: return None
        quotes = data[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = data[0].get("timestamp", [])
        df = pd.DataFrame(quotes, index=[datetime.fromtimestamp(ts).strftime('%Y-%m-%d') for ts in timestamps])
        df.index.name = "Date"
        return df.dropna()
    except: return None

def upload_csv_to_drive(drive_service, df, symbol):
    # 【修正版】BytesIOを使用してバイナリデータとして変換
    csv_buffer = io.BytesIO(df.to_csv().encode('utf-8'))
    file_name = f"{symbol}.csv"
    media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv', resumable=False)
    
    # ファイル存在チェック
    query = f"name='{file_name}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
    results = drive_service.files().list(q=query, fields="files(id)").execute()
    items = results.get('files', [])
    
    if items:
        drive_service.files().update(fileId=items[0]['id'], media_body=media).execute()
        print(f"[{symbol}] 更新しました。")
    else:
        drive_service.files().create(
            body={'name': file_name, 'parents': [DRIVE_FOLDER_ID]}, 
            media_body=media
        ).execute()
        print(f"[{symbol}] 新規作成しました。")

def main():
    if not GCP_SA_KEY or not DRIVE_FOLDER_ID:
        print("エラー: 設定値が読み込めていません")
        return
    drive_service = authenticate_drive()
    for code in range(1300, 1311):
        df = fetch_10y_data(str(code))
        if df is not None: 
            upload_csv_to_drive(drive_service, df, str(code))
        else: 
            print(f"[{code}] データなし")
        time.sleep(1.5)

if __name__ == "__main__":
    try: main()
    except Exception as e: print(f"致命的なエラー: {e}")
