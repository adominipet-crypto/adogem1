import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError

# --- 環境設定（GitHub Secretsから読み込む前提） ---
# 以下の環境変数はGitHub ActionsのSecretsで設定してください
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
GCP_SA_KEY = os.environ.get('GCP_SA_KEY')

# --- グローバル変数 ---
stage_survivors = {f"stage{i}": 0 for i in range(1, 13)}
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None
stage_results_report = {
    "trend_align": [], "upper_shadow": [], "ceiling_avoid": [],
    "new_high_pass": [], "weekly_ma_pass": [], "monthly_high_pass": [], "completed_pass": []
}

STAGE_LABELS = {
    "trend_align": "2.月足60", "upper_shadow": "8.上ヒゲ", "ceiling_avoid": "9.天井回避",
    "new_high_pass": "10.新高値", "weekly_ma_pass": "11.週足60", "monthly_high_pass": "12.天井維持", "completed_pass": "完全合格"
}

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
        target = datetime.datetime.now().date() - datetime.timedelta(days=1)
        GLOBAL_LATEST_DATE = target

def connect_spreadsheet(sheet_name="シート1"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(GCP_SA_KEY), scopes=scopes)
    return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)

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
    try:
        df = get_stock_data_fallback(symbol, force_check_date=False)
        if df is None: return None
        future_df = df[df.index.date > base_date]
        return future_df.iloc[0] if not future_df.empty else None
    except: return None

# --- シート1・シート2更新ロジック ---
def update_yesterday_results():
    global stage_results_report
    try:
        sheet = connect_spreadsheet("シート1")
        all_records = sheet.get_all_values()
        cell_list = []
        reverse_stage_map = {"7. 長トレンド": "trend_align", "8. 上ヒゲ": "upper_shadow", "9. 天井圏回避": "ceiling_avoid", "10. 新高値": "new_high_pass", "11. 週足60": "weekly_ma_pass", "12. 天井圏維持": "monthly_high_pass"}
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
            code, row_date_str = row[1], row[0]
            stage_name = row[2]
            try: 
                selected_price = int(row[4])
                sel_date = datetime.datetime.strptime(row_date_str, "%Y-%m-%d").date()
            except: continue
            next_data = get_next_trading_day_data(code, sel_date)
            if next_data is not None:
                next_close = int(next_data['Close'])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:+.2f}%")])
                s_key = reverse_stage_map.get(stage_name, "completed_pass")
                result_line = f"  {mark} ■ {code} | {selected_price}円 ({row_date_str[5:]}) → {next_close}円 ({pct:+.2f}%)"
                stage_results_report[s_key].append(result_line)
        if cell_list: sheet.update_cells(cell_list)
    except Exception as e: print(f"Sheet1判定エラー: {e}")

def update_sheet2_results():
    try:
        sheet2 = connect_spreadsheet("シート2")
        all_records = sheet2.get_all_values()
        cell_list = []
        for i in range(0, len(all_records), 4):
            if i >= len(all_records) or len(all_records[i]) < 3: continue
            data_date_str, code = all_records[i][0], all_records[i][1]
            if not code or data_date_str == "選定日付": continue
            try: 
                selected_price = int(all_records[i][2])
                sel_date = datetime.datetime.strptime(data_date_str, "%Y-%m-%d").date()
            except: continue
            df = get_stock_data_fallback(code, force_check_date=False)
            if df is None: continue
            future_df = df[df.index.date > sel_date]
            if future_df.empty: continue
            first_day = future_df.iloc[0]
            close_1 = int(first_day['Close'])
            pct_1 = ((close_1 - selected_price) / selected_price) * 100
            cell_list.extend([gspread.Cell(i+2, 5, close_1), gspread.Cell(i+3, 5, f"{pct_1:+.2f}%")])
            for day_idx in range(1, min(len(future_df), 15)):
                col = day_idx + 5
                close_curr = int(future_df.iloc[day_idx]['Close'])
                close_prev = int(future_df.iloc[day_idx-1]['Close'])
                pct_day = ((close_curr - close_prev) / close_prev) * 100
                cell_list.extend([gspread.Cell(i+2, col, close_curr), gspread.Cell(i+3, col, f"{pct_day:+.2f}%")])
        if cell_list: sheet2.update_cells(cell_list, value_input_option='RAW')
    except Exception as e: print(f"Sheet2更新エラー: {e}")

# --- スキャン・フィルタリング判定処理 ---
def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    stage_survivors["stage1"] += 1
    monthly_close = df['Close'].resample('ME').last()
    if len(monthly_close) < 60 or df['Close'].iloc[-1] < monthly_close.rolling(60).mean().iloc[-1]: return "SKIP"
    stage_survivors["stage2"] += 1
    if df['Volume'].iloc[-1] < 50000: return "SKIP"
    stage_survivors["stage3"] += 1
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df['MA60'] = df['Close'].rolling(60).mean()
    df['MA100'] = df['Close'].rolling(100).mean()
    df['MA300'] = df['Close'].rolling(300).mean()
    today, yest, yest2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
    if not (today['MA5'] < today['Close']) or today['Close'] <= today['Open'] or yest['Close'] >= yest['MA5'] or yest2['Close'] >= yest2['MA5']: return "SKIP"
    stage_survivors["stage4"] += 1
    if today['MA60'] <= yest['MA60']: return "SKIP"
    stage_survivors["stage5"] += 1
    # 6. 右肩上がり
    if today['MA60'] <= yest['MA60']: return "SKIP"
    stage_survivors["stage6"] += 1

    ppp_label = "★PPP " if (today['MA5'] > today['MA20'] > today['MA60'] > today['MA100'] > (today['MA300'] if pd.notna(today['MA300']) else 0)) else ("★PPP(Short) " if (today['MA5'] > today['MA20'] > today['MA60'] > today['MA100']) else "")
    data_date = df.index[-1].strftime("%Y-%m-%d")

    # 判定フロー（フィルタリング）
    if today['MA100'] <= yest['MA100']: 
        sheet1_final_log[symbol] = {"price": int(
