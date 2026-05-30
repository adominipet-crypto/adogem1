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

# 統計カウンタの初期化
stats = {
    "pass_delay": 0,       # 0. データ遅延
    "pass_volume": 0,      # 0. 出来高
    "pass_kahanshin": 0,   # 1. 下半身
    "pass_tame": 0,        # 2. 溜め
    "pass_ma60_up": 0,     # 3. 60日線
    "pass_trend_align": 0, # 4. 長トレンド
    "pass_upper_shadow": 0,# 5. 上ヒゲ
    "pass_ceiling_avoid": 0,# 6. 天井圏回避
    "pass_new_high": 0,    # 7. 新高値
    "★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0
}

# 最終的に全条件をクリアした銘柄だけを格納する
selected_stocks = {}

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
        for code, data in selected_stocks.items():
            price = data["price"]
            stage_name = data["stage_name"]
            ppp_status = data["ppp_label"].strip() if data["ppp_label"].strip() else "通常"
            
            # 全条件をクリアしたものだけがここに来る
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
        
        # 0. データ遅延対策ガード
        last_data_date = df.index[-1].date()
        today_date = datetime.date.today()
        if (today_date - last_data_date).days > (3 if today_date.weekday() in [5, 6] else 1):
            stats["pass_delay"] += 1
            return "SKIP"

        # 0. 出来高フィルター
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

        # 十字線回避ロジック
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

        # 1. 下半身フィルター
        if not (ma5_t < close) or close <= open_p: return "SKIP" 
        stats["pass_kahanshin"] += 1
        
        # 2. 溜めフィルター
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["pass_tame"] += 1

        # 3. 60日線フィルター
        if ma60_t <= yest['MA60']: return "SKIP" 
        stats["pass_ma60_up"] += 1

        # 4. 長トレンドフィルター
        if ma100_t <= yest['MA100']: return "SKIP"
        stats["pass_trend_align"] += 1

        # 5. 上ヒゲフィルター
        if (high - close) >= ((close - open_p) * 1.5): return "SKIP"
        stats["pass_upper_shadow"] += 1

        # 6. 天井圏回避フィルター（ロジックの連続性のために新高値の前に移動）
        if close >= (df['High'].iloc[-100:].max() * 0.97): return "SKIP"
        stats["pass_ceiling_avoid"] += 1

        # 7. 新高値フィルター（ここで条件を満たさないものを除外(SKIP)するように修正）
        if not (close >= df['High'].iloc[-6:-1].max()): return "SKIP"
        stats["pass_new_high"] += 1

        # 🌟 すべてのフィルター（1〜7）をクリアした銘柄だけを格納
        selected_stocks[symbol] = {
            "price": int(close), 
            "text": f"  最終 {ppp_label}{stock_text}", 
            "stage_name": "7. 新高値(最終)", 
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
        record_to_spreadsheet()
        
        # 最終合格銘柄の一覧を作成
        detail_lines = []
        for code, data in selected_stocks.items():
            detail_lines.append(data["text"])
            
        detail_text = "\n".join(detail_lines) if detail_lines else "(該当なし)"

        # レポート本文（ナンバリングを0〜7に完全修正）
        body = f"総対象: {len(symbols)}\n\n" \
               f"0.データ遅延: {stats['pass_delay']}件\n" \
               f"0.出来高: {stats['pass_volume']}件\n" \
               f"1.下半身: {stats['pass_kahanshin']}件\n" \
               f"2.溜め: {stats['pass_tame']}件\n" \
               f"3.60日線: {stats['pass_ma60_up']}件\n" \
               f"4.長トレンド: {stats['pass_trend_align']}件\n" \
               f"5.上ヒゲ: {stats['pass_upper_shadow']}件\n" \
               f"6.天井圏回避: {stats['pass_ceiling_avoid']}件\n" \
               f"7.新高値: {stats['pass_new_high']}件\n\n" \
               f"★PPP: {stats['★PPP']} / ★Short: {stats['★PPP(Short)']} / 通常: {stats['normal_detect']}\n\n" \
               f"【詳細（全条件クリア銘柄一覧）】\n" \
               f"{detail_text}"

        msg = MIMEMultipart()
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg['Subject'] = f"📊 adoGEM レポート ({start_range}-{end_range}) 合致:{len(selected_stocks)}件"
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
