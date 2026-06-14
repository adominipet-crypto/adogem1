import sys
import traceback
import os
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import yfinance as yf
# ... (その他必要なimportがある場合はここに追加してください) ...

# 1. 起動直後のデバッグログ
print(f"★[DEBUG] 起動しました。カレントディレクトリ: {os.getcwd()}")
print(f"★[DEBUG] ファイル一覧: {os.listdir('.')}")

# 2. 致命的エラーをキャッチする設定
def exception_handler(type, value, tb):
    print("★[FATAL ERROR] 致命的なエラーが発生しました！")
    traceback.print_exception(type, value, tb)
    sys.exit(1)

sys.excepthook = exception_handler

# --- ここに既存の関数定義 (fetch_global_latest_date, analyze_stockなど) を全て含めてください ---
# 例:
# def fetch_global_latest_date(): ...
# def update_yesterday_results(): ...
# def update_sheet2_results(): ...
# def analyze_stock(s): ...
# def record_to_spreadsheet(): ...

def main():
    print("★main()関数の中に入りました！")
    
    # 範囲を 4000〜4500 に固定
    start_r = 4000
    end_r = 4501
    
    try:
        print("★事前処理開始...")
        fetch_global_latest_date()
        update_yesterday_results()
        update_sheet2_results()
        
        # 銘柄スキャンループ
        print(f"★実験開始: {start_r}番から{end_r-1}番までスキャンします")
        for s in [str(i) for i in range(start_r, end_r)]: 
            print(f"★処理中: {s}") # 銘柄ごとの進行状況を表示
            analyze_stock(s)
            
        print("★スキャンループ完了。スプレッドシートへの記録を開始します")
        record_to_spreadsheet()
        print("★記録完了。メール送信処理へ...")
        
    except Exception as e:
        print(f"★main()内でエラー発生: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("★スクリプト起動しました")
    main()
    print("★スクリプト正常終了")
