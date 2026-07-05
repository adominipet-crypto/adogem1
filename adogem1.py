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
JQ_REFRESH_TOKEN = os.environ.get('JQ_REFRESH_TOKEN') # J-Quants用リフレッシュトークン

# --- グローバル変数 ---
# 1〜9の9ステージ構成
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  
ALL_STOCK_DATA_CACHE = {} # J-Quantsから一括取得した当日データを格納する辞書

# ステージ6〜9および完全合格の答え合わせ用レポート構造
stage_results_report = {
    "stage6": [],
    "stage7": [],
    "stage8": [],
    "stage9": [],
    "completed_pass": []
}

STAGE_LABELS = {
    "stage6": "6.溜め",
    "stage7": "7.右肩上がり",
    "stage8": "8.長期トレンド",
    "stage9": "9.当日陽線",
    "completed_pass": "完全合格"
}

# 6〜9の自動集計用カウンター
stage_stats_counter = {
    6: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    7: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    8: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    9: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}
}

# --- J-Quants API データ一括取得関数 ---
def fetch_all_stock_data_from_jquants():
    global GLOBAL_LATEST_DATE, ALL_STOCK_DATA_CACHE
    if not JQ_REFRESH_TOKEN:
        print("エラー: JQ_REFRESH_TOKEN が GitHub Secrets に設定されていません。")
        return False
        
    try:
        print("J-Quants API から認証IDを取得中...")
        auth_url = f"https://api.jquants.com/v1/auth/idtoken?refreshToken={JQ_REFRESH_TOKEN}"
        res = requests.post(auth_url, timeout=15)
        id_token = res.json().get("idToken")
        if not id_token:
            print("J-Quants 認証トークンの取得に失敗しました。")
            return False
            
        headers = {"Authorization": f"Bearer {id_token}"}
        
        # 【テスト用設定】日付を直近の金曜日に固定
        today_str = "2026-07-03"
        print(f"【テスト実行】J-Quants から金曜日の株価一括データ({today_str})を取得中...")
        
        prices_url = f"https://api.jquants.com/v1/prices/daily_quotes?date={today_str}"
        res = requests.get(prices_url, headers=headers, timeout=30)
        
        if res.status_code != 200 or "daily_quotes" not in res.json() or not res.json()["daily_quotes"]:
            print(f"指定日({today_str})のデータが取得できないため、直近のデータを探索します。")
            prices_url = "https://api.jquants.com/v1/prices/daily_quotes"
            res = requests.get(prices_url, headers=headers, timeout=30)
            
        data = res.json().get("daily_quotes", [])
        if not data:
            print("株価データの取得に失敗しました。")
            return False
            
        # データの最新営業日を確定
        latest_date_str = data[0]["Date"]
        GLOBAL_LATEST_DATE = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d").date()
        print(f"データ対象日を確定しました: {GLOBAL_LATEST_DATE}")
        
        # 4桁コードをキーにしてキャッシュへ格納
        for item in data:
            code = item["Code"][:4]
            ALL_STOCK_DATA_CACHE[code] = item
            
        print(f"全 {len(ALL_STOCK_DATA_CACHE)} 銘柄の当日株価データをキャッシュしました。")
        return True
    except Exception as e:
        print(f"J-Quants データ一括取得エラー: {e}")
        return False

def fetch_global_latest_date():
    pass

def get_previous_trading_day(base_date):
    target = base_date - datetime.timedelta(days=1)
    while target.weekday() >= 5:
        target -= datetime.timedelta(days=1)
    return target

def connect_spreadsheet(sheet_name=None):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    gcp_key = os.environ.get('GCP_SA_KEY')
    if not gcp_key:
        raise ValueError("GCP_SA_KEY が設定されていません。")
    
    if gcp_key.startswith('{'):
        creds = Credentials.from_service_account_info(json.loads(gcp_key), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(gcp_key, scopes=scopes)
        
    spreadsheet = gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ")
    
    if sheet_name is None:
        target_date = GLOBAL_LATEST_DATE if GLOBAL_LATEST_DATE else datetime.date.today()
        sheet_name = f"{target_date.month}月"
        
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        print(f"シート「{sheet_name}」が見つからないため、新規作成します。")
        new_sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        headers = ["選定日付", "コード", "通過条件ステージ", "PPP", "選定時株価", "翌日終値", "判定", "比率(%)"]
        new_sheet.append_row(headers, value_input_option='RAW')
        return new_sheet

def get_stock_data_fallback(symbol, force_check_date=True):
    try:
        item = ALL_STOCK_DATA_CACHE.get(symbol)
        if not item or item.get("Close") is None: return None
        
        df = pd.DataFrame({
            "Open": [item["Open"]], 
            "High": [item["High"]], 
            "Low": [item["Low"]], 
            "Close": [item["Close"]], 
            "Volume": [item["Volume"]]
        }, index=[GLOBAL_LATEST_DATE])
        
        return df
    except: return None

def get_next_trading_day_data(symbol, base_date):
    try:
        item = ALL_STOCK_DATA_CACHE.get(symbol)
        if item and item.get("Close") is None: return None
        return {"Close": item["Close"]}
    except: return None

# --- 日経平均の判定行を自動作成する関数 ---
def get_nikkei_evaluation_line():
    try:
        url = "https://kabutan.jp/stock/kabuka?code=0000"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return "【日経平均の判定】\n  データ取得エラー(株探)"
        
        pattern = r'
