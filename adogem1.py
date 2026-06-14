import sys
import os
import traceback
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
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

# --- 15日判定ロジック ---
def perform_15day_analysis(data_rows):
    """直近15日分のデータから判定を行う関数"""
    total_success = 0
    total_trials = 0
    
    # データを解析（列のインデックスはシートの構成に合わせてください）
    # 例: C列(index 2)がステージ1, N列(index 13)がステージ12とする
    for row in data_rows:
        try:
            # ステージ12の生存数を判定基準の例として使用
            success = int(row[13]) 
            trials = int(row[1])
            total_success += success
            total_trials += trials
        except:
            continue
            
    if total_trials > 0:
        ratio = (total_success / total_trials) * 100
        print(f"★[15日分析] 成功率: {ratio:.2f}%")
        # ここに「比率に応じた判定」ロジックを追加可能
        if ratio > 5.0:
            print("★[判定] 良好なトレンドです")
        return ratio
    return 0

# --- 既存の処理 ---
def init_google_sheets():
    global gc, workbook, sheet1, sheet2
    try:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GCP_SA_KEY")
        if not sa_json: return False
        creds = Credentials.from_service_account_info(json.loads(sa_json)) if sa_json.strip().startswith('{') else Credentials.from_service_account_file(sa_json)
        gc = gspread.authorize(creds)
        workbook = gc.open("Stock_Analysis_Data") 
        sheet1 = workbook.get_sheet_by_id(0)
        sheet2 = workbook.worksheet("シート2")
        return True
    except: return False

def analyze_stock(s):
    global total_count, stage_counts, ppp_count, short_count, normal_count, perfect_pass_list
    ticker_symbol = f"{s}.T"
    total_count += 1
    try:
        df = yf.download(ticker_symbol, period="1y", progress=False)
        if df.empty or len(df) < 60: return
        
        stage_counts[1] += 1
        # (判定ロジックは以前のまま省略なしでここに記述してください)
        # ※以前のコードからanalyze_stockの中身をここにペーストしてください
        
    except: pass

def record_to_spreadsheet():
    print("★[5/6] 解析結果をスプレッドシートに記録中...")
    if sheet2 is None: return
    
    # 1. 毎日のデータを追記
    row_data = [target_date, total_count, stage_counts[1], stage_counts[2], stage_counts[3], stage_counts[4], stage_counts[5], stage_counts[6], stage_counts[7], stage_counts[8], stage_counts[9], stage_counts[10], stage_counts[11], stage_counts[12], ppp_count, short_count, normal_count, str(perfect_pass_list)]
    sheet2.append_row(row_data)
    
    # 2. 15日判定ロジック
    all_data = sheet2.get_all_values()
    # ヘッダーを除外して直近15日を取得
    data_only = all_data[1:] 
    if len(data_only) >= 15:
        last_15 = data_only[-15:]
        print("★[SYSTEM] 15日データ蓄積完了。最終判定ロジックを実行します...")
        perform_15day_analysis(last_15)

# --- main関数など他は以前のコードと同様 ---
def main():
    init_google_sheets()
    # ... 他の処理 ...
    record_to_spreadsheet()
    # ...

if __name__ == "__main__":
    main()
