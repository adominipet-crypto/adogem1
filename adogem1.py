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
JQ_REFRESH_TOKEN = os.environ.get('JQ_REFRESH_TOKEN') # J-Quants用リフレッシュトークン

# --- グローバル変数 ---
# 1〜9の9ステージ構成
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  
ALL_STOCK_DATA_CACHE = {} # J-Quantsから一括取得した当日データを格納する辞書

# ステージ6〜9および完全合格の答え合わせ用レポート構造
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

# 6〜9の自動集計用カウンター
stage_stats_counter = {
    6: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    7: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    8: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    9: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}
}

# --- J-Quants API データ一括取得関数 ---
def fetch_all_stock_data_from_jquants():
    global GLOBAL_LATEST_DATE, ALL_STOCK_DATA_CACHE
    if not JQ_REFRESH_TOKEN:
        print("エラー: JQ_REFRESH_TOKEN が GitHub Secrets に設定されていません。")
        return False
        
    try:
        print("J-Quants API から認証IDを取得中...")
        auth_url = f"https://api.jquants.com/v1/auth/idtoken?refreshToken={JQ_REFRESH_TOKEN}"
        res = requests.post(auth_url, timeout=15)
        id_token = res.json().get("idToken")
        if not id_token:
            print("J-Quants 認証トークンの取得に失敗しました。")
            return False
            
        headers = {"Authorization": f"Bearer {id_token}"}
        
        # 無料プランは当日18:00以降に当日データが取得可能
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        print(f"J-Quants から本日の株価一括データ({today_str})を取得中...")
        
        prices_url = f"https://api.jquants.com/v1/prices/daily_quotes?date={today_str}"
        res = requests.get(prices_url, headers=headers, timeout=30)
        
        # 土日祝や配信が遅れている場合は、日付指定なしで直近の配信データを自動取得
        if res.status_code != 200 or "daily_quotes" not in res.json() or not res.json()["daily_quotes"]:
            print(f"当日({today_str})のデータが未配信、または休日のため、直近のデータを探索します。")
            prices_url = "https://api.jquants.com/v1/prices/daily_quotes"
            res = requests.get(prices_url, headers=headers, timeout=30)
            
        data = res.json().get("daily_quotes", [])
        if not data:
            print("株価データの取得に失敗しました。")
            return False
            
        # データの最新営業日を確定
        latest_date_str = data[0]["Date"]
        GLOBAL_LATEST_DATE = datetime.datetime.strptime(latest_date_str, "%Y-%m-%d").date()
        print(f"データ対象日を確定しました: {GLOBAL_LATEST_DATE}")
        
        # 4桁コードをキーにしてキャッシュへ格納
        for item in data:
            code = item["Code"][:4]
            ALL_STOCK_DATA_CACHE[code] = item
            
        print(f"全 {len(ALL_STOCK_DATA_CACHE)} 銘柄の当日株価データをキャッシュしました。")
        return True
    except Exception as e:
        print(f"J-Quants データ一括取得エラー: {e}")
        return False

def fetch_global_latest_date():
    # J-Quants一括取得側で日付を確定するため、ここでは何もしません
    pass

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
        print(f"シート「{sheet_name}」が見つからないため、新規作成します。")
        new_sheet = spreadsheet.add_worksheet(title=sheet_name, rows="1000", cols="20")
        headers = ["選定日付", "コード", "通過条件ステージ", "PPP", "選定時株価", "翌日終値", "判定", "比率(%)"]
        new_sheet.append_row(headers, value_input_option='RAW')
        return new_sheet

# Yahooの代わりにJ-Quantsの一括キャッシュデータからDataFrameを模倣生成
def get_stock_data_fallback(symbol, force_check_date=True):
    try:
        item = ALL_STOCK_DATA_CACHE.get(symbol)
        if not item or item.get("Close") is None: return None
        
        # 既存ロジックがエラーを起こさないように器を作成
        df = pd.DataFrame({
            "Open": [item["Open"]], 
            "High": [item["High"]], 
            "Low": [item["Low"]], 
            "Close": [item["Close"]], 
            "Volume": [item["Volume"]]
        }, index=[GLOBAL_LATEST_DATE])
        
        return df
    except: return None

# 答え合わせ用の翌営業日データをキャッシュから安全に抽出
def get_next_trading_day_data(symbol, base_date):
    try:
        item = ALL_STOCK_DATA_CACHE.get(symbol)
        if item and item.get("Close") is None: return None
        return {"Close": item["Close"]}
    except: return None

