import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

stats = {
    "total_fetched": 0, "pass_delay": 0, "pass_volume": 0, "pass_kahanshin": 0, "pass_tame": 0,
    "pass_ma60_up": 0, "pass_trend_align": 0, "pass_upper_shadow": 0, "pass_new_high": 0, "pass_ceiling_avoid": 0,
    "★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0
}

highest_stages = {}
selected_stocks = {}

def connect_spreadsheet(sheet_name="シート1"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)

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

def record_to_spreadsheet():
    """ 🌟 [完全維持] シート1へ、これまで通り途中で脱落したステージも含めて個別選別を記録する """
    try:
        sheet = connect_spreadsheet("シート1")
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        new_rows = []
        for code, data in highest_stages.items():
            price = data["price"]
            stage_key = data["stage_key"]
            ppp_status = data["ppp_label"].strip() if data["ppp_label"].strip() else "通常"
            
            stage_names = {
                "ma60_up": "4. 60日線右肩上がり", "trend_align": "5. 長期トレンド同期",
                "upper_shadow": "6. 上ヒゲ選別", "ceiling_avoid": "7. 天井圏回避(最終)"
            }
            stage_name = stage_names.get(stage_key, stage_key)
            new_rows.append([today_str, code, stage_name, ppp_status, price, "", "判定待ち", ""])
        if new_rows:
            new_rows.sort(key=lambda x: x[1])
            sheet.append_rows(new_rows, value_input_option='RAW')
            print(f"【シート1記録】従来通り {len(new_rows)} 件の個別ログを追記しました。")
    except Exception as e:
        print(f"シート1記録エラー: {e}")
        raise e

def record_to_sheet2():
    """ 🌟 [画像完全同期修正] 画像3枚目のレイアウト通りに、シート2へ最終合格を縦下方向（4行区切り）に追加 """
    if not selected_stocks:
        print("【シート2記録】本日「7. 天井圏回避(最終)」に合格した銘柄がないため、書き込みをスキップします。")
        return

    try:
        sheet2 = connect_spreadsheet("シート2")
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        
        row_height = 4 
        a_values = sheet2.col_values(1)
        start_row = 1
        
        if a_values:
            current_len = len(a_values)
            start_row = ((current_len // row_height) * row_height) + 1
            if start_row <= current_len:
                start_row += row_height

        cell_updates = []
        sorted_codes = sorted(selected_stocks.keys())
        
        for idx, code in enumerate(sorted_codes):
            r = start_row + (idx * row_height)
            data = selected_stocks[code]
            
            price = data["price"]
            stage_name = data["stage_name"]
            ppp_status = data["ppp_label"].strip() if data["ppp_label"].strip() else "通常"
            
            # --- 1行目（上段）ご指定配置 ---
            cell_updates.append(gspread.Cell(r, 1, today_str))            # A1: 日付データ値
            cell_updates.append(gspread.Cell(r, 2, code))                 # B1: 銘柄コード
            cell_updates.append(gspread.Cell(r, 3, price))                # C1: 選定時終値
            cell_updates.append(gspread.Cell(r, 4, ""))                   # D1: 空き
            cell_updates.append(gspread.Cell(r, 5, "翌日終値"))           # E1: 翌日終値（固定文字）
            
            # F1(6列目)〜R1(18列目)まで3〜15営業日の見出しをセット
            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r, 3 + day, f"{day}営業日")) # F1は3+3=6列目
                
            # 15営業日の次の3列（S, T, U列）にC1との関係値をセットする見出し
            cell_updates.append(gspread.Cell(r, 19, "差額(対選定)"))       # S1
            cell_updates.append(gspread.Cell(r, 20, "判定(対選定)"))       # T1
            cell_updates.append(gspread.Cell(r, 21, "比率(%)"))            # U1

            # --- 2行目（中段）ご指定配置 ---
            cell_updates.append(gspread.Cell(r + 1, 1, "通過条件ステージ")) # A2: 通過条件ステージ
            cell_updates.append(gspread.Cell(r + 1, 2, stage_name))         # B2: PPP (※画像準拠でここにPPP状態、A2隣接へ実際の文字)
            cell_updates.append(gspread.Cell(r + 1, 2, ppp_status))         # 画像の位置に固定
            cell_updates.append(gspread.Cell(r + 1, 1, "通過条件ステージ")) # 表記ズレ補正用固定名
            cell_updates.append(gspread.Cell(r + 1, 2, ppp_status))         # B2の位置にPPP
            # A2に「通過条件ステージ」の文字が入るため、実際の値は隣または適切な枠に調整。画像に合わせA2, B2テキスト配置
            cell_updates.append(gspread.Cell(r + 1, 1, "通過条件ステージ"))
            cell_updates.append(gspread.Cell(r + 1, 2, ppp_status))
            # 通過条件ステージ文字はそのままA2、B2にPPP文字を上書き
            cell_updates.append(gspread.Cell(r + 1, 4, ""))                 # D2: 空き
            cell_updates.append(gspread.Cell(r + 1, 5, "判定待ち"))         # E2: 判定（初期値）

            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r + 1, 3 + day, "判定"))   # F2〜R2に判定の初期枠

            cell_updates.append(gspread.Cell(r + 1, 19, "差額枠"))
            cell_updates.append(gspread.Cell(r + 1, 20, "判定枠"))
            cell_updates.append(gspread.Cell(r + 1, 21, "比率枠"))

            # --- 3行目（下段）ご指定配置 ---
            cell_updates.append(gspread.Cell(r + 2, 1, "PPP"))              # A3: PPP（固定見出し文字に補正）
            cell_updates.append(gspread.Cell(r + 2, 5, "前日比(%)"))        # E3: 前日比(%)
            
            for day in range(3, 16):
                cell_updates.append(gspread.Cell(r + 2, 3 + day, "前日比(%)")) # F3〜R3

            # --- 4行目（空白）完全なセパレーター行にリセット ---
            cell_updates.append(gspread.Cell(r + 3, 1, ""))
            cell_updates.append(gspread.Cell(r + 3, 2, ""))

        if cell_updates:
            sheet2.update_cells(cell_updates, value_input_option='RAW')
            print(f"【シート2記録】最終合格 {len(sorted_codes)} 件を画像モックと同一レイアウトで追記しました（行 {start_row} 〜）。")
            
    except Exception as e:
        print(f"シート2記録エラー: {e}")
        raise e

