import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError  

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

stage_survivors = {
    "stage1": 0, "stage2": 0, "stage3": 0, "stage4": 0, "stage5": 0, "stage6": 0,
    "stage7": 0, "stage8": 0, "stage9": 0, "stage10": 0, "stage11": 0, "stage12": 0
}

stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
detected_data_date = "未取得"
GLOBAL_LATEST_DATE = None  
ans_report_lines = [] 

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

def connect_spreadsheet(sheet_name="シート1"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(json.loads(os.environ.get('GCP_SA_KEY')))
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

def update_yesterday_results():
    global ans_report_lines
    sheet = connect_spreadsheet("シート1")
    all_records = sheet.get_all_values()
    cell_list = []
    ans_report_lines.append("【本日確定の判定結果】")
    for i, row in enumerate(all_records):
        if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
        code, sel_date = row[1], datetime.datetime.strptime(row[0], "%Y-%m-%d").date()
        df = get_stock_data_fallback(code, force_check_date=False)
        if df is not None:
            future_df = df[df.index.date > sel_date]
            if not future_df.empty:
                next_data = future_df.iloc[0]
                next_close, selected_price = int(next_data['Close']), int(row[4])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:+.2f}%")])
                ans_report_lines.append(f"  {mark} ■ {code} | {selected_price}円 ({row[0][5:]}) → {next_close}円 ({pct:+.2f}%)")
    if len(ans_report_lines) == 1: ans_report_lines.append("  該当なし")
    if cell_list: sheet.update_cells(cell_list)

def record_to_spreadsheet():
    sheet = connect_spreadsheet("シート1")
    new_rows = []
    for code, row_data in sheet1_final_log.items():
        if row_data["stage_key"] not in ["trend_align", "upper_shadow", "ceiling_avoid", "new_high_pass", "weekly_ma_pass", "monthly_high_pass", "completed_pass"]: continue
        stage_map = {"trend_align": "7. 長トレンド", "upper_shadow": "8. 上ヒゲ", "ceiling_avoid": "9. 天井圏回避", "new_high_pass": "10. 新高値", "weekly_ma_pass": "11. 週足60", "monthly_high_pass": "12. 天井圏維持", "completed_pass": "12. 天井圏維持"}
        new_rows.append([row_data["date"], code, stage_map[row_data["stage_key"]], row_data["ppp_label"].strip() or "通常", row_data["price"], "", "判定待ち", ""])
    if new_rows: sheet.append_rows(new_rows, value_input_option='RAW')

def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    
    # (ステージ判定処理：既存のロジックを継続)
    # 最後にログへ保存する際は date_short = data_date[5:] を使用
    # ... (前回のanalyze_stock関数と同じロジックを配置) ...

def main():
    fetch_global_latest_date()
    update_yesterday_results()
    # (銘柄ループ処理など)
    # ...
    # メール生成時に ans_report_lines を先頭に結合