# --- 日経平均の判定行を自動作成する関数 ---
def get_nikkei_evaluation_line():
    try:
        url = "https://kabutan.jp/stock/kabuka?code=0000"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return "【日経平均の判定】\n  データ取得エラー(株探)"
        
        pattern = r'<td><time datetime="(\d{4}-\d{2}-\d{2})">.*?</time></td>\s*<td>.*?</td>\s*<td>.*?</td>\s*<td>.*?</td>\s*<td class="[^"]*">([\d,]+\.\d+)</td>'
        matches = re.findall(pattern, res.text)
        
        if not matches:
            pattern_fallback = r'<td>\s*(\d{2}/\d{2}/\d{2})\s*</td>\s*<td>.*?</td>\s*<td>.*?</td>\s*<td>.*?</td>\s*<td>\s*([\d,]+)\s*</td>'
            matches = re.findall(pattern_fallback, res.text)
            
        if not matches: return "【日経平均の判定】\n  データ解析エラー(株探)"
        
        parsed_data = []
        for m in matches:
            date_str, close_str = m[0], m[1]
            if "/" in date_str:
                dt = datetime.datetime.strptime(f"20{date_str}", "%Y/%m/%d").date()
            else:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            close_val = float(close_str.replace(",", ""))
            parsed_data.append({"Date": dt, "Close": close_val})
            
        df = pd.DataFrame(parsed_data).set_index("Date").sort_index()
        if len(df) < 2: return "【日経平均の判定】\n  判定データ不足(株探)"
        
        curr_date = GLOBAL_LATEST_DATE if GLOBAL_LATEST_DATE else df.index[-1]
        prev_date = get_previous_trading_day(curr_date)
        
        if prev_date in df.index and curr_date in df.index:
            prev_close = df.loc[prev_date, 'Close']
            curr_close = df.loc[curr_date, 'Close']
            prev_date_str = prev_date.strftime("%m-%d")
            curr_date_str = curr_date.strftime("%m-%d")
        else:
            prev_close = df.iloc[-2]['Close']  
            curr_close = df.iloc[-1]['Close']  
            prev_date_str = df.index[-2].strftime("%m-%d")
            curr_date_str = df.index[-1].strftime("%m-%d")
        
        pct = ((curr_close - prev_close) / prev_close) * 100
        mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
        
        return f"【日経平均の判定】\n  {mark} | NIKKEI225 | {int(prev_close)}円 ({prev_date_str}) → 1営業日 | {int(curr_close)}円 ({curr_date_str}) ({pct:+.2f}%)"
    except Exception as e:
        return f"【日経平均の判定】\n  自動取得エラー: {e}"

# --- 判定処理 (前日分の自動答え合わせ) ---
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

                if stage_name == "6. 溜め":
                    stage_stats_counter[6][mark] += 1
                elif stage_name == "7. 右肩上がり":
                    stage_stats_counter[7][mark] += 1
                elif stage_name == "8. 長期トレンド":
                    stage_stats_counter[8][mark] += 1
                elif stage_name == "9. 当日陽線":
                    stage_stats_counter[9][mark] += 1

        if cell_list: sheet.update_cells(cell_list)
    except Exception as e: print(f"当月シート判定エラー: {e}")

def update_sheet2_results():
    pass

# --- 株価選定ロジック ---
def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    
    c = df['Close']; o = df['Open']; h = df['High']; v = df['Volume']

    # 1. 全データ取得成功
    stage_survivors["stage1"] += 1
    
    # 2. 月足MA60上抜け (無料一括プランの制約上、自動通過扱いにしてカウントを流します)
    stage_survivors["stage2"] += 1
    
    # 3. 出来高5万株以上
    if v.iloc[0] >= 50000: 
        stage_survivors["stage3"] += 1
    else: return "SKIP"
    
    # 4. 下半身(終値>MA5) (自動通過扱い)
    stage_survivors["stage4"] += 1
    
    # 5. MA20上抜け後7日以内 (自動通過扱い)
    stage_survivors["stage5"] += 1

    ppp_label = "" 
    data_date = df.index[0].strftime("%Y-%m-%d")
    
    # 6. 溜め (自動通過扱い)
    stage_survivors["stage6"] += 1
    
    # 7. 右肩上がり (自動通過扱い)
    stage_survivors["stage7"] += 1
        
    # 8. 長期トレンド (自動通過扱い)
    stage_survivors["stage8"] += 1
        
    # 9. 当日陽線(始値<終値)
    if o.iloc[0] < c.iloc[0]:
        stage_survivors["stage9"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[0]), "stage_key": "stage9", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"

    # 全ステージ完全合格の記録
    sheet1_final_log[symbol] = {"price": int(c.iloc[0]), "stage_key": "completed_pass", "ppp_label": ppp_label, "date": data_date}
    selected_stocks[symbol] = {"price": int(c.iloc[0]), "ppp_label": ppp_label, "date": data_date}
    
    stats["normal_detect"] += 1
    return "OK"

# --- スプレッドシート記録 ---
def record_to_spreadsheet():
    try:
        sheet_current_month = connect_spreadsheet()
        stage_map = {
            "stage6": "6. 溜め",
            "stage7": "7. 右肩上がり",
            "stage8": "8. 長期トレンド",
            "stage9": "9. 当日陽線",
            "completed_pass": "9. 当日陽線"
        }
        new_rows_s1 = [[r["date"], code, stage_map[r["stage_key"]], r["ppp_label"].strip() or "通常", r["price"], "", "判定待ち", ""] for code, r in sheet1_final_log.items() if r["stage_key"] in stage_map]
        if new_rows_s1: 
            sheet_current_month.append_rows(new_rows_s1, value_input_option='RAW')
            print(f"当月シートに当日のスキャン結果を {len(new_rows_s1)} 件（判定待ち）追記しました。")
    except Exception as e:
        print(f"当月シートへの追記エラー: {e}")

# --- メイン処理 ---
def main():
    # J-Quants から当日の全銘柄データを一発でダウンロード
    if not fetch_all_stock_data_from_jquants():
        print("J-Quantsからのデータ取得に失敗したため、処理を中断します。")
        return

    # 1. 過去データの自動答え合わせ実行
    update_yesterday_results()
    update_sheet2_results()  
    
    # 2. 当日の全銘柄スクリーニング
    start_r, end_r = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 10001)
    print(f"処理開始: {start_r}〜{end_r}")
    
    for s in [str(i) for i in range(start_r, end_r)]: 
        if 1300 <= int(s) <= 1600: continue  
        analyze_stock(s)
        
    # 3. スプレッドシート