def get_stock_data_fallback(symbol):
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
        return df.sort_index()
    except:
        return None

def update_yesterday_results():
    """ 🌟 [完全現状維持] シート1の自動答え合わせロジック（一切触っていません） """
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
    try:
        df = get_stock_data_fallback(symbol)
        if df is None or df.empty or len(df) < 100: return "SKIP"
        
        last_data_date = df.index[-1].date()
        today_date = datetime.date.today()
        if (today_date - last_data_date).days > (3 if today_date.weekday() in [5, 6] else 1):
            stats["pass_delay"] += 1
            return "SKIP"

        if df['Volume'].iloc[-1] < 50000: return "SKIP"
        stats["pass_volume"] += 1

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

        # 各ステージ判定と、シート1用へのデータ登録
        if not (ma5_t < close) or close <= open_p: return "SKIP" 
        stats["pass_kahanshin"] += 1
        
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["pass_tame"] += 1

        if ma60_t <= yest['MA60']: return "SKIP" 
        stats["pass_ma60_up"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "ma60_up", "ppp_label": ppp_label}

        if ma100_t <= yest['MA100']: return "SKIP"
        stats["pass_trend_align"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "trend_align", "ppp_label": ppp_label}

        if (high - close) >= ((close - open_p) * 1.5): return "SKIP"
        stats["pass_upper_shadow"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "upper_shadow", "ppp_label": ppp_label}

        if close >= df['High'].iloc[-6:-1].max(): stats["pass_new_high"] += 1
        
        if close >= (df['High'].iloc[-100:].max() * 0.97): return "SKIP"
        stats["pass_ceiling_avoid"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "ceiling_avoid", "ppp_label": ppp_label}

        # 7を完全クリアしたエリート銘柄のみをシート2用として抽出
        selected_stocks[symbol] = {
            "price": int(close), 
            "stage_name": "7. 天井圏回避(最終)", 
            "ppp_label": ppp_label
        }

        if "★PPP " in ppp_label: stats["★PPP"] += 1
        elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
        else: stats["normal_detect"] += 1
        return f"{ppp_label}{stock_text}"
    except: return "ERROR"

def get_target_symbols(start, end):
    return [str(i) for i in range(start, end)]

def main():
    start_range, end_range = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 10001)
    try:
        if start_range == 1300:
            update_yesterday_results()
            time.sleep(2)
        symbols = get_target_symbols(start_range, end_range)
        for symbol in symbols: analyze_stock(symbol)
        
        # 🌟 分離された2つの関数を実行
        record_to_spreadsheet() # シート1は元のまま個別保存
        record_to_sheet2()      # シート2は画像通りの完全横長フォーマットで積み上げ
        
        stages_output = {"ma60_up": [], "trend_align": [], "upper_shadow": [], "ceiling_avoid": []}
        for code, data in highest_stages.items():
            k = data["stage_key"]
            ppp = data["ppp_label"]
            stages_output[k].append(f"  ■ {code} | {data['price']}円" if not ppp else f"  {ppp}■ {code} | {data['price']}円")

        body = f"総対象: {len(symbols)}\n\n" \
               f"0.データ遅延: {stats['pass_delay']}件\n" \
               f"1.出来高: {stats['pass_volume']}\n2.下半身: {stats['pass_kahanshin']}\n3.溜め: {stats['pass_tame']}\n" \
               f"4.60日線: {stats['pass_ma60_up']}\n5.長トレンド: {stats['pass_trend_align']}\n6.上ヒゲ: {stats['pass_upper_shadow']}\n" \
               f"5.新高値: {stats['pass_new_high']}\n7.天井圏回避: {stats['pass_ceiling_avoid']}\n\n" \
               f"★PPP: {stats['★PPP']} / ★Short: {stats['★PPP(Short)']} / 通常: {stats['normal_detect']}\n\n" \
               f"【詳細】\n" \
               f"4.60日:\n" + "\n".join(stages_output["ma60_up"]) + "\n\n" \
               f"5.長トレンド:\n" + "\n".join(stages_output["trend_align"]) + "\n\n" \
               f"6.上ヒゲ:\n" + "\n".join(stages_output["upper_shadow"]) + "\n\n" \
               f"7.天井回避:\n" + "\n".join(stages_output["ceiling_avoid"])

        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"📊 adoGEM レポート ({start_range}-{end_range})"
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
