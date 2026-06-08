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
        
        # 時差や週末（土日・月曜早朝）を考慮し、10日前までのデータであれば有効データとして受け入れる（厳しすぎる条件を緩和）
        if (last_data_date > today and (last_data_date - today).days > 1) or (today - last_data_date).days > 10:
            return None
            
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        
        # 当日のリアルタイム暫定データ（出来高が極小で株価が変化していないプレマーケット等）のみを除外する
        if last_data_date == today and last_row['Volume'] < 100:
            if last_row['Close'] == prev_row['Close'] and last_row['High'] == prev_row['High']:
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
            rows_count = len(new_rows)
            print(f"【シート1記録】確定ステージが7以上の個別ログを計 {rows_count} 件追記しました。")
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
            stocks_count = len(sorted_codes)
            print(f"【シート2記録】完全規定合格(ステージ12) {stocks_count} 件をシート2に追記しました。")
            time.sleep(3)
            
    except Exception as e:
        print(f"シート2記録エラー: {e}")
        raise e

def update_yesterday_results():
    try:
        sheet = connect_spreadsheet("シート1")
        all_records = sheet.get_all_values()
        cell_list = []
        
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 8 or row[6] != "判定待ち": continue
            code = row[1]
            
            try:
                selected_price = int(row[4])
            except ValueError:
                continue
                
            df = get_stock_data_fallback(code)
            
            if df is not None and len(df) >= 1:
                next_close = int(df['Close'].iloc[-1])
                if next_close == selected_price and len(df) >= 2:
                    next_close = int(df['Close'].iloc[-2])
                pct = ((next_close - selected_price) / selected_price) * 100
                
                if pct >= 2.0:
                    mark = "◎"
                elif pct >= 0.1:
                    mark = "◯"
                elif pct > -0.1:
                    mark = "▲"
                else:
                    mark = "✕"
                
                cell_list.append(gspread.Cell(i + 1, 6, next_close))
                cell_list.append(gspread.Cell(i + 1, 7, mark))
                cell_list.append(gspread.Cell(i + 1, 8, f"{pct:+.2f}%"))
                print(f"【答え合わせ完了】シート1 {code}: {mark} ({pct:+.2f}%)")
                
                time.sleep(0.5)
        
        if cell_list:
            sheet.update_cells(cell_list)
            update_count = len(cell_list) // 3
            print(f"【システム】シート1の合計 {update_count} 件を一括更新しました。")
            time.sleep(5)
    except Exception as e:
        print(f"自動答え合わせエラー: {e}")
        raise e

