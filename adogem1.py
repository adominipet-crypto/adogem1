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

# 1〜12の各ステージに「到達して生存している」銘柄数を保持する辞書
stage_survivors = {
    "stage1": 0, "stage2": 0, "stage3": 0, "stage4": 0, "stage5": 0, "stage6": 0,
    "stage7": 0, "stage8": 0, "stage9": 0, "stage10": 0, "stage11": 0, "stage12": 0
}

stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}

# 1銘柄につき確定した最終判定のみを保持する辞書
sheet1_final_log = {}
# ステージ12を完全クリアした最終規定合格銘柄のみを保持する辞書（シート2用）
selected_stocks = {}

def connect_spreadsheet(sheet_name="シート1"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    
    max_retries = 5
    backoff_factor = 5  
    
    for attempt in range(1, max_retries + 1):
        try:
            client = gspread.authorize(creds)
            return client.open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)
        except APIError as e:
            if e.response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries:
                sleep_time = attempt * backoff_factor
                print(f"【⚠️Google API制限検知 {e.response.status_code}】")
                print(f"  --> {sleep_time}秒待機して再試行します（試行 {attempt}/{max_retries}）")
                time.sleep(sleep_time)
            else:
                raise e  
        except Exception as e:
            if attempt < max_retries:
                time.sleep(attempt * backoff_factor)
            else:
                raise e

def send_error_email(error_message, start_range, end_range):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"⚠️【エラー発生】adoGEM スキャン停止 ({start_range}-{end_range})"
    
    body = f"プログラムの実行中にエラーが発生し、処理が中断されました。\n" \
           f"発生日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
           f"【エラー詳細・ログ】\n" \
           f"--------------------------------------------------\n" \
           f"{error_message}\n" \
           f"--------------------------------------------------"
    
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e:
        print(f"エラーメール送信失敗: {e}")

def get_stock_data_fallback(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=5y&interval=1d" 
        headers = {"User-Agent": "Mozilla/5.0"}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return None
        result = res.json().get("chart", {}).get("result", [])
        if not result: return None
        
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        
        df = pd.DataFrame({
            "Open": quotes.get("open", []), "High": quotes.get("high", []),
            "Low": quotes.get("low", []), "Close": quotes.get("close", []), "Volume": quotes.get("volume", [])
        }, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        
        df.dropna(subset=["Close", "Volume"], inplace=True)
        df = df[df['Volume'] > 0] 
        df = df.sort_index()
        
        if df.empty or len(df) < 100: return None
        
        last_data_date = df.index[-1].date()
        today = datetime.date.today()
        
        if last_data_date > today or (today - last_data_date).days > 7:
            return None
            
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        if last_row['Close'] == prev_row['Close'] and last_row['High'] == prev_row['High'] and last_row['Volume'] < 100:
            df = df.iloc[:-1]
            
        return df
    except:
        return None

def record_to_spreadsheet():
    try:
        sheet = connect_spreadsheet("シート1")
        new_rows = []
        
        for code, row_data in sheet1_final_log.items():
            stage_key = row_data["stage_key"]
            
            # シート1は 7. 長トレンド以上の「留まった」ログ（および完全合格）のみを書き出し対象にする
            if stage_key in ["fetched", "monthly_60ma", "volume", "kahanshin", "tame", "ma60_up"]:
                continue

            price = row_data["price"]
            ppp_status = row_data["ppp_label"].strip() if row_data["ppp_label"].strip() else "通常"
            data_date = row_data["date"]  
            
            stage_names = {
                "trend_align": "7. 長トレンド",
                "upper_shadow": "8. 上ヒゲクリア", 
                "ceiling_avoid": "9. 天井圏回避",
                "new_high_pass": "10. 新高値更新",
                "weekly_ma_pass": "11. 週足60クリア",
                "monthly_high_pass": "12. 天井圏維持",
                "completed_pass": "12. 天井圏維持"
            }
            stage_name = stage_names.get(stage_key, stage_key)
            new_rows.append([data_date, code, stage_name, ppp_status, price, "", "判定待ち", ""])
            
        if new_rows:
            new_rows.sort(key=lambda x: x[1])
            sheet.append_rows(new_rows, value_input_option='RAW')
            print(f"【シート1記録】確定ステージが7以上の個別ログを計 {len(new_rows)} 件追記しました。")
            time.sleep(3)
    except Exception as e:
        print(f"シート1記録エラー: {e}")
        raise e

def record_to_sheet2():
    if not selected_stocks:
        print("【シート2記録】本日ステージ12を完全クリアした銘柄がないため、書き込みをスキップします。")
        return

    try:
        sheet2 = connect_spreadsheet("シート2")
        row_height = 4 
        
        col1_values = sheet2.col_values(1)
        last_filled_row = len(col1_values)
        
        start_row = ((last_filled_row // row_height) * row_height) + 1
        if start_row <= last_filled_row:
            start_row += row_height

        cell_updates = []
        sorted_codes = sorted(selected_stocks.keys())
        
        for idx, code in enumerate(sorted_codes):
            r = start_row + (idx * row_height)
            data = selected_stocks[code]
            
            price = data["price"]
            ppp_status = data["ppp_label"].strip() if data["ppp_label"].strip() else "通常"
            data_date = data["date"]  
            
            # --- 1行目 ---
            cell_updates.append(gspread.Cell(r, 1, data_date))
            cell_updates.append(gspread.Cell(r, 2, code))
            cell_updates.append(gspread.Cell(r, 3, price))
            cell_updates.append(gspread.Cell(r, 4, ""))
            cell_updates.append(gspread.Cell(r, 5, "翌日終値"))
            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r, 3 + day, f"{day}営業日"))
            cell_updates.append(gspread.Cell(r, 19, "差額(対選定)"))
            cell_updates.append(gspread.Cell(r, 20, "判定(対選定)"))
            cell_updates.append(gspread.Cell(r, 21, "比率(%)"))

            # --- 2行目 ---
            cell_updates.append(gspread.Cell(r + 1, 1, "通過条件ステージ"))
            cell_updates.append(gspread.Cell(r + 1, 2, "12. 天井圏維持"))
            cell_updates.append(gspread.Cell(r + 1, 4, ""))
            cell_updates.append(gspread.Cell(r + 1, 5, "判定待ち"))
            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r + 1, 3 + day, "判定"))
            cell_updates.append(gspread.Cell(r + 1, 19, "差額枠"))
            cell_updates.append(gspread.Cell(r + 1, 20, "判定枠"))
            cell_updates.append(gspread.Cell(r + 1, 21, "比率枠"))

            # --- 3行目 ---
            cell_updates.append(gspread.Cell(r + 2, 1, "PPP"))
            cell_updates.append(gspread.Cell(r + 2, 2, ppp_status))
            cell_updates.append(gspread.Cell(r + 2, 5, "前日比(%)"))
            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r + 2, 3 + day, "前日比(%)"))

            # --- 4行目 ---
            cell_updates.append(gspread.Cell(r + 3, 1, ""))
            cell_updates.append(gspread.Cell(r + 3, 2, ""))

        if cell_updates:
            sheet2.update_cells(cell_updates, value_input_option='RAW')
            print(f"【シート2記録】完全規定合格(ステージ12) {len(sorted_codes
