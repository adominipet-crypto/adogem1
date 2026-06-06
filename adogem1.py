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

# 全てが連番・ステップ式の合格カウンタ（ステージ9・10を末尾に拡張）
stats = {
    "stage0_fetched": 0,      # 0. 全データ取得成功
    "stage0.5_higher_ma": 0,  # 0.5 上位足(月足)トレンドクリア
    "stage1_volume": 0,       # 1. 出来高クリア
    "stage2_kahanshin": 0,    # 2. 下半身クリア
    "stage3_tame": 0,         # 3. 溜めクリア
    "stage4_ma60": 0,         # 4. 60日線クリア
    "stage5_trend": 0,        # 5. 長トレンドクリア
    "stage6_upper": 0,        # 6. 上ヒゲクリア
    "stage7_ceiling": 0,      # 7. 天井圏回避クリア
    "stage8_new_high": 0,     # 8. 新高値更新(規定合格)
    "stage9_weekly_ma": 0,    # 9. 【追加】週足トレンド(26週線超え)クリア
    "stage10_monthly_high": 0,# 10.【追加】長期天井圏維持(2年最高値から-20%以内)クリア
    "★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0
}

# 重複を排除し、1銘柄につき最終判定のみを保持する辞書
sheet1_final_log = {}
# 条件8以降（9、10を含む）をすべて完全クリアした最終規定合格銘柄のみを保持する辞書（シート2用）
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
    backoff_factor = 3  
    
    for attempt in range(1, max_retries + 1):
        try:
            client = gspread.authorize(creds)
            return client.open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)
        except APIError as e:
            if e.response.status_code in [500, 502, 503, 504, 429] and attempt < max_retries:
                sleep_time = attempt * backoff_factor
                print(f"【⚠️Google APIエラー {e.response.status_code}】サーバーが一時的に不安定です。")
                print(f"  --> {sleep_time}秒後に自動再試行します（試行 {attempt}/{max_retries}）")
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
        print("【システム】エラーメールを送信しました。")
    except Exception as e:
        print(f"エラーメール送信失敗: {e}")

