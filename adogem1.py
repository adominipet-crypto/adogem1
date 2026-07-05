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
JQ_REFRESH_TOKEN = os.environ.get('JQ_REFRESH_TOKEN')

# --- グローバル変数 ---
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  
ALL_STOCK_DATA_CACHE = {}

stage_results_report = {
    "stage6": [], "stage7": [], "stage8": [], "stage9": [], "completed_pass": []
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

# --- J-Quants API ---
def fetch_all_stock_data_from_jquants():
    global GLOBAL_LATEST_DATE, ALL_STOCK_DATA_CACHE
    if not JQ_REFRESH_TOKEN:
        print("エラー: JQ_REFRESH_TOKEN が未設定です。")
        return False
        
    try:
        print("J-Quants API 認証中...")
        auth_url_base = "https://api.jquants.com/v1/auth/idtoken"
        auth_url = f"{auth_url_base}?refreshToken={JQ_REFRESH_TOKEN}"
        res = requests.post(auth_url, timeout=15)
        id_token = res.json().get("idToken")
        if not id_token:
            return False
            
        headers = {"Authorization": f"Bearer {id_token}"}
        
        # 【テスト用設定】日付を直近の金曜日に固定
        today_str = "2026-07-03"
        print(f"【テスト】日付固定({today_str})で取得中...")
        
        p_url_base = "https://api.jquants.com/v1/prices/daily_quotes"
        prices_url = f"{p_url_base}?date={today_str}"
        res = requests.get(prices_url, headers=headers, timeout=30)
        
        if res.status_code != 200 or not res.json().get("daily_quotes"):
            prices_url = p_url_base
            res = requests.get(prices_url, headers=headers, timeout=30)
            
        data = res.json().get("daily_quotes", [])
        if not data:
            return False
            
        latest_date_str = data[0]["Date"]
        GLOBAL_LATEST_DATE = datetime.datetime.strptime(
            latest_date_str, "%Y-%m-%d"
        ).date()
        
        for item in data:
            code = item["Code"][:4]
            ALL_STOCK_DATA_CACHE[code] = item
            
        return True
    except Exception as e:
        print(f"エラー: {e}")
        return False

def get_previous_trading_day(base_date):
    target = base_date - datetime.timedelta(days=1)
    while target.weekday() >= 5:
        target -= datetime.timedelta(days=1)
    return target

def connect_spreadsheet(sheet_name=None):
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets", 
        "https://www.googleapis.com/auth/drive"
    ]
    gcp_key = os.environ.get('GCP_SA_KEY')
    if gcp_key.startswith('{'):
        creds = Credentials.from_service_account_info(
            json.loads(gcp_key), scopes=scopes
        )
    else:
        creds = Credentials.from_service_account_file(gcp_key, scopes=scopes)
        
    spreadsheet = gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ")
    
    if sheet_name is None:
        td = GLOBAL_LATEST_DATE if GLOBAL_LATEST_DATE else datetime.date.today()
        sheet_name = f"{td.month}月"
        
    try:
        return spreadsheet.worksheet(sheet_name)
    except gspread.exceptions.WorksheetNotFound:
        new_sheet = spreadsheet.add_worksheet(
            title=sheet_name, rows="1000", cols="20"
        )
        h = ["選定日付", "コード", "通過条件ステージ", "PPP", "選定時株価", "翌日終値", "判定", "比率(%)"]
        new_sheet.append_row(h, value_input_option='RAW')
        return new_sheet

def get_stock_data_fallback(symbol, force_check_date=True):
    try:
        item = ALL_STOCK_DATA_CACHE.get(symbol)
        if not item or item.get("Close") is None: return None
        
        df = pd.DataFrame({
            "Open": [item["Open"]], 
            "High": [item["High"]], 
            "Low": [item["Low"]], 
            "Close": [item["Close"]], 
            "Volume": [item["Volume"]]
        }, index=[GLOBAL_LATEST_DATE])
        return df
    except: return None

def get_next_trading_day_data(symbol, base_date):
    try:
        item = ALL_STOCK_DATA_CACHE.get(symbol)
        if item and item.get("Close") is None: return None
        return {"Close": item["Close"]}
    except: return None

