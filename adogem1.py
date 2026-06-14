import sys
import os
import traceback
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta

# --- グローバル変数 ---
target_date = "----"
total_count = 0
stage_counts = {i: 0 for i in range(1, 13)}
ppp_count = 0
short_count = 0
normal_count = 0
perfect_pass_list = []
yesterday_results = {}
gc, workbook, sheet1, sheet2 = None, None, None, None

# --- [修正箇所] 認証初期化 ---
def init_google_sheets():
    global gc, workbook, sheet1, sheet2
    try:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GCP_SA_KEY")
        if not sa_json: 
            print("★[ERROR] 認証情報が見つかりません")
            return False
            
        # ★ここを修正：scopes引数を削除しました
        if sa_json.strip().startswith('{'):
            creds_dict = json.loads(sa_json)
            creds = Credentials.from_service_account_info(creds_dict)
        else:
            creds = Credentials.from_service_account_file(sa_json)
            
        gc = gspread.authorize(creds)
        workbook = gc.open("Stock_Analysis_Data") 
        sheet1 = workbook.get_sheet_by_id(0)
        sheet2 = workbook.worksheet("シート2")
        return True
    except Exception as e:
        print(f"★[ERROR] 初期化失敗: {e}")
        return False

# --- 以下、前回の機能ロジックを維持 ---
def fetch_global_latest_date():
    global target_date
    try:
        ticker = yf.Ticker("^N225")
        hist = ticker.history(period="2d")
        target_date = hist.index[-1].strftime('%Y-%m-%d') if not hist.empty else datetime.now().strftime('%Y-%m-%d')
    except:
        target_date = datetime.now().strftime('%Y-%m-%d')

def analyze_stock(s):
    global total_count, stage_counts, ppp_count, short_count, normal_count, perfect_pass_list
    ticker_symbol = f"{s}.T"
    total_count += 1
    
    try:
        # ※以前の解析ロジックをここに貼り付けてください
        # ※今回はエラーログ確認のため、必要に応じて最小限のダウンロードに留めてテストしてください
        df = yf.download(ticker_symbol, period="1y", progress=False)
        if df.empty: return
        
        # (判定ロジック...)
        stage_counts[1] += 1
    except Exception as e:
        print(f"★[ERROR] {ticker_symbol} スキャン中にエラー: {e}")

def perform_15day_analysis(data_rows):
    print("★[SYSTEM] 15日データ解析実行")

def record_to_spreadsheet():
    print("★[5/6] シート2へ記録中...")
    if sheet2 is None: return
    row_data = [target_date, total_count, stage_counts[1], stage_counts[2], stage_counts[3], stage_counts[4], stage_counts[5], stage_counts[6], stage_counts[7], stage_counts[8], stage_counts[9], stage_counts[10], stage_counts[11], stage_counts[12], ppp_count, short_count, normal_count, str(perfect_pass_list)]
    sheet2.append_row(row_data)
    
    all_data = sheet2.get_all_values()
    if len(all_data) > 15:
        perform_15day_analysis(all_data[-15:])

def main():
    print("★[SYSTEM] スキャン開始")
    if not init_google_sheets(): return
    
    fetch_global_latest_date()
    
    # ★テスト時は range(1000, 1100) など範囲を絞ることを強く推奨します
    for s in [str(i) for i in range(1000, 10000)]:
        analyze_stock(s)
            
    record_to_spreadsheet()
    print("★[SYSTEM] 処理完了")

if __name__ == "__main__":
    main()
