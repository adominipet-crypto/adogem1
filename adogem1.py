import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError  

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# --- グローバル変数 ---
stage_survivors = {f"stage{i}": 0 for i in range(1, 13)}
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  
nikkei_report_lines = []        
final_judgement_summary = ""   

stage_results_report = {
    "trend_align": [],
    "upper_shadow": [],
    "ceiling_avoid": [],
    "new_high_pass": [],
    "weekly_ma_pass": [],
    "monthly_high_pass": [],
    "completed_pass": []
}

STAGE_LABELS = {
    "trend_align": "7.長トレンド",
    "upper_shadow": "8.上ヒゲ",
    "ceiling_avoid": "9.天井回避",
    "new_high_pass": "10.新高値",
    "weekly_ma_pass": "11.週足60",
    "monthly_high_pass": "12.天井維持",
    "completed_pass": "完全合格"
}

# デバッグ用カウンター（ログ溢れ防止）
debug_log_count = 0

# --- 共通関数 ---
def fetch_global_latest_date():
    global GLOBAL_LATEST_DATE
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/^N225?range=1mo&interval=1d&nocache={int(time.time())}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        }
        res = requests.get(url, headers=headers, timeout=15)
        timestamps = res.json().get("chart", {}).get("result", [])[0].get("timestamp", [])
        GLOBAL_LATEST_DATE = datetime.datetime.fromtimestamp(timestamps[-1]).date()
        print(f"【DEBUG】基準日取得成功 (GLOBAL_LATEST_DATE): {GLOBAL_LATEST_DATE}")
    except Exception as e:
        now = datetime.datetime.now()
        target = now.date() - datetime.timedelta(days=1)
        while target.weekday() >= 5: target -= datetime.timedelta(days=1)
        GLOBAL_LATEST_DATE = target
        print(f"【DEBUG】基準日取得エラーのため代替日を使用: {GLOBAL_LATEST_DATE} (理由: {e})")

def connect_spreadsheet(sheet_name="シート1"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    gcp_key = os.environ.get('GCP_SA_KEY')
    if not gcp_key:
        raise ValueError("GCP_SA_KEY が設定されていません。")
    
    if gcp_key.startswith('{'):
        creds = Credentials.from_service_account_info(json.loads(gcp_key), scopes=scopes)
    else:
        creds = Credentials.from_service_account_file(gcp_key, scopes=scopes)
        
    return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)