def analyze_stock(symbol):
    try:
        # ───【1. 全データ取得成功】───
        stage_survivors["stage1"] += 1
        df = get_stock_data_fallback(symbol)
        if df is None: return "SKIP"
        
        # ───【2. 月足MA60クリア】───
        stage_survivors["stage2"] += 1
        monthly_close = df['Close'].resample('ME').last()
        if len(monthly_close) >= 60:
            monthly_ma60 = monthly_close.rolling(60).mean()
            if monthly_close.iloc[-1] < monthly_ma60.iloc[-1]: return "SKIP"

        # ───【3. 出来高5万株クリア】───
        stage_survivors["stage3"] += 1
        if df['Volume'].iloc[-1] < 50000: return "SKIP"

        data_date = df.index[-1].strftime("%Y-%m-%d")

        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['MA100'] = df['Close'].rolling(100).mean()
        df['MA300'] = df['Close'].rolling(300).mean() if len(df) >= 300 else None
        
        today, yest, yest2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        close, open_p, high, low = today['Close'], today['Open'], today['High'], today['Low']
        ma5_t, ma20_t, ma60_t, ma100_t, ma300_t = today['MA5'], today['MA20'], today['MA60'], today['MA100'], today['MA300']

        ppp_label = ""
        if ma300_t is not None and pd.notna(ma300_t) and (ma5_t > ma20_t > ma60_t > ma100_t > ma300_t): 
            ppp_label = "★PPP "
        elif (ma5_t > ma20_t > ma60_t > ma100_t): 
            ppp_label = "★PPP(Short) "
            
        stock_text = f"■ {symbol} | {int(close)}円"

        if day_range := high - low:
            body_size = abs(close - open_p)
            if (body_size / day_range) < 0.05:
                high_box, low_box = max(close, open_p), min(close, open_p)
                if ((high - high_box) / day_range) >= 0.25 and ((low_box - low) / day_range) >= 0.25:
                    return "SKIP"

        # ───【4. 下半身クリア】───
        stage_survivors["stage4"] += 1
        if not (ma5_t < close) or close <= open_p: return "SKIP" 
        
        # ───【5. 溜めクリア】───
        stage_survivors["stage5"] += 1
        if yest['Close'] >= yest['MA5'] or yest2['Close'] >= yest2['MA5']: return "SKIP"

        # ───【6. 右肩上がり】───
        stage_survivors["stage6"] += 1
        if ma60_t <= yest['MA60']: return "SKIP" 

        # ───【7. 長トレンド】───
        stage_survivors["stage7"] += 1
        if ma100_t <= yest['MA100']: 
            sheet1_final_log[symbol] = {"price": int(close), "stage_key": "trend_align", "ppp_label": ppp_label, "date": data_date}
            return "SKIP"

        # ───【8. 上ヒゲクリア】───
        stage_survivors["stage8"] += 1
        if (high - close) >= ((close - open_p) * 1.5): 
            sheet1_final_log[symbol] = {"price": int(close), "stage_key": "upper_shadow", "ppp_label": ppp_label, "date": data_date}
            return "SKIP"
        
        # ───【9. 天井圏回避】───
        stage_survivors["stage9"] += 1
        if ma100_t <= close <= (ma100_t * 1.03): 
            sheet1_final_log[symbol] = {"price": int(close), "stage_key": "ceiling_avoid", "ppp_label": ppp_label, "date": data_date}
            return "SKIP"

        # ───【10. 新高値更新】───
        stage_survivors["stage10"] += 1
        highest_5d = df['High'].iloc[-6:-1].max() if len(df) >= 6 else df['High'].iloc[:-1].max()
        if close <= highest_5d: 
            sheet1_final_log[symbol] = {"price": int(close), "stage_key": "new_high_pass", "ppp_label": ppp_label, "date": data_date}
            return "SKIP"

        # ───【11：週足60クリア】───
        stage_survivors["stage11"] += 1
        weekly_close = df['Close'].resample('W').last()
        if len(weekly_close) >= 60:
            weekly_ma60 = weekly_close.rolling(60).mean()
            if weekly_close.iloc[-1] < weekly_ma60.iloc[-1]:
                sheet1_final_log[symbol] = {"price": int(close), "stage_key": "weekly_ma_pass", "ppp_label": ppp_label, "date": data_date}
                return "SKIP"

        # ───【12：天井圏維持（完全クリア合格）】───
        stage_survivors["stage12"] += 1
        if len(monthly_close) >= 24:
            monthly_ma24 = monthly_close.rolling(24).mean()
            if close < (monthly_ma24.iloc[-1] * 0.80):
                sheet1_final_log[symbol] = {"price": int(close), "stage_key": "monthly_high_pass", "ppp_label": ppp_label, "date": data_date}
                return "SKIP"

        # ───【すべての条件を完全突破（合格）】───
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "completed_pass", "ppp_label": ppp_label, "date": data_date}
        selected_stocks[symbol] = {"price": int(close), "ppp_label": ppp_label, "date": data_date}

        if "★PPP " in ppp_label: stats["★PPP"] += 1
        elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
        else: stats["normal_detect"] += 1
        return f"{ppp_label}{stock_text}"
    except:
        return "ERROR"

def get_target_symbols(start, end):
    return [str(i) for i in range(start, end)]

