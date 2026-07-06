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
JQ_API_KEY = os.environ.get('JQ_REFRESH_TOKEN')

ALL_STOCK_DATA_CACHE = {}
GLOBAL_LATEST_DATE = None

def fetch_all_stock_data_from_jquants():
    global GLOBAL_LATEST_DATE, ALL_STOCK_DATA_CACHE
    
    if not JQ_API_KEY:
        print("DEBUGエラー: GitHub Secretsに APIキー（JQ_REFRESH_TOKEN）が設定されていません。")
        return False
        
    try:
        headers = {"x-api-key": JQ_API_KEY}
        res = None
        
        # 【V2正式仕様】/v2/market/daily_prices に変更。まずはpremiumプランで試す
        print("DEBUG: J-Quants V2 (Premium) の株価データ取得を開始します...")
        res = requests.get("https://api.jquants.com/v2/market/daily_prices?plan=premium", headers=headers, timeout=30)
        
        # 403や404であれば、lightプラン用パラメータで再試行
        if res.status_code != 200:
            print(f"DEBUG: Premiumで取得不可（コード:{res.status_code}）。Lightプラン用で再試行します...")
            res = requests.get("https://api.jquants.com/v2/market/daily_prices?plan=light", headers=headers, timeout=30)
        
        print(f"DEBUG: 株価データ最終応答コード: {res.status_code}")
        if res.status_code != 200:
            print(f"DEBUGエラー: 株価データ取得に失敗しました。応答: {res.text}")
            return False
            
        # V2のデータキー名は daily_prices になっています
        data = res.json().get("daily_prices", [])
        if not data:
            print("DEBUGエラー: daily_prices の中身が空です。")
            return False
            
        GLOBAL_LATEST_DATE = datetime.datetime.strptime(data[0]["Date"], "%Y-%m-%d").date()
        for item in data: 
            code = item.get("Code", "")
            if code:
                ALL_STOCK_DATA_CACHE[code[:4]] = item
            
        print(f"DEBUG成功: V2から {GLOBAL_LATEST_DATE} のデータを {len(ALL_STOCK_DATA_CACHE)} 件取得しました。")
        return True
        
    except Exception as e:
        print(f"DEBUG致命的エラー: 例外が発生しました。内容: {str(e)}")
        return False

def run_logic():
    print("DEBUG: スプレッドシート処理を開始します...")
    try:
        creds = Credentials.from_service_account_info(json.loads(os.environ.get('GCP_SA_KEY')), 
                      scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
        sheet = gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(f"{GLOBAL_LATEST_DATE.month}月")
        records = sheet.get_all_values()
        print(f"DEBUG: シートから {len(records)} 行読み込みました。")
    except Exception as e:
        print(f"DEBUGエラー: シート接続に失敗しました: {e}")
        return

    # 1. 答え合わせ処理
    cell_list = []
    for i, row in enumerate(records):
        if i > 0 and len(row) > 6 and row[6].strip() == "判定待ち":
            code = row[1]
            if code in ALL_STOCK_DATA_CACHE:
                item = ALL_STOCK_DATA_CACHE[code]
                close_val = item.get("Close") or item.get("AdjustmentClose")
                if close_val is None: continue
                
                next_close = float(close_val)
                price = float(row[4])
                pct = ((next_close - price) / price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:.2f}%")])
    
    if cell_list: 
        sheet.update_cells(cell_list)
        print(f"DEBUG: {len(cell_list)//3} 件の判定結果をシートに書き込みました。")
    else:
        print("DEBUG: 判定対象の銘柄（判定待ち）が見つかりませんでした。")

    # 2. 新規銘柄追記
    new_rows = []
    start, end = 1300, 10001
    for s in [str(i) for i in range(start, end)]:
        if 1300 <= int(s) <= 1600: continue
        item = ALL_STOCK_DATA_CACHE.get(s)
        if item:
            open_val = item.get("Open") or item.get("AdjustmentOpen")
            close_val = item.get("Close") or item.get("AdjustmentClose")
            volume_val = item.get("Volume") or item.get("AdjustmentVolume", 0)
            
            if open_val and close_val and float(volume_val) >= 50000 and float(open_val) < float(close_val):
                new_rows.append([GLOBAL_LATEST_DATE.strftime("%Y-%m-%d"), s, "9.当日陽線", "通常", float(close_val), "", "判定待ち", ""])
    
    if new_rows: 
        sheet.append_rows(new_rows)
        print(f"DEBUG: 新規銘柄 {len(new_rows)} 件を追記しました。")
    else:
        print("DEBUG: 条件に合う新規銘柄がありませんでした。")

    # 3. メール送信
    try:
        msg = MIMEMultipart()
        msg['Subject'] = "adoGEM スキャン結果通知"
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        body = f"本日のスキャンが完了しました。\n判定対象銘柄数: {len(cell_list)//3}件\n新規追加銘柄数: {len(new_rows)}件"
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("DEBUG: メール送信に成功しました。")
    except Exception as e:
        print(f"DEBUGエラー: メール送信に失敗しました: {e}")

if __name__ == "__main__": 
    if fetch_all_stock_data_from_jquants(): 
        run_logic()
    else:
        print("DEBUG: データ取得失敗のため処理を終了します。")
