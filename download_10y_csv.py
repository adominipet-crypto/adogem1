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

# --- 環境設定 ---
# 既存のシークレットをそのまま使用します
GCP_SA_KEY = os.environ.get('GCP_SA_KEY')
DRIVE_FOLDER_ID = '1xdomdWgW1JdJZK2immYokfFl4LfTdIBk'
# --- Drive API 認証 ---
def authenticate_drive():
    scopes = ['https://www.googleapis.com/auth/drive']
    creds = Credentials.from_service_account_info(json.loads(GCP_SA_KEY), scopes=scopes)
    return build('drive', 'v3', credentials=creds)

# --- 10年分の株価データ取得 ---
def fetch_10y_data(symbol):
    try:
        # range=10y を指定して過去10年分を取得
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=10y&interval=1d"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code != 200:
            return None
            
        result = res.json().get("chart", {}).get("result", [])
        if not result:
            return None
            
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        
        # DataFrameの作成
        df = pd.DataFrame({
            "Open": quotes.get("open", []),
            "High": quotes.get("high", []),
            "Low": quotes.get("low", []),
            "Close": quotes.get("close", []),
            "Volume": quotes.get("volume", [])
        }, index=[datetime.fromtimestamp(ts).strftime('%Y-%m-%d') for ts in timestamps])
        
        df.index.name = "Date"
        return df.dropna()
    except Exception as e:
        print(f"[{symbol}] データ取得エラー: {e}")
        return None

# --- CSVをGoogleドライブへアップロード ---
def upload_csv_to_drive(drive_service, df, symbol):
    # DataFrameをメモリ上でCSV文字列に変換
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer)
    csv_buffer.seek(0)
    
    file_name = f"{symbol}.csv"
    file_metadata = {
        'name': file_name,
        'parents': [DRIVE_FOLDER_ID]
    }
    
    media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv', resumable=True)
    
    try:
        # 同名ファイルの存在確認（あれば上書き、なければ新規作成するための検索）
        query = f"name='{file_name}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        
        if items:
            # 既存のファイルを更新（上書き）
            file_id = items[0]['id']
            drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            print(f"[{symbol}] 既存のCSVを更新しました。")
        else:
            # 新規作成
            drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            print(f"[{symbol}] 新規CSVを作成しました。")
            
    except Exception as e:
        print(f"[{symbol}] ドライブ保存エラー: {e}")

# --- メイン処理 ---
def main():
    if not GCP_SA_KEY or not DRIVE_FOLDER_ID:
        print("エラー: GCP_SA_KEY または DRIVE_FOLDER_ID が設定されていません。")
        return
        
    drive_service = authenticate_drive()
    
    # 対象銘柄リスト（テストとして最初は少数で実行することを推奨します）
    # 例として 1300 〜 1310 でテスト
    start_code = 1300
    end_code = 1310 
    
    print(f"データ取得を開始します... ({start_code} 〜 {end_code})")
    
    for code in range(start_code, end_code + 1):
        symbol = str(code)
        df = fetch_10y_data(symbol)
        
        if df is not None and not df.empty:
            upload_csv_to_drive(drive_service, df, symbol)
        else:
            print(f"[{symbol}] データが存在しないか、スキップされました。")
            
        # Yahoo Financeへの負荷軽減のため、必ず待機時間を入れる（BAN対策）
        time.sleep(1.5) 
        
    print("全処理が完了しました！")

if __name__ == "__main__":
    main()
