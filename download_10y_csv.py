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

# 即時出力設定
sys.stdout.reconfigure(line_buffering=True)

# 環境変数の読み込み
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

def main():
    print("--- プログラム開始 ---")
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, DRIVE_FOLDER_ID]):
        print("エラー: 環境変数が不足しています")
        print(f"ID:{bool(CLIENT_ID)}, SECRET:{bool(CLIENT_SECRET)}, TOKEN:{bool(REFRESH_TOKEN)}, FOLDER:{bool(DRIVE_FOLDER_ID)}")
        return

    print(f"保存先フォルダID: {DRIVE_FOLDER_ID}")
    try:
        drive_service = authenticate_drive()
        print("認証成功")
        # 動作テスト：最初の1つだけ実行して確認
        print("銘柄コード 1300 を処理中...")
        # (ここにfetchやuploadの呼び出しを入れる)
        print("--- 完了 ---")
    except Exception as e:
        print(f"致命的なエラーが発生しました: {e}")

if __name__ == "__main__":
    main()
