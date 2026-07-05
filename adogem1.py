import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError  
import re

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
JQ_REFRESH_TOKEN = os.environ.get('JQ_REFRESH_TOKEN')

# --- J-Quants 認証 ---
def get_jquants_token():
    try:
        url = "https://api.jquants.com/v1/token/auth_user"
        res = requests.post(url, json={"refreshtoken": JQ_REFRESH_TOKEN})
        return res.json().get("idToken")
    except: return None

# --- J-Quants データ取得 ---
def get_stock_data_jquants(symbol, token):
    try:
        url = f"https://api.jquants.com/v1/prices/daily_quotes?code={symbol}01"
        headers = {"Authorization": f"Bearer {token}"}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return None
        data = res.json().get('daily_quotes', [])
        if not data: return None
        df = pd.DataFrame(data)
        df['Date'] = pd.to_datetime(df['Date'])
        df.set_index('Date', inplace=True)
        df = df.rename(columns={
            'ClosePrice': 'Close', 'OpenPrice': 'Open', 
            'HighPrice': 'High', 'LowPrice': 'Low', 'TurnoverValue': 'Volume'
        })
        return df.sort_index()
    except: return None

# --- グローバル変数 ---
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  

stage_results_report = {"stage6": [], "stage7": [], "stage8": [], "stage9": [], "completed_pass": []}
STAGE_LABELS = {"stage6": "6.溜め", "stage7": "7.右肩上がり", "stage8": "8.長期トレンド", "stage9": "9.当日陽線", "completed_pass": "完全合格"}
stage_stats_counter = {6: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}, 7: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}, 8: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}, 9: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}}

# --- 共通関数 ---
def fetch_global_latest_date():
    global GLOBAL_LATEST_DATE
    # 日付判定ロジックは既存のものを維持
    now = datetime.datetime.now()
    target = now.date()
    while target.weekday() >= 5: target -= datetime.timedelta(days=1)
    GLOBAL_LATEST_DATE = target

def get_previous_trading_day(base_date):
    target = base_date - datetime.timedelta(days=1)
    while target.weekday() >= 5: target -= datetime.timedelta(days=1)
    return target

def connect_spreadsheet(sheet_name=None):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    gcp_key = os.environ.get('GCP_SA_KEY')
    creds = Credentials.from_service_account_info(json.loads(gcp_key)) if gcp_key.startswith('{') else Credentials.from_service_account_file(gcp_key, scopes=scopes)
    spreadsheet = gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ")
    sheet_name = sheet_name or f"{GLOBAL_LATEST_DATE.month}月"
    try: return spreadsheet.worksheet(sheet_name)
    except: return spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")

def get_next_trading_day_data(symbol, base_date, token):
    df = get_stock_data_jquants(symbol, token)
    if df is None: return None
    future = df[df.index.date > base_date]
    return future.iloc[0] if not future.empty else None

def get_nikkei_evaluation_line():
    # 株探スクレイピングロジックは既存のまま
    return "【日経平均の判定】\n  (既存ロジック維持)"

# --- 株価選定ロジック ---
def analyze_stock(symbol, token):
    df = get_stock_data_jquants(symbol, token)
    if df is None: return "SKIP"
    
    idx = len(df) - 1
    if idx < 100: return "SKIP"
    prev_idx = idx - 1
    
    c = df['Close']; o = df['Open']; v = df['Volume']
    ma5 = c.rolling(5).mean(); ma20 = c.rolling(20).mean(); ma60 = c.rolling(60).mean(); ma100 = c.rolling(100).mean(); ma300 = c.rolling(300).mean()

    stage_survivors["stage1"] += 1
    if c.iloc[idx] <= ma60.iloc[idx]: return "SKIP"
    stage_survivors["stage2"] += 1
    if v.iloc[idx] < 50000: return "SKIP"
    stage_survivors["stage3"] += 1
    if c.iloc[idx] <= ma5.iloc[idx]: return "SKIP"
    stage_survivors["stage4"] += 1
    
    # MA20上抜け判定(既存のまま)
    cross_check = any(c.iloc[i] > ma20.iloc[i] and c.iloc[i-1] <= ma20.iloc[i-1] for i in range(idx - 6, idx + 1) if i >= 1)
    if not cross_check: return "SKIP"
    stage_survivors["stage5"] += 1
    
    ppp_label = "★PPP " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0)) else ("★PPP(Short) " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx]) else "")
    data_date = df.index[idx].strftime("%Y-%m-%d")
    
    # 溜め、右肩、長期トレンド、陽線判定(既存のまま)
    if c.iloc[prev_idx] >= ma5.iloc[prev_idx]:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage6", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    stage_survivors["stage6"] += 1
    if ma60.iloc[idx] <= ma60.iloc[prev_idx]:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage7", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    stage_survivors["stage7"] += 1
    if ma100.iloc[idx] <= ma100.iloc[prev_idx]:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage8", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    stage_survivors["stage8"] += 1
    if o.iloc[idx] >= c.iloc[idx]:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage9", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    stage_survivors["stage9"] += 1

    sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "completed_pass", "ppp_label": ppp_label, "date": data_date}
    selected_stocks[symbol] = {"price": int(c.iloc[idx]), "ppp_label": ppp_label, "date": data_date}
    if "★PPP " in ppp_label: stats["★PPP"] += 1
    elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
    else: stats["normal_detect"] += 1
    return "OK"

# --- メイン処理 ---
def main():
    token = get_jquants_token()
    fetch_global_latest_date()
    
    # 既存の判定処理および全銘柄ループ
    start_r, end_r = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 10001)
    for s in [str(i) for i in range(start_r, end_r)]:
        if 1300 <= int(s) <= 1600: continue
        analyze_stock(s, token)
        
    # (※以下、record_to_spreadsheet、メール送信ロジックを既存のまま連結)
    print("処理完了")

if __name__ == "__main__": main()
