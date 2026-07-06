import warnings
warnings.simplefilter('ignore', FutureWarning)
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, sys, datetime, gspread, json, requests
from google.oauth2.service_account import Credentials

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
JQ_REFRESH_TOKEN = os.environ.get('JQ_REFRESH_TOKEN')

ALL_STOCK_DATA_CACHE = {}
GLOBAL_LATEST_DATE = None

def fetch_all_stock_data_from_jquants():
    global GLOBAL_LATEST_DATE, ALL_STOCK_DATA_CACHE
    try:
        res = requests.post(f"https://api.jquants.com/v1/auth/idtoken?refreshToken={JQ_REFRESH_TOKEN}", timeout=15)
        id_token = res.json().get("idToken")
        headers = {"Authorization": f"Bearer {id_token}"}
        res = requests.get("https://api.jquants.com/v1/prices/daily_quotes", headers=headers, timeout=30)
        data = res.json().get("daily_quotes", [])
        if not data: return False
        GLOBAL_LATEST_DATE = datetime.datetime.strptime(data[0]["Date"], "%Y-%m-%d").date()
        for item in data: ALL_STOCK_DATA_CACHE[item["Code"][:4]] = item
        print(f"DEBUG: {GLOBAL_LATEST_DATE} のデータを {len(ALL_STOCK_DATA_CACHE)} 件取得しました。")
        return True
    except Exception as e:
        print(f"DEBUG: データ取得失敗 {e}")
        return False

def run_logic():
    # 1. スプレッドシート接続
    try:
        creds = Credentials.from_service_account_info(json.loads(os.environ.get('GCP_SA_KEY')), 
                      scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        sheet = gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(f"{GLOBAL_LATEST_DATE.month}月")
        records = sheet.get_all_values()
        print(f"DEBUG: シートから {len(records)} 行読み込みました。")
    except Exception as e:
        print(f"DEBUG: シート接続エラー: {e}")
        return

    # 2. 答え合わせ処理
    cell_list = []
    for i, row in enumerate(records):
        if i > 0 and len(row) > 6 and row[6].strip() == "判定待ち":
            code = row[1]
            if code in ALL_STOCK_DATA_CACHE:
                next_close = float(ALL_STOCK_DATA_CACHE[code]["Close"])
                price = float(row[4])
                pct = ((next_close - price) / price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:.2f}%")])
                print(f"DEBUG: 銘柄 {code} 判定済み: {next_close}円, {mark}")
    
    if cell_list: 
        sheet.update_cells(cell_list)
        print("DEBUG: 判定結果をシートに書き込みました。")
    else:
        print("DEBUG: 判定対象の銘柄（判定待ち）が見つかりませんでした。")

    # 3. 新規銘柄追記（簡易スキャン）
    new_rows = []
    start, end = 1300, 10001
    for s in [str(i) for i in range(start, end)]:
        if 1300 <= int(s) <= 1600: continue
        item = ALL_STOCK_DATA_CACHE.get(s)
        if item and item.get("Volume", 0) >= 50000 and item["Open"] < item["Close"]:
            new_rows.append([GLOBAL_LATEST_DATE.strftime("%Y-%m-%d"), s, "9.当日陽線", "通常", item["Close"], "", "判定待ち", ""])
    
    if new_rows: 
        sheet.append_rows(new_rows)
        print(f"DEBUG: 新規銘柄 {len(new_rows)} 件を追記しました。")
    else:
        print("DEBUG: 新規条件合致銘柄が見つかりませんでした。")

    # 4. メール送信
    try:
        print("DEBUG: メール送信開始...")
        msg = MIMEMultipart()
        msg['Subject'] = "adoGEM スキャン結果通知"
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        body = f"本日のスキャンが完了しました。\n判定対象銘柄数: {len(cell_list)/3}件\n新規追加銘柄数: {len(new_rows)}件"
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("DEBUG: メール送信成功")
    except Exception as e:
        print(f"DEBUG: メール送信失敗: {e}")

if __name__ == "__main__": 
    if fetch_all_stock_data_from_jquants(): 
        run_logic()
    else:
        print("DEBUG: データ取得失敗のため処理中断")
