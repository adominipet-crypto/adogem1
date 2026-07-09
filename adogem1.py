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

# --- グローバル変数 ---
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  

stage_results_report = {
    "stage6": [], "stage7": [], "stage8": [], "stage9": [], "completed_pass": []
}
STAGE_LABELS = {
    "stage6": "6.溜め", "stage7": "7.右肩上がり", "stage8": "8.長期トレンド", 
    "stage9": "9.当日陽線", "completed_pass": "完全合格"
}
stage_stats_counter = {6: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}, 7: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}, 8: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}, 9: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}}

# --- 共通関数 ---
def fetch_global_latest_date():
    global GLOBAL_LATEST_DATE
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/^N225?range=1mo&interval=1d&nocache={int(time.time())}"
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        timestamps = res.json().get("chart", {}).get("result", [])[0].get("timestamp", [])
        GLOBAL_LATEST_DATE = datetime.datetime.fromtimestamp(timestamps[-1]).date()
    except:
        now = datetime.datetime.now()
        target = now.date() - datetime.timedelta(days=1)
        while target.weekday() >= 5: target -= datetime.timedelta(days=1)
        GLOBAL_LATEST_DATE = target

def get_previous_trading_day(base_date):
    target = base_date - datetime.timedelta(days=1)
    while target.weekday() >= 5: target -= datetime.timedelta(days=1)
    return target

def connect_spreadsheet(sheet_name=None):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    gcp_key = os.environ.get('GCP_SA_KEY')
    if not gcp_key: raise ValueError("GCP_SA_KEY が設定されていません。")
    
    creds = Credentials.from_service_account_info(json.loads(gcp_key), scopes=scopes) if gcp_key.startswith('{') else Credentials.from_service_account_file(gcp_key, scopes=scopes)
    
    spreadsheet = gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ")
    sheet_name = sheet_name or f"{GLOBAL_LATEST_DATE.month}月"
    try: return spreadsheet.worksheet(sheet_name)
    except:
        new_sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        new_sheet.append_row(["選定日付", "コード", "通過条件ステージ", "PPP", "選定時株価", "翌日終値", "判定", "比率(%)"], value_input_option='RAW')
        return new_sheet

def get_stock_data_fallback(symbol, force_check_date=True):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=5y&interval=1d&nocache={int(time.time())}" 
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if res.status_code != 200: return None
        result = res.json().get("chart", {}).get("result", [])
        if not result: return None
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        df = pd.DataFrame({"Close": quotes.get("close", []), "Open": quotes.get("open", []), "High": quotes.get("high", []), "Low": quotes.get("low", []), "Volume": quotes.get("volume", [])}, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        df = df.dropna().sort_index()
        if force_check_date and GLOBAL_LATEST_DATE and df.index[-1].date() != GLOBAL_LATEST_DATE: return None
        return df
    except: return None

def get_next_trading_day_data(symbol, base_date):
    df = get_stock_data_fallback(symbol, force_check_date=False)
    return df[df.index.date > base_date].iloc[0] if df is not None and not df[df.index.date > base_date].empty else None

def get_nikkei_evaluation_line():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/^N225?range=1mo&interval=1d"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        data = res.json()["chart"]["result"][0]
        close = data["indicators"]["quote"][0]["close"]
        ts = data["timestamp"]
        df = pd.DataFrame({"Close": close}, index=[datetime.datetime.fromtimestamp(t).date() for t in ts]).dropna()
        curr_date, prev_date = GLOBAL_LATEST_DATE, get_previous_trading_day(GLOBAL_LATEST_DATE)
        curr_val, prev_val = df.loc[curr_date, "Close"], df.loc[prev_date, "Close"]
        pct = ((curr_val - prev_val) / prev_val) * 100
        mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
        return f"【日経平均の判定】\n  {mark} | NIKKEI225 | {int(prev_val)}円 ({prev_date.strftime('%m-%d')}) → {int(curr_val)}円 ({curr_date.strftime('%m-%d')}) ({pct:+.2f}%)"
    except Exception as e: return f"【日経平均の判定】\n  自動取得エラー: {e}"

def update_yesterday_results():
    global stage_results_report, stage_stats_counter
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        cell_list = []
        target_match_date = get_previous_trading_day(GLOBAL_LATEST_DATE) if GLOBAL_LATEST_DATE else None
        
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
            code, sel_date = row[1], datetime.datetime.strptime(row[0], "%Y-%m-%d").date()
            if target_match_date and sel_date != target_match_date: continue
            
            next_data = get_next_trading_day_data(code, sel_date)
            if next_data is not None:
                next_close, selected_price = int(next_data['Close']), int(row[4])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:+.2f}%")])
                s_key = {"6. 溜め": "stage6", "7. 右肩上がり": "stage7", "8. 長期トレンド": "stage8", "9. 当日陽線": "stage9"}.get(row[2], "completed_pass")
                ppp_prefix = f"{row[3].strip()} " if row[3].strip() in ["★PPP", "★PPP(Short)"] else ""
                stage_results_report[s_key].append(f"  {ppp_prefix}{mark} ■ {code} | {selected_price}円 ({row[0][5:]}) → {next_close}円 ({pct:+.2f}%)")
        if cell_list: sheet.update_cells(cell_list)
    except Exception as e: print(f"判定エラー: {e}")

def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    idx, prev_idx = len(df) - 1, len(df) - 2
    if idx < 100: return "SKIP"
    c, o, v = df['Close'], df['Open'], df['Volume']
    ma5, ma20, ma60, ma100, ma300 = c.rolling(5).mean(), c.rolling(20).mean(), c.rolling(60).mean(), c.rolling(100).mean(), c.rolling(300).mean()

    stage_survivors["stage1"] += 1
    if c.iloc[idx] <= ma60.iloc[idx] or v.iloc[idx] < 50000 or c.iloc[idx] <= ma5.iloc[idx]: return "SKIP"
    stage_survivors.update({"stage2": stage_survivors["stage2"]+1, "stage3": stage_survivors["stage3"]+1, "stage4": stage_survivors["stage4"]+1})
    
    if not any(c.iloc[i] > ma20.iloc[i] and c.iloc[i-1] <= ma20.iloc[i-1] for i in range(idx - 6, idx + 1) if i >= 1): return "SKIP"
    stage_survivors["stage5"] += 1
    
    ppp = "★PPP " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0)) else ("★PPP(Short) " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx]) else "")
    date_str = df.index[idx].strftime("%Y-%m-%d")
    
    for cond, stage, key in [(c.iloc[prev_idx] < ma5.iloc[prev_idx], "stage6", "stage6"), (ma60.iloc[idx] > ma60.iloc[prev_idx], "stage7", "stage7"), (ma100.iloc[idx] > ma100.iloc[prev_idx], "stage8", "stage8"), (o.iloc[idx] < c.iloc[idx], "stage9", "stage9")]:
        if not cond:
            sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": key, "ppp_label": ppp, "date": date_str}; return "SKIP"
        stage_survivors[stage] += 1
    
    sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "completed_pass", "ppp_label": ppp, "date": date_str}
    selected_stocks[symbol] =
