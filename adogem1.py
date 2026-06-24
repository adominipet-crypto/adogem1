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
stage_survivors = {f"stage{i}": 0 for i in range(1, 12)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  
stage_results_report = {
    "trend_align": [],
    "upper_shadow": [],
    "ceiling_avoid": [],
    "new_high_pass": [],
    "positive_01_pass": [],  # 0.1%以上陽線用に統一
    "completed_pass": []
}

STAGE_LABELS = {
    "trend_align": "7.長トレンド",
    "upper_shadow": "8.上ヒゲ",
    "ceiling_avoid": "9.天井回避(現在スルー中)",
    "new_high_pass": "10.新高値",
    "positive_01_pass": "11.0.1%以上陽線", 
    "completed_pass": "完全合格"
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

def get_next_trading_day_data(symbol, base_date):
    try:
        df = get_stock_data_fallback(symbol, force_check_date=False)
        if df is None: return None
        future_df = df[df.index.date > base_date]
        return future_df.iloc[0] if not future_df.empty else None
    except: return None

# --- 判定処理 (前日分の自動答え合わせ) ---
def update_yesterday_results():
    global stage_results_report
    try:
        sheet = connect_spreadsheet("シート1")
        all_records = sheet.get_all_values()
        cell_list = []
        reverse_stage_map = {
            "7. 長トレンド": "trend_align",
            "8. 上ヒゲ": "upper_shadow",
            "9. 天井圏回避": "ceiling_avoid",
            "10. 新高値": "new_high_pass",
            "11. 0.1%以上陽線": "positive_01_pass"
        }
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
            code, row_date_str = row[1], row[0]
            stage_name = row[2]
            try: 
                selected_price = int(row[4])
                sel_date = datetime.datetime.strptime(row_date_str, "%Y-%m-%d").date()
            except: continue
            next_data = get_next_trading_day_data(code, sel_date)
            if next_data is not None:
                next_close = int(next_data['Close'])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct >= 0.1 else "▲" if pct > -0.1 else "✕"
                cell_list.extend([gspread.Cell(i+1, 6, next_close), gspread.Cell(i+1, 7, mark), gspread.Cell(i+1, 8, f"{pct:+.2f}%")])
                
                s_key = reverse_stage_map.get(stage_name, "completed_pass")
                if stage_name == "11. 0.1%以上陽線" and row[3] != "通常": 
                    s_key = "completed_pass"
                
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
            if i >= len(all_records) or len(all_records[i]) < 20: continue
            data_date_str, code = all_records[i][17], all_records[i][18]
            if not code or data_date_str == "選定日付": continue
            try: 
                selected_price = int(all_records[i][19])
                sel_date = datetime.datetime.strptime(data_date_str, "%Y-%m-%d").date()
            except: continue
            df = get_stock_data_fallback(code, force_check_date=False)
            if df is None: continue
            future_df = df[df.index.date > sel_date]
            if future_df.empty: continue
            
            # 1日目（翌日終値）の更新
            first_day = future_df.iloc[0]
            close_1 = int(first_day['Close'])
            pct_1 = ((close_1 - selected_price) / selected_price) * 100
            cell_list.extend([gspread.Cell(i+2, 1, close_1), gspread.Cell(i+3, 1, f"{pct_1:+.2f}%")])
            
            # 2日目〜14日目の更新（3〜15営業日分）
            for day_idx in range(1, min(len(future_df), 14)):
                col = day_idx + 1
                close_curr = int(future_df.iloc[day_idx]['Close'])
                close_prev = int(future_df.iloc[day_idx-1]['Close'])
                pct_day = ((close_curr - close_prev) / close_prev) * 100
                cell_list.extend([gspread.Cell(i+2, col, close_curr), gspread.Cell(i+3, col, f"{pct_day:+.2f}%")])
        if cell_list: sheet2.update_cells(cell_list, value_input_option='RAW')
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

    # 1. データ取得成功
    stage_survivors["stage1"] += 1
    
    # 2. 月足60
    if c.iloc[idx] > ma60.iloc[idx]: 
        stage_survivors["stage2"] += 1
    else: return "SKIP"
    
    # 3. 出来高5万株以上
    if v.iloc[idx] >= 50000: 
        stage_survivors["stage3"] += 1
    else: return "SKIP"
    
    # 4. 下半身
    if c.iloc[idx] > ma5.iloc[idx]: 
        stage_survivors["stage4"] += 1
    else: return "SKIP"
    
    # 5. 溜め
    if c.iloc[prev_idx] < ma5.iloc[prev_idx]: 
        stage_survivors["stage5"] += 1
    else: return "SKIP"
    
    # 6. 右肩
    if ma60.iloc[idx] > ma60.iloc[prev_idx]: 
        stage_survivors["stage6"] += 1
    else: return "SKIP"
    
    # PPP判定用レーベル作成
    ppp_label = "★PPP " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0)) else ("★PPP(Short) " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx]) else "")
    data_date = df.index[idx].strftime("%Y-%m-%d")
    
    # 7. 長期トレンド
    if ma100.iloc[idx] > ma100.iloc[prev_idx]: 
        stage_survivors["stage7"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "trend_align", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
        
    # 8. 上ヒゲクリア
    upper = h.iloc[idx] - max(o.iloc[idx], c.iloc[idx])
    body = abs(c.iloc[idx] - o.iloc[idx])
    if body == 0 or (upper <= (body * 1.5)): 
        stage_survivors["stage8"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "upper_shadow", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
        
    # 9. 天井圏MA100回避【★一時的に無条件スルー記号（True or）を追加】
    if True or (abs(c.iloc[idx] - ma100.iloc[idx]) / ma100.iloc[idx]) >= 0.03: 
        stage_survivors["stage9"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "ceiling_avoid", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
        
    # 10. 新高値MA5更新
    if ma5.iloc[idx] >= ma5.rolling(20).max().iloc[idx]: 
        stage_survivors["stage10"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "new_high_pass", "ppp_label": ppp_label, "date": data_date}
        return "SKIP"
        
    # 新11. 0.1%以上陽線クリア (開始値より終値が0.1%以上高い場合のみ通過)
    if o.iloc[idx] > 0 and ((c.iloc[idx] - o.iloc[idx]) / o.iloc[idx]) >= 0.001:
        stage_survivors["stage11"] += 1
    else:
        sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "positive_01_pass", "ppp_label": ppp_label, "date": data_date}
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
        sheet1 = connect_spreadsheet("シート1")
        stage_map = {
            "trend_align": "7. 長トレンド",
            "upper_shadow": "8. 上ヒゲ",
            "ceiling_avoid": "9. 天井圏回避 現在スキップ",
            "new_high_pass": "10. 新高値",
            "positive_01_pass": "11. 0.1%以上陽線",
            "completed_pass": "11. 0.1%以上陽線"
        }
        new_rows_s1 = [[r["date"], code, stage_map[r["stage_key"]], r["ppp_label"].strip() or "通常", r["price"], "", "判定待ち", ""] for code, r in sheet1_final_log.items() if r["stage_key"] in stage_map]
        if new_rows_s1: 
            sheet1.append_rows(new_rows_s1, value_input_option='RAW')
            print(f"シート1に当日のスキャン結果を {len(new_rows_s1)} 件（判定待ち）追記しました。")
    except Exception as e:
        print(f"シート1への追記エラー: {e}")

    try:
        if selected_stocks:
            sheet2 = connect_spreadsheet("シート2")
            new_rows_s2 = []
            for code, r in selected_stocks.items():
                row1 = ["翌日終値"] + [f"{d}営業日" for d in range(3, 16)] + ["差額(対選定)", "判定(対選定)", "比率(%)"] + [r["date"], code, r["price"]]
                row2 = ["判定"] * 14 + ["", "", ""] + ["通過条件ステージ", "11. 0.1%以上陽線", ""]
                row3 = ["前日比(%)"] * 14 + ["", "", ""] + ["PPP", r["ppp_label"].strip() or "通常", ""]
                row4 = [""]
                
                new_rows_s2.extend([row1, row2, row3, row4])
            
            if new_rows_s2:
                sheet2.append_rows(new_rows_s2, value_input_option='RAW')
                print(f"シート2に完全合格銘柄を {len(selected_stocks)} 件追記しました。")
    except Exception as e:
        print(f"シート2への追記エラー: {e}")

# --- メイン処理 ---
def main():
    fetch_global_latest_date()
    
    # 1. 過去データの自動答え合わせ実行
    update_yesterday_results()
    update_sheet2_results()
    
    # 2. 当日の全銘柄スクリーニング
    start_r, end_r = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 10001)
    print(f"処理開始: {start_r}〜{end_r}")
    
    for s in [str(i) for i in range(start_r, end_r)]: 
        if 1300 <= int(s) <= 1600: continue  # ETF/REIT除外
        analyze_stock(s)
        
    # 3. スプレッドシートへ判定待ちデータを一括書き込み
    record_to_spreadsheet()
    
    # 4. レポートメールの組み立て
    final_list = [f"  {'★PPP ' in s['ppp_label'] and s['ppp_label'] or ''}■ {code} | {s['price']}円 ({s['date'][5:]})" for code, s in sorted(selected_stocks.items())]
    header = f"データ対象日(完全一致): {GLOBAL_LATEST_DATE}"
    
    survivors_block = (
        "【各ステージ生存数】\n"
        f"1.取得: {stage_survivors['stage1']}\n"
        f"2.月足60: {stage_survivors['stage2']}\n"
        f"3.出来高: {stage_survivors['stage3']}\n"
        f"4.下半身: {stage_survivors['stage4']}\n"
        f"5.溜め: {stage_survivors['stage5']}\n"
        f"6.右肩: {stage_survivors['stage6']}\n"
        f"7.長期T: {stage_survivors['stage7']}\n"
        f"8.上ヒゲ: {stage_survivors['stage8']}\n"
        f"9.天井回避: {stage_survivors['stage9']} (※スルー適用中)\n"
        f"10.新高値: {stage_survivors['stage10']}\n"
        f"11.0.1%以上陽線: {stage_survivors['stage11']}"
    )
    
    judgement_lines = ["【本日確定の判定結果】"]
    has_any_result = False
    stage_count_map = {
        "trend_align": stage_survivors['stage7'],
        "upper_shadow": stage_survivors['stage8'],
        "ceiling_avoid": stage_survivors['stage9'],
        "new_high_pass": stage_survivors['stage10'],
        "positive_01_pass": stage_survivors['stage11'],
        "completed_pass": len(final_list)
    }

    for key, lines in stage_results_report.items():
        if lines:
            has_any_result = True
            label = STAGE_LABELS.get(key, "不明なステージ")
            count = stage_count_map.get(key, 0)
            judgement_lines.append(f"{label}: {count}件中、前日クリアした銘柄の答え合わせ")
            judgement_lines.extend(lines)
            judgement_lines.append("")
            
    if not has_any_result:
        judgement_lines.append("  該当なし")
        
    judgement_block = "\n".join(judgement_lines).strip()
    final_list_str = "\n".join(final_list) if final_list else '  該当なし'

    condition_text = """

--------------------------------------------------
【条件一覧】
1. 全データ取得成功
2. 月足クリア >MA60
3. 出来高5万株クリア
4. 下半身クリア
5. 溜めクリア >MA5
6. 右肩上がり >MA60
7. 長期トレンド MA100>前日
8. 上ヒゲクリア
9. 天井圏回避 (★一時的スルー無効化中)
10. 新高値更新 >MA5
11. 0.1%以上陽線 ((終値 - 開始値) / 開始値 >= 0.1%)

【判定結果マーク基準】翌日終値
 ◎ ： +2.0%以上
 ◯ ： +0.1%〜+2.0%
 ▲ ： -0.1%〜+0.1%
 ✕ ： -0.1%未満"""

    body = (
        f"==================================================\n"
        f"{header}\n"
        f"総対象: {end_r-start_r}件\n\n"
        f"{survivors_block}\n\n"
        f"★PPP: {stats['★PPP']} / Short: {stats['★PPP(Short)']} / 通常: {stats['normal_detect']}\n\n"
        f"【完全合格一覧】\n"
        f"{final_list_str}\n\n"
        f"==================================================\n"
        f"{judgement_block}"
        f"{condition_text}"
    )
    
    # 5. メール送信
    try:
        msg = MIMEMultipart()
        msg['From'], msg['To'], msg['Subject'] = SENDER_EMAIL, SENDER_EMAIL, f"📊 adoGEM レポート {len(final_list)}件"
        msg.attach(MIMEText(body, 'plain'))
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("検証レポートメールを正常に送信しました。")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__": 
    main()