def main():
    start_range, end_range = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 10001)
    try:
        if start_range == 1300:
            update_yesterday_results()
            time.sleep(2)
            
        symbols = get_target_symbols(start_range, end_range)
        for symbol in symbols:
            analyze_stock(symbol)
        
        record_to_spreadsheet() 
        record_to_sheet2()      
        
        stages_output = {
            "trend_align": [], "upper_shadow": [], "ceiling_avoid": [], 
            "new_high_pass": [], "weekly_ma_pass": [], "monthly_high_pass": [], "completed_pass": []
        }
        for code, row_data in sheet1_final_log.items():
            k = row_data["stage_key"]
            if k not in stages_output: continue 
            ppp = row_data["ppp_label"]
            item_str = f"  ■ {code} | {row_data['price']}円" if not ppp else f"  {ppp}■ {code} | {row_data['price']}円"
            stages_output[k].append(item_str)

        final_passed_list = []
        for code in sorted(selected_stocks.keys()):
            ppp = selected_stocks[code]["ppp_label"]
            price = selected_stocks[code]["price"]
            item_str = f"  ■ {code} | {price}円" if not ppp else f"  {ppp}■ {code} | {price}円"
            final_passed_list.append(item_str)

        # メール本文の組み立て（生存数方式・1〜12全表示）
        total_len = len(symbols)
        s1 = stage_survivors['stage1']
        s2 = stage_survivors['stage2']
        s3 = stage_survivors['stage3']
        s4 = stage_survivors['stage4']
        s5 = stage_survivors['stage5']
        s6 = stage_survivors['stage6']
        s7 = stage_survivors['stage7']
        s8 = stage_survivors['stage8']
        s9 = stage_survivors['stage9']
        s10 = stage_survivors['stage10']
        s11 = stage_survivors['stage11']
        s12 = len(final_passed_list)

        body = f"総対象: {total_len}件\n\n" \
               f"【各ステージの生存（クリア）件数】\n" \
               f"1. 全データ取得: {s1}件\n" \
               f"2. 月足MA60クリア: {s2}件\n" \
               f"3. 出来高5万株クリア: {s3}件\n" \
               f"4. 下半身クリア: {s4}件\n" \
               f"5. 溜めクリア: {s5}件\n" \
               f"6. 右肩上がりクリア: {s6}件\n" \
               f"7. 長期トレンドクリア: {s7}件\n" \
               f"8. 上ヒゲクリア: {s8}件\n" \
               f"9. 天井圏回避クリア: {s9}件\n" \
               f"10. 新高値更新クリア: {s10}件\n" \
               f"11. 週足60クリア: {s11}件\n" \
               f"12. 天井圏維持(完全合格): {s12}件\n\n" \
               f"★PPP: {stats['★PPP']} / ★Short: {stats['★PPP(Short)']} / 通常: {stats['normal_detect']}\n\n" \
               f"【詳細（各銘柄の最終判定ステージ）】\n"
               
        body += f"7. 長期トレンド:\n" + "\n".join(stages_output["trend_align"]) + "\n\n" \
                f"8. 上ヒゲクリア:\n" + "\n".join(stages_output["upper_shadow"]) + "\n\n" \
                f"9. 天井圏回避:\n" + "\n".join(stages_output["ceiling_avoid"]) + "\n\n" \
                f"10. 新高値更新:\n" + "\n".join(stages_output["new_high_pass"]) + "\n\n" \
                f"11. 週足60クリア:\n" + "\n".join(stages_output["weekly_ma_pass"]) + "\n\n" \
                f"12. 天井圏維持(完全合格):\n" + "\n".join(final_passed_list) + "\n\n" \
                f"--------------------------------------------------\n" \
                f"【条件一覧】\n" \
                f"1. 全データ取得成功\n" \
                f"2. 月足MA60クリア\n" \
                f"3. 出来高5万株クリア\n" \
                f"4. 下半身クリア\n" \
                f"5. 溜めMA5クリア（MA5以上削除）\n" \
                f"6. 右肩上がり（MA60以下削除）\n" \
                f"7. 長期トレンド（MA100が前日より上昇）\n" \
                f"8. 上ヒゲクリア（上ヒゲが実態の1.5以上削除）\n" \
                f"9. 天井圏MA100回避（MA100の3％以内削除）\n" \
                f"10. 新高値MA5更新\n" \
                f"11. 週足MA60クリア\n" \
                f"12. 天井圏維持（月足MA24の20%以上削除）\n" \
                f"--------------------------------------------------\n" \
                f"【判定結果マーク基準】翌日終値\n" \
                f" ◎ ： +2.0%以上\n" \
                f" ◯ ： +0.1%〜+2.0%\n" \
                f" ▲ ： -0.1%〜+0.1%\n" \
                f" ✕ ： -0.1%未満\n" \
                f"--------------------------------------------------"

        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"📊 adoGEM レポート ({start_range}-{end_range}) 完全合格:{s12}件"
        m