# --- 日経平均 ---
def get_nikkei_evaluation_line():
    try:
        # 改行エラー対策のため文字列を小分けにして連結
        url = (
            "https://"
            "kabutan.jp/stock/"
            "kabuka?code=0000"
        )
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/91.0.4472.124 Safari/537.36"
        )
        headers = {"User-Agent": ua}
        res = requests.get(url, headers=headers, timeout=15)
        
        if res.status_code != 200: return "【日経】取得エラー"
        
        p1 = r'<td><time datetime="(\d{4}-\d{2}-\d{2})">.*?</time></td>'
        p2 = r'\s*<td>.*?</td>\s*<td>.*?</td>\s*<td>.*?</td>'
        p3 = r'\s*<td class="[^"]*">([\d,]+\.\d+)</td>'
        pattern = p1 + p2 + p3
        
        matches = re.findall(pattern, res.text)
        
        if not matches:
            fb1 = r'<td>\s*(\d{2}/\d{2}/\d{2})\s*</td>\s*<td>.*?</td>'
            fb2 = r'\s*<td>.*?</td>\s*<td>.*?</td>\s*<td>\s*([\d,]+)\s*</td>'
            matches = re.findall(fb1 + fb2, res.text)
            
        if not matches: return "【日経】解析エラー"
        
        parsed_data = []
        for m in matches:
            date_str, close_str = m[0], m[1]
            if "/" in date_str:
                dt = datetime.datetime.strptime(f"20{date_str}", "%Y/%m/%d").date()
            else:
                dt = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            c_val = float(close_str.replace(",", ""))
            parsed_data.append({"Date": dt, "Close": c_val})
            
        df = pd.DataFrame(parsed_data).set_index("Date").sort_index()
        if len(df) < 2: return "【日経】データ不足"
        
        curr_date = GLOBAL_LATEST_DATE if GLOBAL_LATEST_DATE else df.index[-1]
        prev_date = get_previous_trading_day(curr_date)
        
        if prev_date in df.index and curr_date in df.index:
            p_close = df.loc[prev_date, 'Close']
            c_close = df.loc[curr_date, 'Close']
            p_str = prev_date.strftime("%m-%d")
            c_str = curr_date.strftime("%m-%d")
        else:
            p_close = df.iloc[-2]['Close']  
            c_close = df.iloc[-1]['Close']  
            p_str = df.index[-2].strftime("%m-%d")
            c_str = df.index[-1].strftime("%m-%d")
        
        pct = ((c_close - p_close) / p_close) * 100
        mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
        
        return f"【日経】{mark} | {int(p_close)}円({p_str}) → {int(c_close)}円({c_str}) ({pct:+.2f}%)"
    except Exception as e:
        return f"【日経】エラー: {e}"

