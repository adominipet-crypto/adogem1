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
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  

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

stage_stats_counter = {
    6: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    7: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    8: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    9: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}
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
    except Exception as e:
        print(f"[DEBUG] 日経平均日付取得エラー: {e}")
        now = datetime.datetime.now()
        target = now.date() - datetime.timedelta(days=1)
        while target.weekday() >= 5: target -= datetime.timedelta(days=1)
        GLOBAL_LATEST_DATE = target

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
        print(f"シート新規作成: {sheet_name}")
        new_sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        headers = ["選定日付", "コード", "通過条件ステージ", "PPP", "選定時株価", "翌日終値", "判定", "比率(%)"]
        new_sheet.append_row(headers, value_input_option='RAW')
        return new_sheet

def get_stock_data_fallback(symbol, force_check_date=True):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=5y&interval=1d&nocache={int(time.time())}" 
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if res.status_code != 200:
            return None
        result = res.json().get("chart", {}).get("result", [])
        if not result: return None
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        df = pd.DataFrame({"Close": quotes.get("close", []), "Open": quotes.get("open", []), "High": quotes.get("high", []), "Low": quotes.get("low", []), "Volume": quotes.get("volume", [])}, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        df = df.dropna().sort_index()
        
        # 【修正箇所】厳格な完全一致から、前後7日以内のズレであれば許容するように緩和
        if force_check_date and GLOBAL_LATEST_DATE:
            days_diff = abs((df.index[-1].date() - GLOBAL_LATEST_DATE).days)
            if days_diff > 7:
                return None
        return df
    except Exception as e:
        return None

def get_next_trading_day_data(symbol, base_date):
    try:
        df = get_stock_data_fallback(symbol, force_check_date=False)
        if df is None: return None
        future_df = df[df.index.date > base_date]
        return future_df.iloc[0] if not future_df.empty else None
    except: return None

# --- 日経平均の判定行を自動作成する関数 ---
def get_nikkei_evaluation_line():
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/^N225?range=1mo&interval=1d&nocache={int(time.time())}"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if res.status_code != 200: return "【日経平均の判定】\n  データ取得エラー"
        
        result = res.json().get("chart", {}).get("result", [])
        if not result: return "【日経平均の判定】\n  データ空エラー"
        
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        
        df = pd.DataFrame({"Close": quotes.get("close", [])}, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        df = df.dropna().sort_index()
        
        if GLOBAL_LATEST_DATE:
            df_filtered = df[df.index.date <= GLOBAL_LATEST_DATE]
        else:
            df_filtered = df

        if len(df_filtered) < 2: return "【日経平均の判定】\n  判定データ不足"
        
        prev_close = df_filtered.iloc[-2]['Close']  
        curr_close = df_filtered.iloc[-1]['Close']  
        prev_date_str = df_filtered.index[-2].strftime("%m-%d") 
        curr_date_str = df_filtered.index[-1].strftime("%m-%d") 
        
        pct = ((curr_close - prev_close) / prev_close) * 100
        mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
        
        return f"【日経平均の判定】\n  {mark} | NIKKEI225 | {int(prev_close)}円 ({prev_date_str}) → 1営業日 | {int(curr_close)}円 ({curr_date_str}) ({pct:+.2f}%)"
    except Exception as e:
        return f"【日経平均の判定】\n  自動取得エラー: {e}"

# --- 判定処理 (答え合わせ) ---
def update_yesterday_results():
    global stage_results_report, stage_stats_counter
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        cell_list = []
        
        if GLOBAL_LATEST_DATE:
            target_match_date = get_previous_trading_day(GLOBAL_LATEST_DATE)
        else:
            target_match_date = None

        reverse_stage_map = {
            "6. 溜め": "stage6",
            "7. 右肩上がり": "stage7",
            "8. 長期トレンド": "stage8",
            "9. 当日陽線": "stage9"
        }
        
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
            code, row_date_str = row[1], row[0]
            stage_name = row[2]
            ppp_status = row[3].strip() 
            
            try: 
                selected_price = int(row[4])
                sel_date = datetime.datetime.strptime(row_date_str, "%Y-%m-%d").date()
                if target_match_date and sel_date != target_match_date:
                    continue
            except: continue

            next_data = get_next_trading_day_data(code, sel_date)
            if next_data is not None:
                next_close = int(next_data['Close'])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:+.2f}%")])
                
                s_key = reverse_stage_map.get(stage_name, "completed_pass")
                ppp_prefix = f"{ppp_status} " if ppp_status in ["★PPP", "★PPP(Short)"] else ""
                result_line = f"  {ppp_prefix}{mark} ■ {code} | {selected_price}円 ({row_date_str[5:]}) → {next_close}円 ({pct:+.2f}%)"
                stage_results_report[s_key].append(result_line)

                if stage_name == "6. 溜め": stage_stats_counter[6][mark] += 1
                elif stage_name == "7. 右肩上がり": stage_stats_counter[7][mark] += 1
                elif stage_name == "8. 長期トレンド": stage_stats_counter[8][mark] += 1
                elif stage_name == "9. 当日陽線": stage_stats_counter[9][mark] += 1

        if cell_list: sheet.update_cells(cell_list)
    except Exception as e: print(f"当月シート判定エラー: {e}")

def update_sheet2_results():
    pass

# --- 株価選定ロジック ---
def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    
    idx = len(df) - 1
    if idx < 100: return "SKIP"  
    
    prev_idx = idx - 1

    c = df['Close']; o = df['Open']; h = df['High']; v = df['Volume']
    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    ma100 = c.rolling(100).mean()
    ma300 = c.rolling(300).mean()

    # 1. 全データ取得成功
    stage_survivors["stage1"] += 1
    
    # 2. 月足MA60上抜け
    ma60_m = df['MA60_Monthly'] if 'MA60_Monthly' in df.columns else ma60
    if c.iloc[idx] > ma60_m.iloc[idx]: stage_survivors["stage2"] += 1
    else: return "SKIP"
    
    # 3. 出来高5万株以上
    if v.iloc[idx] >= 50000: stage_survivors["stage3"] += 1
    else: return "SKIP"
    
    # 4. 下半身(終値>MA5)
    if c.iloc[idx] > ma5.iloc[idx]: stage_survivors["stage4"] += 1
    else: return "SKIP"
    
    # 5. MA20上抜け後7日以内
    cross_check = False
    for i in range(idx - 6, idx + 1):
        if i >= 1 and c.iloc[i] > ma20.iloc[i] and c.iloc[i-1] <= ma20.iloc[i-1]:
            cross_check = True
            break
    if cross_check: stage_survivors["stage5"] += 1
    else: return "SKIP"

    # PPP判定用レーベル作成
    ppp_label = "★PPP " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0)) else ("★PPP(Short) " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx]) else "")
    data_date = df.index[idx].strftime("%Y-%m-%d")
    
    # 6. 溜め(前日終値<MA5)
    if c.iloc[prev_idx] < ma5.iloc[prev_idx]: stage_survivors["stage6"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage6", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
    
    # 7. 右肩上がり(MA60)
    if ma60.iloc[idx] > ma60.iloc[prev_idx]: stage_survivors["stage7"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage7", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
        
    # 8. 長期トレンド(MA100上昇)
    if ma100.iloc[idx] > ma100.iloc[prev_idx]: stage_survivors["stage8"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage8", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
        
    # 9. 当日陽線(始値<終値)
    if o.iloc[idx] < c.iloc[idx]: stage_survivors["stage9"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "stage9", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"

    # 全ステージ完全合格の記録
    sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "completed_pass", "ppp_label": ppp_label, "date": data_date}
    selected_stocks[symbol] = {"price": int(c.iloc[idx]), "ppp_label": ppp_label, "date": data_date}
    
    if "★PPP " in ppp_label: stats["★PPP"] += 1
    elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
    else: stats["normal_detect"] += 1
    return "OK"

# --- スプレッドシート記録 ---
def record_to_spreadsheet():
    try:
        sheet_current_month = connect_spreadsheet()
        stage_map = {
            "stage6": "6. 溜め", "stage7": "7. 右肩上がり",
            "stage8": "8. 長期トレンド", "stage9": "9. 当日陽線",
            "completed_pass": "9. 当日陽線" 
        }
        new_rows_s1 = [[r["date"], code, stage_map[r["stage_key"]], r["ppp_label"].strip() or "通常", r["price"], "", "判定待ち", ""] for code, r in sheet1_final_log.items() if r["stage_key"] in stage_map]
        if new_rows_s1: 
            sheet_current_month.append_rows(new_rows_s1, value_input_option='RAW')
            print(f"データ追記完了: {len(new_rows_s1)}件")
    except Exception as e:
        print(f"当月シートへの追記エラー: {e}")

# --- メイン処理 ---
def main():
    fetch_global_latest_date()
    
    # 1. 過去データの自動答え合わせ実行
    update_yesterday_results()
    update_sheet2_results()  
    
    # 2. 当日の全銘柄スクリーニング
    start_r = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_r = int(sys.argv[2]) if len(sys.argv) > 2 else 10001
    print(f"開始: {start_r} から {end_r}")
    
    for s in [str(i) for i in range(start_r, end_r)]: 
        if 1300 <= int(s) <= 1600: continue  
        analyze_stock