def get_stock_data_fallback(symbol):
    """ 【自立型・照合検証プロセス】
        取得データの最終日付が本日(実行日)の東証データと完全一致しているか、
        データに不自然な暫定値（PTSノイズ等）が含まれていないかを二重に照合・補正します。
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=2y&interval=1d"
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
        
        # ──【照合チェック1: 日付の厳格一致】──
        last_data_date_str = df.index[-1].strftime("%Y-%m-%d")
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        
        if last_data_date_str != today_str:
            return None
            
        # ──【照合チェック2: PTS等の暫定ノイズ排除】──
        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]
        if last_row['Close'] == prev_row['Close'] and last_row['High'] == prev_row['High'] and last_row['Volume'] < 100:
            df = df.iloc[:-1]
            
        return df
    except:
        return None

def record_to_spreadsheet():
    """ 🌟 シート1へ記録：最高到達ステージ名を割り当てて記録 """
    try:
        sheet = connect_spreadsheet("シート1")
        new_rows = []
        
        for code, row_data in sheet1_final_log.items():
            price = row_data["price"]
            stage_key = row_data["stage_key"]
            ppp_status = row_data["ppp_label"].strip() if row_data["ppp_label"].strip() else "通常"
            data_date = row_data["date"]  
            
            stage_names = {
                "ma60_up": "4. 60日線右肩上がり", 
                "trend_align": "5. 長期トレンド同期",
                "upper_shadow": "6. 上ヒゲ選別", 
                "ceiling_avoid": "7. 天井圏回避(最終)",
                "new_high_pass": "8. 新高値更新(規定合格)",
                "weekly_ma_pass": "9. 週足トレンド合格",
                "monthly_high_pass": "10. 天井圏維持(完全合格)"
            }
            stage_name = stage_names.get(stage_key, stage_key)
            new_rows.append([data_date, code, stage_name, ppp_status, price, "", "判定待ち", ""])
            
        if new_rows:
            new_rows.sort(key=lambda x: x[1])
            sheet.append_rows(new_rows, value_input_option='RAW')
            print(f"【シート1記録】個別ログを計 {len(new_rows)} 件追記しました。")
    except Exception as e:
        print(f"シート1記録エラー: {e}")
        raise e

def record_to_sheet2():
    """ 🌟 シート2へ記録：条件8以降（9、10すべて）を完全クリアした銘柄を追記 """
    if not selected_stocks:
        print("【シート2記録】本日すべての規定条件を満たした銘柄がないため、書き込みをスキップします。")
        return

    try:
        sheet2 = connect_spreadsheet("シート2")
        row_height = 4 
        
        cells_a = sheet2.findall(pd.compile(r'.+'), in_column=1)
        if cells_a:
            last_filled_row = max(cell.row for cell in cells_a)
            start_row = ((last_filled_row // row_height) * row_height) + 1
            if start_row <= last_filled_row:
                start_row += row_height
        else:
            start_row = 1

        cell_updates = []
        sorted_codes = sorted(selected_stocks.keys())
        
        for idx, code in enumerate(sorted_codes):
            r = start_row + (idx * row_height)
            data = selected_stocks[code]
            
            price = data["price"]
            ppp_status = data["ppp_label"].strip() if data["ppp_label"].strip() else "通常"
            data_date = data["date"]  
            
            # --- 1行目（上段） ---
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

            # --- 2行目（中段）通過条件を「8. 新高値更新以降クリア」として表記 ---
            cell_updates.append(gspread.Cell(r + 1, 1, "通過条件ステージ")) 
            cell_updates.append(gspread.Cell(r + 1, 2, "8. 新高値更新以降"))    
            cell_updates.append(gspread.Cell(r + 1, 4, ""))                 
            cell_updates.append(gspread.Cell(r + 1, 5, "判定待ち"))         

            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r + 1, 3 + day, "判定"))

            cell_updates.append(gspread.Cell(r + 1, 19, "差額枠"))
            cell_updates.append(gspread.Cell(r + 1, 20, "判定枠"))
            cell_updates.append(gspread.Cell(r + 1, 21, "比率枠"))

            # --- 3行目（下段） ---
            cell_updates.append(gspread.Cell(r + 2, 1, "PPP"))              
            cell_updates.append(gspread.Cell(r + 2, 2, ppp_status))         
            cell_updates.append(gspread.Cell(r + 2, 5, "前日比(%)"))        
            
            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r + 2, 3 + day, "前日比(%)"))

            # --- 4行目（空白セパレーター） ---
            cell_updates.append(gspread.Cell(r + 3, 1, ""))
            cell_updates.append(gspread.Cell(r + 3, 2, ""))

        if cell_updates:
            sheet2.update_cells(cell_updates, value_input_option='RAW')
            print(f"【シート2記録】完全規定合格 {len(sorted_codes)} 件をシート2に追記しました。")
            
    except Exception as e:
        print(f"シート2記録エラー: {e}")
        raise e

def update_yesterday_results():
    """ 翌営業日の答え合わせロジック（厳格照合フィルタ付き） """
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
                mark = "◎" if pct >= 2.0 else "◯" if pct > 0.1 else "▲" if pct >= -0.1 else "✕"
                
                cell_list.append(gspread.Cell(i + 1, 6, next_close))
                cell_list.append(gspread.Cell(i + 1, 7, mark))
                cell_list.append(gspread.Cell(i + 1, 8, f"{pct:+.2f}%"))
                print(f"【答え合わせ完了】シート1 {code}: {mark} ({pct:+.2f}%)")
        
        if cell_list:
            sheet.update_cells(cell_list)
            print(f"【システム】シート1の合計 {len(cell_list)//3} 件を一括更新しました。")
    except Exception as e:
        print(f"自動答え合わせエラー: {e}")
        raise e

def analyze_stock(symbol):
    """ 各銘柄のテクニカル分析およびステップ式ステージ絞り込み """
    try:
        df = get_stock_data_fallback(symbol)
        if df is None: return "SKIP"
        
        stats["stage0_fetched"] += 1

        # ───【ステージ0.5 上位足(月足)トレンドフィルター】───
        monthly_close = df['Close'].resample('ME').last()
        if len(monthly_close) >= 12:
            monthly_ma12 = monthly_close.rolling(12).mean()
            if monthly_close.iloc[-1] < monthly_ma12.iloc[-1]:
                return "SKIP"
        stats["stage0.5_higher_ma"] += 1

        if df['Volume'].iloc[-1] < 50000: return "SKIP"
        stats["stage1_volume"] += 1

        # 実際のデータ確定日付（文字列）を取得
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

        if not (ma5_t < close) or close <= open_p: return "SKIP" 
        stats["stage2_kahanshin"] += 1
        
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["stage3_tame"] += 1

        if ma60_t <= yest['MA60']: return "SKIP" 
        stats["stage4_ma60"] += 1
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "ma60_up", "ppp_label": ppp_label, "date": data_date}

        if ma100_t <= yest['MA100']: return "SKIP"
        stats["stage5_trend"] += 1
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "trend_align", "ppp_label": ppp_label, "date": data_date}

        if (high - close) >= ((close - open_p) * 1.5): return "SKIP"
        stats["stage6_upper"] += 1
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "upper_shadow", "ppp_label": ppp_label, "date": data_date}
        
        if close >= (df['High'].iloc[-100:].max() * 0.97): return "SKIP"
        stats["stage7_ceiling"] += 1
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "ceiling_avoid", "ppp_label": ppp_label, "date": data_date}

        if close < df['High'].iloc[-6:-1].max(): return "SKIP"
        stats["stage8_new_high"] += 1
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "new_high_pass", "ppp_label": ppp_label, "date": data_date}

        # ───【🌟ステージ9：週足トレンドフィルター (追加)】───
        weekly_close = df['Close'].resample('W').last()
        if len(weekly_close) >= 26:
            weekly_ma26 = weekly_close.rolling(26).mean()
            # 週足終値が26週移動平均線を割り込んでいる（下落トレンド、天井割れ）なら除外
            if weekly_close.iloc[-1] < weekly_ma26.iloc[-1]:
                return "SKIP"
        stats["stage9_weekly_ma"] += 1
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "weekly_ma_pass", "ppp_label": ppp_label, "date": data_date}

        # ───【🌟ステージ10：天井圏維持フィルター（2年最高値から-20%以内） (追加)】───
        # 過去24ヶ月（2年間）の月足最高値を算出
        if len(monthly_close) >= 1:
            max_period = min(len(monthly_close), 24)
            monthly_high_24m = df['High'].resample('ME').max().iloc[-max_period:].max()
            # 2年最高値から20%以上下に沈んでいる（天井圏を完全に割り込んで崩れている）場合は除外
            if close < (monthly_high_24m * 0.80):
                return "SKIP"
        stats["stage10_monthly_high"] += 1
        sheet1_final_log[symbol] = {"price": int(close), "stage_key": "monthly_high_pass", "ppp_label": ppp_label, "date": data_date}

        # 🌟 条件8、9、10をすべて完全クリアした合格銘柄のみをシート2用辞書に格納
        selected_stocks[symbol] = {
            "price": int(close), 
            "ppp_label": ppp_label,
            "date": data_date  
        }

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
        
        # スプレッドシートへの永続化
        record_to_spreadsheet() # シート1 
        record_to_sheet2()      # シート2 (条件8〜10を完全クリアした銘柄を掲載)
        
        # メール配信用詳細テキスト
        stages_output = {
            "ma60_up": [], "trend_align": [], "upper_shadow": [], 
            "ceiling_avoid": [], "new_high_pass": [], "weekly_ma_pass": [], "monthly_high_pass": []
        }
        for code, row_data in sheet1_final_log.items():
            k = row_data["stage_key"]
            ppp = row_data["ppp_label"]
            item_str = f"  ■ {code} | {row_data['price']}円" if not ppp else f"  {ppp}■ {code} | {row_data['price']}円"
            stages_output[k].append(item_str)

        # メール本文の組み立て
        body = f"総対象: {len(symbols)}件\n\n" \
               f"【各ステージで留まった(合格)件数】\n" \
               f"0. 全データ取得成功: {stats['stage0_fetched']}件\n" \
               f"0.5 上位足トレンドクリア: {stats['stage0.5_higher_ma']}件\n" \
               f"1. 出来高クリア: {stats['stage1_volume']}件\n" \
               f"2. 下半身クリア: {stats['stage2_kahanshin']}件\n" \
               f"3. 溜めクリア: {stats['stage3_tame']}件\n" \
               f"4. 60日線クリア: {stats['stage4_ma60']}件\n" \
               f"5. 長トレンドクリア: {stats['stage5_trend']}件\n" \
               f"6. 上ヒゲクリア: {stats['stage6_upper']}件\n" \
               f"7. 天井圏回避クリア: {stats['stage7_ceiling']}件\n" \
               f"8. 新高値更新(規定合格): {stats['stage8_new_high']}件\n" \
               f"9. 週足トレンドクリア: {stats['stage9_weekly_ma']}件\n" \
               f"10.天井圏維持(完全合格): {stats['stage10_monthly_high']}件\n\n" \
               f"★PPP: {stats['★PPP']} / ★Short: {stats['★PPP(Short)']} / 通常: {stats['normal_detect']}\n\n" \
               f"【詳細（各銘柄の最終判定ステージ）】\n" \
               f"8.新高値更新で留まった銘柄:\n" + "\n".join(stages_output["new_high_pass"]) + "\n\n" \
               f"9.週足トレンドクリアで留まった銘柄:\n" + "\n".join(stages_output["weekly_ma_pass"]) + "\n\n" \
               f"10.天井圏維持(完全確定合格)の銘柄:\n" + "\n".join(stages_output["monthly_high_pass"])

        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"📊 adoGEM レポート ({start_range}-{end_range}) 完全合格:{stats['stage10_monthly_high']}件"
        msg.attach(MIMEText(body, 'plain'))
        
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("スキャンおよびレポートメール送信完了")
        
    except Exception as e:
        send_error_email(traceback.format_exc(), start_range, end_range)
        sys.exit(1)

if __name__ == "__main__":
    main()
