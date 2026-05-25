import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests
from google.oauth2.service_account import Credentials

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

stats = {
    "total_fetched": 0, "pass_volume": 0, "pass_kahanshin": 0, "pass_tame": 0,
    "pass_ma60_up": 0, "pass_trend_align": 0, "pass_upper_shadow": 0, "pass_new_high": 0, "pass_ceiling_avoid": 0,
    "★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0,
    "list_tame": [], "list_ma60_up": [], "list_trend_align": [], "list_upper_shadow": [], "list_new_high": [], "list_ceiling_avoid": []
}

def connect_spreadsheet():
    """Googleスプレッドシートへ安全に接続"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    
    client = gspread.authorize(creds)
    return client.open("adoGEM_検証ログ").worksheet("選定ログ")

def record_to_spreadsheet():
    """本日の選定結果（条件4以降）をシートに自動追記"""
    try:
        sheet = connect_spreadsheet()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        new_rows = []
        target_stages = {
            "4. 60日線右肩上がり": stats["list_ma60_up"], "新. 長期トレンド同期": stats["list_trend_align"],
            "新. 上ヒゲ選別": stats["list_upper_shadow"], "6. 天井圏回避(最終)": stats["list_ceiling_avoid"]
        }
        for stage_name, stock_list in target_stages.items():
            for stock in stock_list:
                parts = stock.split(" ■ ")
                if len(parts) < 2: continue
                code_price = parts[1].replace("円", "").split(" | ")
                new_rows.append([today_str, code_price[0].strip(), int(code_price[1].strip()), stage_name, "", "判定待ち"])
        if new_rows:
            sheet.append_rows(new_rows)
            print(f"【シート記録】{len(new_rows)} 件記録しました。")
    except Exception as e:
        print(f"シート記録エラー: {e}")

def get_stock_data_fallback(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=2y&interval=1d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return None
        result = res.json().get("chart", {}).get("result", [])
        if not result or result is None: return None
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        if not timestamps or not quotes.get("close", []): return None
        df = pd.DataFrame({
            "Open": quotes.get("open", []), "High": quotes.get("high", []),
            "Low": quotes.get("low", []), "Close": quotes.get("close", []), "Volume": quotes.get("volume", [])
        }, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        df.dropna(subset=["Close", "Volume"], inplace=True)
        return df.sort_index()
    except:
        return None

def update_yesterday_results():
    """過去の『判定待ち』データの答え合わせ（◎◯▲✕ ＆ 前日比％）を自動実行"""
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        if all_records and len(all_records[0]) < 7: sheet.update_cell(1, 7, "前日比(%)")
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 6 or row[5] != "判定待ち": continue
            code, selected_price = row[1], int(row[2])
            df = get_stock_data_fallback(code)
            if df is not None and len(df) >= 1:
                next_close = int(df['Close'].iloc[-1])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct > 0.1 else "▲" if pct >= -0.1 else "✕"
                sheet.update_cell(i + 1, 5, next_close)
                sheet.update_cell(i + 1, 6, mark)
                sheet.update_cell(i + 1, 7, f"{pct:+.2f}%")
                print(f"【答え合わせ】{code