def get_stock_data_fallback(symbol, force_check_date=True):
    global debug_log_count
    try:
        if symbol == "^N225":
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/^N225?range=5y&interval=1d&nocache={int(time.time())}"
        else:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=5y&interval=1d&nocache={int(time.time())}" 
        
        # 本物のブラウザに近いUser-Agentに偽装
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
        }
        res = requests.get(url, headers=headers, timeout=15)
        
        # 200以外のHTTPエラーをすべて暴く
        if res.status_code != 200:
            if debug_log_count < 10:
                print(f"【⚠️通信警告】銘柄 {symbol} の接続に失敗。ステータスコード: {res.status_code}")
                if res.status_code == 403:
                    print(" -> [原因示唆] 403 Forbidden: GitHubのIPアドレスがYahoo側からアクセス遮断されています。")
                elif res.status_code == 429:
                    print(" -> [原因示唆] 429 Too Many Requests: 短時間での大量リクエストによる一時的ブロックです。")
                debug_log_count += 1
            return None
            
        result = res.json().get("chart", {}).get("result", [])
        if not result: return None
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        if not timestamps: return None
        
        df = pd.DataFrame({"Close": quotes.get("close", []), "Open": quotes.get("open", []), "High": quotes.get("high", []), "Low": quotes.get("low", []), "Volume": quotes.get("volume", [])}, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        df = df.dropna().sort_index()
        
        if df.empty: return None
        
        # 日付不一致で弾かれているかを暴く
        if force_check_date and GLOBAL_LATEST_DATE and df.index[-1].date() != GLOBAL_LATEST_DATE:
            if debug_log_count < 10:
                print(f"【DEBUG】銘柄 {symbol} が日付不一致でスキップ: 銘柄最新日={df.index[-1].date()} vs 基準日={GLOBAL_LATEST_DATE}")
                debug_log_count += 1
            return None
            
        return df
    except Exception as e:
        if debug_log_count < 10:
            print(f"【DEBUG】銘柄 {symbol} のデータ処理中に予期せぬ例外発生: {e}")
            debug_log_count += 1
        return None

def get_next_trading_day_data(symbol, base_date):
    try:
        df = get_stock_data_fallback(symbol, force_check_date=False)
        if df is None: return None
        future_df = df[df.index.date > base_date]
        return future_df.iloc[0] if not future_df.empty else None
    except: return None

# --- 判定処理 (前日分の自動答え合わせ) ---
def update_yesterday_results():
    global stage_results_report, nikkei_report_lines, final_judgement_summary
    try:
        sheet = connect_spreadsheet("シート1")
        all_records = sheet.get_all_values()
        cell_list = []
        reverse_stage_map = {
            "7. 長トレンド": "trend_align",
            "8. 上ヒゲ": "upper_shadow",
            "9. 天井圏回避": "ceiling_avoid",
            "10. 新高値": "new_high_pass",
            "11. 週足60": "weekly_ma_pass",
            "12. 天井圏維持": "monthly_high_pass"
        }
        
        n225_df = get_stock_data_fallback("^N225", force_check_date=False)
        nikkei_results = {}
        count_marks = {"◎": 0, "◯": 0, "▲": 0, "✕": 0}
        
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
            code, row_date_str = row[1], row[0]
            stage_name = row[2]
            try: 
                selected_price = int(row[4])
                sel_date = datetime.datetime.strptime(row_date_str, "%Y-%m-%d").date()
            except: continue
            
            if n225_df is not None and sel_date not in nikkei_results:
                n225_future = n225_df[n225_df.index.date > sel_date]
                n225_past = n225_df[n225_df.index.date <= sel_date]
                if not n225_future.empty and not n225_past.empty:
                    n225_prev_close = n225_past.iloc[-1]['Close']
                    n225_next_close = n225_future.iloc[0]['Close']
                    n225_pct = ((n225_next_close - n225_prev_close) / n225_prev_close) * 100
                    n225_mark = "◎" if n225_pct >= 2.0 else "◯" if n225_pct >= 0.1 else "▲" if n225_pct > -0.1 else "✕"
                    nikkei_results[sel_date] = f" {n225_mark} | NIKKEI225 | {int(n225_prev_close)}円 ({row_date_str[5:]}) → 1営業日 | {int(n225_next_close)}円 ({n225_pct:+.2f}%)"
            
            next_data = get_next_trading_day_data(code, sel_date)
            if next_data is not None:
                next_close = int(next_data['Close'])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:+.2f}%")])
                
                count_marks[mark] += 1
                
                s_key = reverse_stage_map.get(stage_name, "completed_pass")
                if stage_name == "12. 天井圏維持" and row[3] != "通常": 
                    s_key = "completed_pass"
                
                result_line = f"  {mark} ■ {code} | {selected_price}円 ({row_date_str[5:]}) → {next_close}円 ({pct:+.2f}%)"
                stage_results_report[s_key].append(result_line)
                
        if cell_list: sheet.update_cells(cell_list)
        
        nikkei_report_lines = list(nikkei_results.values())
        total_j = sum(count_marks.values())
        if total_j > 0:
            maru_rate = ((count_marks["◎"] + count_marks["◯"]) / total_j) * 100
            final_judgement_summary = f"◎{count_marks['◎']}件 / ◯{count_marks['◯']}件 / ▲{count_marks['▲']}件 / ✕{count_marks['✕']}件 / ◎◯{maru_rate:.0f}%"
        else:
            final_judgement_summary = "◎0件 / ◯0件 / ▲0件 / ✕0件 / ◎◯0%"
            
    except Exception as e: print(f"Sheet1判定エラー: {e}")

