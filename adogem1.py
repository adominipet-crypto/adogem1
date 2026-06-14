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

# --- 初期化・接続系 ---
def init_google_sheets():
    global gc, workbook, sheet1, sheet2
    try:
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GCP_SA_KEY")
        if not sa_json: 
            print("★[ERROR] 認証情報が見つかりません")
            return False
        creds = Credentials.from_service_account_info(json.loads(sa_json)) if sa_json.strip().startswith('{') else Credentials.from_service_account_file(sa_json)
        gc = gspread.authorize(creds)
        workbook = gc.open("Stock_Analysis_Data") 
        sheet1 = workbook.get_sheet_by_id(0)
        sheet2 = workbook.worksheet("シート2")
        return True
    except Exception as e:
        print(f"★[ERROR] 初期化失敗: {e}")
        return False

def fetch_global_latest_date():
    global target_date
    print("★[1/6] fetch_global_latest_date を実行中...")
    try:
        ticker = yf.Ticker("^N225")
        hist = ticker.history(period="2d")
        target_date = hist.index[-1].strftime('%Y-%m-%d') if not hist.empty else datetime.now().strftime('%Y-%m-%d')
    except:
        target_date = datetime.now().strftime('%Y-%m-%d')

# --- 判定ロジック ---
def analyze_stock(s):
    global total_count, stage_counts, ppp_count, short_count, normal_count, perfect_pass_list
    ticker_symbol = f"{s}.T"
    total_count += 1
    
    # ログ出力（進行状況確認用）
    if int(s) % 100 == 0:
        print(f"★[DEBUG] {s}番台をスキャン中...")

    try:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365 * 7)
        
        # データ取得
        df_daily = yf.download(ticker_symbol, start=start_dt, end=end_dt, progress=False)
        
        if df_daily.empty:
            return
            
        stage_counts[1] += 1
        
        # 指標計算（以前のロジック）
        close_d = df_daily['Close'].squeeze()
        ma5_d = close_d.rolling(window=5).mean()
        ma60_d = close_d.rolling(window=60).mean()
        
        # 最新値の取得
        latest_idx = close_d.index[-1]
        c_val = close_d.loc[latest_idx]
        
        # 簡易判定例（すべてのステージ判定はここに記述）
        if c_val >= ma60_d.loc[latest_idx]:
            stage_counts[2] += 1
        
        # (※以前のステージ1-12判定ロジックをここに全て記述してください)

    except Exception as e:
        # ここがエラーをキャッチしてログに出すため、何が起きているか分かります
        print(f"★[ERROR] {ticker_symbol} 解析中に問題発生: {e}")

# --- 記録・判定ロジック ---
def perform_15day_analysis(data_rows):
    print("★[SYSTEM] 15日データ蓄積完了。最終判定ロジックを実行します...")
    # ここに独自の15日トレンド判定ロジックを記述
    pass

def record_to_spreadsheet():
    print("★[5/6] 解析結果をスプレッドシートに記録中...")
    if sheet2 is None: return
    
    # 1. 毎日のデータを追記
    row_data = [target_date, total_count, stage_counts[1], stage_counts[2], stage_counts[3], stage_counts[4], stage_counts[5], stage_counts[6], stage_counts[7], stage_counts[8], stage_counts[9], stage_counts[10], stage_counts[11], stage_counts[12], ppp_count, short_count, normal_count, str(perfect_pass_list)]
    sheet2.append_row(row_data)
    
    # 2. 15日判定
    try:
        all_data = sheet2.get_all_values()
        if len(all_data) > 15:
            last_15 = all_data[-15:]
            perform_15day_analysis(last_15)
    except Exception as e:
        print(f"★[ERROR] 15日判定でエラー: {e}")

# --- メイン ---
def main():
    print("★[SYSTEM] スキャン開始")
    if not init_google_sheets(): return
    
    fetch_global_latest_date()
    
    # スキャンループ
    # 9000件全てを短時間で処理するのはライブラリの制限上困難なため、エラーログを確認しながら進めてください
    for s in [str(i) for i in range(1000, 10000)]:
        analyze_stock(s)
            
    record_to_spreadsheet()
    print("★[SYSTEM] 処理完了")

if __name__ == "__main__":
    main()
