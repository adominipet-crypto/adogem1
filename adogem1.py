import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

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
        now = datetime.datetime.now()
        target = now.date() - datetime.timedelta(days=1)
        while target.weekday() >= 5: target -= datetime.timedelta(days=1)
        GLOBAL_LATEST_DATE = target

def connect_spreadsheet(sheet_name="シート1"):
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        sa_key = os.environ.get('GCP_SA_KEY')
        if not sa_key: raise ValueError("GCP_SA_KEYが設定されていません")
        creds = Credentials.from_service_account_info(json.loads(sa_key), scopes=scopes)
        return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)
    except Exception as e:
        print(f"★[ERROR] スプレッドシート接続失敗: {e}")
        raise

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

# --- 判定処理 ---
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
            
            # 翌日の株価取得
            df = get_stock_data_fallback(code, force_check_date=False)
            if df is None: continue
            future_df = df[df.index.date > sel_date]
            if not future_df.empty:
                next_close = int(future_df.iloc[0]['Close'])
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

# --- スキャン処理 ---
def analyze_stock(symbol):
    # 【ETF/REIT除外フィルタ】
    if 1300 <= int(symbol) <= 1699: return "SKIP"
    
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
    if today['MA60'] <= yest['MA60']: return "SKIP"
    stage_survivors["stage6"] += 1

    ppp_label = "★PPP " if (today['MA5'] > today['MA20'] > today['MA60'] > today['MA100'] > (today['MA300'] if pd.notna(today['MA300']) else 0)) else ("★PPP(Short) " if (today['MA5'] > today['MA20'] > today['MA60'] > today['MA100']) else "")
    data_date = df.index[-1].strftime("%Y-%m-%d")

    if today['MA100'] <= yest['MA100']: 
        sheet1_final_log[symbol] = {"price": int(today['Close']), "stage_key": "trend_align", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
    stage_survivors["stage7"] += 1
    if (today['High'] - today['Close']) >= ((today['Close'] - today['Open']) * 1.5):
        sheet1_final_log[symbol] = {"price": int(today['Close']), "stage_key": "upper_shadow", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
    stage_survivors["stage8"] += 1
    if today['MA100'] <= today['Close'] <= (today['MA100'] * 1.03):
        sheet1_final_log[symbol] = {"price": int(today['Close']), "stage_key": "ceiling_avoid", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
    stage_survivors["stage9"] += 1
    if today['Close'] <= df['High'].iloc[-6:-1].max():
        sheet1_final_log[symbol] = {"price": int(today['Close']), "stage_key": "new_high_pass", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
    stage_survivors["stage10"] += 1
    if df['Close'].resample('W').last().rolling(60).mean().iloc[-1] > df['Close'].resample('W').last().iloc[-1]:
        sheet1_final_log[symbol] = {"price": int(today['Close']), "stage_key": "weekly_ma_pass", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
    stage_survivors["stage11"] += 1
    if today['Close'] < (monthly_close.rolling(24).mean().iloc[-1] * 0.80):
        sheet1_final_log[symbol] = {"price": int(today['Close']), "stage_key": "monthly_high_pass", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"

    sheet1_final_log[symbol] = {"price": int(today['Close']), "stage_key": "completed_pass", "ppp_label": ppp_label, "date": data_date}
    selected_stocks[symbol] = {"price": int(today['Close']), "ppp_label": ppp_label, "date": data_date}
    if "★PPP " in ppp_label: stats["★PPP"] += 1
    elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
    else: stats["normal_detect"] += 1
    return "OK"

def record_to_spreadsheet():
    try:
        sheet = connect_spreadsheet("シート1")
        new_rows = [[r["date"], code, {"trend_align":"7. 長トレンド","upper_shadow":"8. 上ヒゲ","ceiling_avoid":"9. 天井圏回避","new_high_pass":"10. 新高値","weekly_ma_pass":"11. 週足60","monthly_high_pass":"12. 天井圏維持","completed_pass":"12. 天井圏維持"}[r["stage_key"]], r["ppp_label"].strip() or "通常", r["price"], "", "判定待ち", ""] for code, r in sheet1_final_log.items() if r["stage_key"] in ["trend_align", "upper_shadow", "ceiling_avoid", "new_high_pass", "weekly_ma_pass", "monthly_high_pass", "completed_pass"]]
        if new_rows: sheet.append_rows(new_rows, value_input_option='RAW')
    except Exception as e: print(f"記録エラー: {e}")

def main():
    print("★[SYSTEM] 処理を開始します")
    try:
        fetch_global_latest_date()
        update_yesterday_results()
        update_sheet2_results()
        
        start_r = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
        end_r = int(sys.argv[2]) if len(sys.argv) > 2 else 10001
        
        print(f"★[SYSTEM] {start_r}〜{end_r}をスキャン")
        for s in [str(i) for i in range(start_r, end_r)]:
            analyze_stock(s)
            
        record_to_spreadsheet()
        # (以下メール送信等の省略部分は既存コードと統合してください)
    except Exception as e:
        print(f"★[CRITICAL ERROR] {e}")
        traceback.print_exc()

if __name__ == "__main__": main()