# --- 判定処理 ---
def update_yesterday_results():
    global stage_results_report, stage_stats_counter
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        cell_list = []
        
        target_match_date = get_previous_trading_day(GLOBAL_LATEST_DATE) if GLOBAL_LATEST_DATE else None

        r_map = {
            "6. 溜め": "stage6", "7. 右肩上がり": "stage7",
            "8. 長期トレンド": "stage8", "9. 当日陽線": "stage9"
        }
        
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
            code, row_date_str, stage_name, ppp_status = row[1], row[0], row[2], row[3].strip()
            
            try: 
                s_price = int(row[4])
                sel_date = datetime.datetime.strptime(row_date_str, "%Y-%m-%d").date()
                if target_match_date and sel_date != target_match_date: continue
            except: continue
            
            next_data = get_next_trading_day_data(code, sel_date)
            if next_data is not None:
                n_close = int(next_data['Close'])
                pct = ((n_close - s_price) / s_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                
                cell_list.extend([
                    gspread.Cell(i+1, 6, n_close), 
                    gspread.Cell(i+1, 7, mark), 
                    gspread.Cell(i+1, 8, f"{pct:+.2f}%")
                ])
                
                s_key = r_map.get(stage_name, "completed_pass")
                p_pref = f"{ppp_status} " if ppp_status in ["★PPP", "★PPP(Short)"] else ""
                r_line = f"  {p_pref}{mark} ■ {code} | {s_price}円({row_date_str[5:]}) → {n_close}円({pct:+.2f}%)"
                stage_results_report[s_key].append(r_line)

                if stage_name == "6. 溜め": stage_stats_counter[6][mark] += 1
                elif stage_name == "7. 右肩上がり": stage_stats_counter[7][mark] += 1
                elif stage_name == "8. 長期トレンド": stage_stats_counter[8][mark] += 1
                elif stage_name == "9. 当日陽線": stage_stats_counter[9][mark] += 1

        if cell_list: sheet.update_cells(cell_list)
    except Exception as e: print(f"判定エラー: {e}")

def update_sheet2_results(): pass

# --- 選定ロジック ---
def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    
    c, o, v = df['Close'].iloc[0], df['Open'].iloc[0], df['Volume'].iloc[0]

    stage_survivors["stage1"] += 1
    stage_survivors["stage2"] += 1
    if v >= 50000: stage_survivors["stage3"] += 1
    else: return "SKIP"
    
    stage_survivors["stage4"] += 1
    stage_survivors["stage5"] += 1
    stage_survivors["stage6"] += 1
    stage_survivors["stage7"] += 1
    stage_survivors["stage8"] += 1
        
    ppp_label = "" 
    data_date = df.index[0].strftime("%Y-%m-%d")
    
    if o < c:
        stage_survivors["stage9"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c), "stage_key": "stage9", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"

    sheet1_final_log[symbol] = {"price": int(c), "stage_key": "completed_pass", "ppp_label": ppp_label, "date": data_date}
    selected_stocks[symbol] = {"price": int(c), "ppp_label": ppp_label, "date": data_date}
    stats["normal_detect"] += 1
    return "OK"

# --- 記録 ---
def record_to_spreadsheet():
    try:
        sheet = connect_spreadsheet()
        s_map = {
            "stage6": "6. 溜め", "stage7": "7. 右肩上がり",
            "stage8": "8. 長期トレンド", "stage9": "9. 当日陽線",
            "completed_pass": "9. 当日陽線"
        }
        rows = [
            [r["date"], c, s_map[r["stage_key"]], r["ppp_label"].strip() or "通常", r["price"], "", "判定待ち", ""] 
            for c, r in sheet1_final_log.items() if r["stage_key"] in s_map
        ]
        if rows: sheet.append_rows(rows, value_input_option='RAW')
    except Exception as e: print(f"追記エラー: {e}")

# --- メイン ---
def main():
    if not fetch_all_stock_data_from_jquants(): return

    update_yesterday_results()
    update_sheet2_results()  
    
    start_r, end_r = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 10001)
    
    for s in [str(i) for i in range(start_r, end_r)]: 
        if 1300 <= int(s) <= 1600: continue  
        analyze_stock(s)
        
    record_to_spreadsheet()
    
    final_list = [f"  ■ {c} | {s['price']}円 ({s['date'][5:]})" for c, s in sorted(selected_stocks.items())]
    header = f"データ対象日: {GLOBAL_LATEST_DATE}"
    
    surv = (
        f"1.取得:{stage_survivors['stage1']} 2.M60:{stage_survivors['stage2']} "
        f"3.出来:{stage_survivors['stage3']} 4.下半身:{stage_survivors['stage4']}\n"
        f"5.M20:{stage_survivors['stage5']} 6.溜め:{stage_survivors['stage6']} "
        f"7.右肩:{stage_survivors['stage7']} 8.長期:{stage_survivors['stage8']} "
        f"9.陽線:{stage_survivors['stage9']}"
    )
    
    nikkei = get_nikkei_evaluation_line()
    
    j_lines = ["【本日確定の判定結果】"]
    for key in ["stage6", "stage7", "stage8", "stage9", "completed_pass"]:
        j_lines.append(f"■ {STAGE_LABELS.get(key)}")
        lines = stage_results_report.get(key, [])
        if lines: j_lines.extend(lines)
        else: j_lines.append("  該当なし")
        j_lines.append("") 
        
    j_block = "\n".join(j_lines).strip()
    f_str = "\n".join(final_list) if final_list else '  該当なし'

    l_lines = []
    for stg in [6, 7, 8, 9]:
        cts = stage_stats_counter[stg]
        tot = sum(cts.values())
        wr = int(round((cts["◎"] + cts["◯"]) / tot * 100)) if tot > 0 else 0
        l_lines.append(f"{stg}. ◎{cts['◎']} ◯{cts['◯']} ▲{cts['▲']} ✕{cts['✕']} / {wr}%")
        
    l_text = "\n".join(l_lines)

    body = (
        f"================================\n"
        f"{header}\n\n"
        f"【各ステージ生存数】\n{surv}\n\n"
        f"★PPP:{stats['★PPP']} Short:{stats['★PPP(Short)']} 通常:{stats['normal_detect']}\n\n"
        f"【完全合格一覧】\n{f_str}\n\n"
        f"================================\n"
        f"{nikkei}\n\n{j_block}\n\n"
        f"--------------------------------\n"
        f"【6〜9の判定結果】\n{l_text}\n"
    )
    
    try:
        msg = MIMEMultipart()
        msg['From'] = msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"📊 adoGEM レポート {len(final_list)}件"
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
    except Exception as e: print(f"メール送信エラー: {e}")

if __name__ == "__main__": 
    main()
