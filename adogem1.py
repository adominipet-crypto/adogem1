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

def connect_spreadsheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet("シート1")

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
    try:
        sheet = connect_spreadsheet()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        new_rows = []
        for code, data in highest_stages.items():
            if data["stage_key"] == "tame":
                continue
                
            price = data["price"]
            stage_name = data["stage_name"]
            ppp_status = data["ppp_label"].strip() if data["ppp_label"].strip() else "通常"
            
            new_rows.append([today_str, code, stage_name, ppp_status, price, "", "判定待ち", ""])
        if new_rows:
            new_rows.sort(key=lambda x: x[1])
            sheet.append_rows(new_rows, value_input_option='RAW')
            print(f"【シート記録】{len(new_rows)} 件を追記しました。")
    except Exception as e:
        print(f"シート記録エラー: {e}")
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
    try:
        sheet = connect_spreadsheet()
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
                print(f"【答え合わせ完了】{code}: {mark} ({pct:+.2f}%)")
        
        if cell_list:
            sheet.update_cells(cell_list)
            print(f"【システム】合計 {len(cell_list)//3} 件を一括更新しました。")
    except Exception as e:
        print(f"自動答え合わせエラー: {e}")
        raise e

def analyze_stock(symbol):
    try:
        df = get_stock_data_fallback(symbol)
        if df is None or df.empty or len(df) < 100: return "SKIP"
        
        # データ遅延対策ガード
        last_data_date = df.index[-1].date()
        today_date = datetime.date.today()
        if (today_date - last_data_date).days > (3 if today_date.weekday() in [5, 6] else 1):
            stats["pass_delay"] += 1  # 🌟 遅延ガードに引っかかった件数をカウント
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

        # 精密な十字線（迷いのクロス）限定の回避ロジック
        day_range = high - low
        if day_range > 0:
            body_size = abs(close - open_p)
            if (body_size / day_range) < 0.05:
                high_box = max(close, open_p)
                low_box = min(close, open_p)
                upper_shadow = high - high_box
                lower_shadow = low_box - low
                
                if (upper_shadow / day_range) >= 0.25 and (lower_shadow / day_range) >= 0.25:
                    return "SKIP"

        if not (ma5_t < close) or close <= open_p: return "SKIP" 
        stats["pass_kahanshin"] += 1
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["pass_tame"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "tame", "text": f"  3 {ppp_label}{stock_text}", "stage_name": "3. 溜め", "ppp_label": ppp_label}

        if ma60_t <= yest['MA60']: return "SKIP" 
        stats["pass_ma60_up"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "ma60_up", "text": f"  4 {ppp_label}{stock_text}", "stage_name": "4. 60日線右肩上がり", "ppp_label": ppp_label}

        if ma100_t <= yest['MA100']: return "SKIP"
        stats["pass_trend_align"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "trend_align", "text": f"  長 {ppp_label}{stock_text}", "stage_name": "5. 長期トレンド同期", "ppp_label": ppp_label}

        if (high - close) >= ((close - open_p) * 1.5): return "SKIP"
        stats["pass_upper_shadow"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "upper_shadow", "text": f"  ヒ {ppp_label}{stock_text}", "stage_name": "6. 上ヒゲ選別", "ppp_label": ppp_label}

        if close >= df['High'].iloc[-6:-1].max(): stats["pass_new_high"] += 1
        if close >= (df['High'].iloc[-100:].max() * 0.97): return "SKIP"
        stats["pass_ceiling_avoid"] += 1
        highest_stages[symbol] = {"price": int(close), "stage_key": "ceiling_avoid", "text": f"  最終 {ppp_label}{stock_text}", "stage_name": "7. 天井圏回避(最終)", "ppp_label": ppp_label}

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
        record_to_spreadsheet()
        
        mail_lists = {"tame": [], "ma60_up": [], "trend_align": [], "upper_shadow": [], "ceiling_avoid": []}
        for code, data in highest_stages.items():
            key = data["stage_key"]
            if key in mail_lists: mail_lists[key].append(data["text"])

        def list_str(lst): return "\n".join(lst) + "\n\n" if lst else "(該当なし)\n\n"
        
        valid_count = sum(1 for d in highest_stages.values() if d["stage_key"] != "tame")

        # 🌟 「0.データ遅延」の項目をレポート本文に追加
        body = f"総対象: {len(symbols)}\n\n" \
               f"0.データ遅延: {stats['pass_delay']}件\n" \
               f"1.出来高: {stats['pass_volume']}\n2.下半身: {stats['pass_kahanshin']}\n3.溜め: {stats['pass_tame']}\n" \
               f"4.60日線: {stats['pass_ma60_up']}\n5.長トレンド: {stats['pass_trend_align']}\n6.上ヒゲ: {stats['pass_upper_shadow']}\n" \
               f"5.新高値: {stats['pass_new_high']}\n7.天井圏回避: {stats['pass_ceiling_avoid']}\n\n" \
               f"★PPP: {stats['★PPP']} / ★Short: {stats['★PPP(Short)']} / 通常: {stats['normal_detect']}\n\n" \
               f"【詳細】\n" \
               f"3.溜め: {len(mail_lists['tame'])}件\n\n" \
               f"4.60日:\n{list_str(mail_lists['ma60_up'])}" \
               f"5.長トレンド:\n{list_str(mail_lists['trend_align'])}" \
               f"6.上ヒゲ:\n{list_str(mail_lists['upper_shadow'])}" \
               f"7.天井回避:\n{list_str(mail_lists['ceiling_avoid'])}"

        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"📊 adoGEM レポート ({start_range}-{end_range}) 合致:{valid_count}件"
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