def update_sheet2_results():
    try:
        sheet2 = connect_spreadsheet("シート2")
        all_records = sheet2.get_all_values()
        cell_list = []
        for i in range(0, len(all_records), 4):
            if i >= len(all_records) or len(all_records[i]) < 2: continue
            
            data_date_str = ""
            code = ""
            selected_price = 0
            ppp_text = "通常"
            
            if all_records[i][0] and all_records[i][0] not in ["選定日付", "翌日終値", "判定", "前日比(%)"]:
                data_date_str = all_records[i][0]
                code = all_records[i][1]
                try: selected_price = int(all_records[i][3])
                except: continue
            elif len(all_records[i]) >= 20 and all_records[i][18] and all_records[i][17] != "選定日付":
                data_date_str = all_records[i][17]
                code = all_records[i][18]
                try: selected_price = int(all_records[i][19])
                except: continue
                
                cell_list.extend([
                    gspread.Cell(i+1, 1, data_date_str),
                    gspread.Cell(i+1, 2, code),
                    gspread.Cell(i+1, 4, selected_price)
                ])
                cell_list.extend([
                    gspread.Cell(i+2, 1, "通過条件ステージ"),
                    gspread.Cell(i+2, 2, "12. 天井圏維持"),
                    gspread.Cell(i+3, 1, "PPP")
                ])
                if i+2 < len(all_records) and len(all_records[i+2]) >= 19:
                    ppp_text = all_records[i+2][18].strip() or "通常"
                    cell_list.append(gspread.Cell(i+3, 2, ppp_text))
            else:
                continue
            
            if not code or not data_date_str: continue
            try: sel_date = datetime.datetime.strptime(data_date_str, "%Y-%m-%d").date()
            except: continue
            
            df = get_stock_data_fallback(code, force_check_date=False)
            if df is None: continue
            future_df = df[df.index.date > sel_date]
            if future_df.empty: continue
            
            first_day = future_df.iloc[0]
            close_1 = int(first_day['Close'])
            pct_1 = ((close_1 - selected_price) / selected_price) * 100
            cell_list.extend([gspread.Cell(i+2, 5, close_1), gspread.Cell(i+3, 5, f"{pct_1:+.2f}%")])
            
            for day_idx in range(1, min(len(future_df), 14)):
                col = day_idx + 5  
                close_curr = int(future_df.iloc[day_idx]['Close'])
                close_prev = int(future_df.iloc[day_idx-1]['Close'])
                pct_day = ((close_curr - close_prev) / close_prev) * 100
                cell_list.extend([gspread.Cell(i+2, col, close_curr), gspread.Cell(i+3, col, f"{pct_day:+.2f}%")])
                
        if cell_list: 
            sheet2.update_cells(cell_list, value_input_option='RAW')
            print(f"シート2のデータを {len(cell_list)} 箇所自動修復・更新しました。")
    except Exception as e: print(f"Sheet2更新エラー: {e}")

# --- 株価選定ロジック ---
def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    
    idx = len(df) - 1
    if idx < 480: return "SKIP"
    
    prev_idx = idx - 1

    c = df['Close']; o = df['Open']; h = df['High']; v = df['Volume']
    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    ma100 = c.rolling(100).mean()
    ma300 = c.rolling(300).mean()
    ma24_m = c.rolling(24*20).mean() 
    ma60_w = c.rolling(60*5).mean()

    if c.iloc[idx] > ma60.iloc[idx]: stage_survivors["stage1"] += 1; stage_survivors["stage2"] += 1
    else: return "SKIP"
    if v.iloc[idx] >= 50000: stage_survivors["stage3"] += 1
    else: return "SKIP"
    if c.iloc[idx] > ma5.iloc[idx]: stage_survivors["stage4"] += 1
    else: return "SKIP"
    if c.iloc[prev_idx] < ma5.iloc[prev_idx]: stage_survivors["stage5"] += 1
    else: return "SKIP"
    if ma60.iloc[idx] > ma60.iloc[prev_idx]: stage_survivors["stage6"] += 1
    else: return "SKIP"
    
    ppp_label = "★PPP " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0)) else ("★PPP(Short) " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx]) else "")
    data_date = df.index[idx].strftime("%Y-%m-%d")
    
    if ma100.iloc[idx] > ma100.iloc
