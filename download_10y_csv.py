import os
import sys
import time
import requests
import io
import pandas as pd
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# 出力を即時反映する設定（これがないとログが消えることがあります）
sys.stdout.reconfigure(line_buffering=True)

CLIENT_ID = os.environ.get('CLIENT_ID')
CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
REFRESH_TOKEN = os.environ.get('REFRESH_TOKEN')
DRIVE_FOLDER_ID = os.environ.get('DRIVE_FOLDER_ID')

def authenticate_drive():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token"
    )
    return build('drive', 'v3', credentials=creds)

# 動作確認のため、fetchとuploadを簡略化しました
def main():
    print("--- プログラム開始 ---")
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, DRIVE_FOLDER_ID]):
        print("エラー: 設定値が読み込めていません")
        return

    print(f"フォルダID: {DRIVE_FOLDER_ID}")
    try:
        service = authenticate_drive()
        print("認証成功。テストとして1301をダウンロードします...")
        
        # 1301のデータ取得テスト
        url = "https://query1.finance.yahoo.com/v8/finance/chart/1301.T?range=1mo&interval=1d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        print(f"HTTPステータス: {res.status_code}")
        
        if res.status_code == 200:
            print("データ取得成功！")
        else:
            print("データ取得失敗")
            
        print("--- 終了 ---")
    except Exception as e:
        print(f"致命的なエラー: {e}")

if __name__ == "__main__":
    main()
