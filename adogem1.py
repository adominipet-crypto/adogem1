import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests
from google.oauth2.service_account import Credentials

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

stats = {
    "total_fetched": 0, "pass_volume": 0, "pass_kahanshin": 0, "pass_tame": 0,
    "pass_ma60_up": 0, "pass_trend_align": 0, "pass_upper_shadow": 0, "pass_new_high": 0, "pass_ceiling_avoid": 0,
    "★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0,
    "list_tame": [], "list_ma60_up": [], "list_trend_align": [], "list_upper_shadow": [], "list_new_high": [], "list_ceiling_avoid": []
}

def connect_spreadsheet():
    """新しいスプレッドシート名とタブ名で接続"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    
    # スプレッドシート名とタブ名を最新の指定に修正
    return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet("シート1")

def record_to_spreadsheet():
    """本日の選定結果（条件4以降）をシートに自動追記"""
    try:
        sheet = connect_spreadsheet()
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        new_rows = []
        target_stages = {
            "4. 60日線右肩上がり": stats["list_ma60_up"], 
            "新. 長期トレンド同期": stats["list_trend_align"],
            "新. 上ヒゲ選別": stats["list_upper_shadow"], 
            "6. 天井圏回避(最終)": stats["list_ceiling_avoid"]
        }
        for stage_name, stock_list in target_stages.items():
            for stock in stock_list:
                try:
                    parts = stock.split(" ■ ")
                    if len(parts) < 2: continue
                    code_price = parts[1].replace("円", "").split(" | ")
                    if len(code_price) < 2: continue
                    code = code_price[0].strip()
                    price = int(code_price[1].strip())
                    new_rows.append([today_str, code, price, stage_name, "", "判定待ち"])
                except:
                    continue
        if new_rows:
            sheet.append_rows(new_rows)
            print(f"【シート記録】{len(new_rows)} 件記録しました。")
    except Exception as e:
        print(f"シート記録エラー: {e}")

def get_stock_data_fallback(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.T?range=2y&interval=1d"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code != 200: return None
        result = res.json().get("chart", {}).get("result", [])
        if not result or result is None: return None
        quotes = result[0].get("indicators", {}).get("quote", [{}])[0]
        timestamps = result[0].get("timestamp", [])
        if not timestamps or not quotes.get("close", []): return None
        df = pd.DataFrame({
            "Open": quotes.get("open", []), "High": quotes.get("high", []),
            "Low": quotes.get("low", []), "Close": quotes.get("close", []), "Volume": quotes.get("volume", [])
        }, index=[datetime.datetime.fromtimestamp(ts) for ts in timestamps])
        df.dropna(subset=["Close", "Volume"], inplace=True)
        return df.sort_index()
    except:
        return None

def update_yesterday_results():
    """過去の『判定待ち』データの答え合わせ（◎◯▲✕ ＆ 前日比％）を自動実行"""
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        if all_records and len(all_records[0]) < 7: sheet.update_cell(1, 7, "前日比(%)")
        for i, row in enumerate(all_records):
            if i == 0 or len(row) < 6 or row[5] != "判定待ち": continue
            code, selected_price = row[1], int(row[2])
            df = get_stock_data_fallback(code)
            if df is not None and len(df) >= 1:
                next_close = int(df['Close'].iloc[-1])
                pct = ((next_close - selected_price) / selected_price) * 100
                mark = "◎" if pct >= 2.0 else "◯" if pct > 0.1 else "▲" if pct >= -0.1 else "✕"
                sheet.update_cell(i + 1, 5, next_close)
                sheet.update_cell(i + 1, 6, mark)
                sheet.update_cell(i + 1, 7, f"{pct:+.2f}%")
                print(f"【答え合わせ】{code}: {mark} ({pct:+.2f}%)")
                time.sleep(0.5)
    except Exception as e:
        print(f"自動答え合わせエラー: {e}")

def analyze_stock(symbol):
    try:
        df = get_stock_data_fallback(symbol)
        if df is None or df.empty or len(df) < 100: return "SKIP"
        if (pd.Timestamp.now() - df.index[-1]).days > 7: return "SKIP"
        if df['Volume'].iloc[-1] < 50000 or df['Volume'].iloc[-1] == 0: return "SKIP"
        stats["pass_volume"] += 1

        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['MA100'] = df['Close'].rolling(100).mean()
        df['MA300'] = df['Close'].rolling(300).mean() if len(df) >= 300 else None
        
        today, yest, yest2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        close, open_p, high = today['Close'], today['Open'], today['High']
        ma5_t, ma20_t, ma60_t, ma100_t, ma300_t = today['MA5'], today['MA20'], today['MA60'], today['MA100'], today['MA300']

        ppp_label = ""
        if ma300_t is not None and (ma5_t > ma20_t > ma60_t > ma100_t > ma300_t): ppp_label = "★PPP "
        elif ma300_t is None and (ma5_t > ma20_t > ma60_t > ma100_t): ppp_label = "★PPP(Short) "
        stock_text = f"■ {symbol} | {int(close)}円"

        if not (ma5_t < close) or close <= open_p: return "SKIP" 
        if ma5_t > (open_p + (close - open_p) * 0.5): return "SKIP"
        stats["pass_kahanshin"] += 1

        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["pass_tame"] += 1
        stats["list_tame"].append(f"  3 {ppp_label}{stock_text}")

        if ma60_t <= yest['MA60']: return "SKIP" 
        stats["pass_ma60_up"] += 1
        stats["list_ma60_up"].append(f"  4 {ppp_label}{stock_text}")

        if ma100_t <= yest['MA100']: return "SKIP"
        stats["pass_trend_align"] += 1
        stats["list_trend_align"].append(f"  長 {ppp_label}{stock_text}")

        if (high - close) >= ((close - open_p) * 1.5): return "SKIP"
        stats["pass_upper_shadow"] += 1
        stats["list_upper_shadow"].append(f"  ヒ {ppp_label}{stock_text}")

        if close >= df['High'].iloc[-6:-1].max():
            stats["pass_new_high"] += 1
            stats["list_new_high"].append(f"  5 {ppp_label}{stock_text}")

        if close >= (df['High'].iloc[-100:].max() * 0.97): return "SKIP"
        stats["pass_ceiling_avoid"] += 1
        stats["list_ceiling_avoid"].append(f"  最終 {ppp_label}{stock_text}")

        if "★PPP " in ppp_label: stats["★PPP"] += 1
        elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
        else: stats["normal_detect"] += 1
        return f"{ppp_label}{stock_text}"
    except:
        return "ERROR"

def get_target_symbols(start, end):
    try:
        url = "https://www.jpx.co.jp/markets/statistics-options/data/files/data_j.xls"
        res = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        df_jpx = pd.read_html(res.content)[0]
        df_jpx.columns = df_jpx.iloc[0]
        df_stocks = df_jpx[1:][df_jpx[1:]['市場・商品区分'].astype(str).str.contains('内国株式')]
        codes = sorted(df_stocks[df_stocks['コード'].astype(str).apply(lambda c: str(start) <= c[:4] < str(end))]['コード'].astype(str).unique().tolist())
        if codes: return codes
        raise Exception("No codes")
    except:
        return [str(i) for i in range(start, end)]

def main():
    start_range, end_range = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (1300, 4000)
    symbols = get_target_symbols(start_range, end_range)
    all_results = []
    for symbol in symbols:
        res = analyze_stock(symbol)
        if res not in ["ERROR", "SKIP"]: all_results.append(res)
        time.sleep(0.1)

    # 📊 スプレッドシート処理
    update_yesterday_results()
    record_to_spreadsheet()

    def list_str(lst): return "\n".join(lst) + "\n\n" if lst else "(該当なし)\n\n"
    body = f"総対象: {len(symbols)}\n\n" \
           f"1.出来高: {stats['pass_volume']}\n2.下半身: {stats['pass_kahanshin']}\n3.溜め: {stats['pass_tame']}\n" \
           f"4.60日線: {stats['pass_ma60_up']}\n長トレンド: {stats['pass_trend_align']}\n上ヒゲ: {stats['pass_upper_shadow']}\n" \
           f"5.新高値: {stats['pass_new_high']}\n6.天井圏回避: {stats['pass_ceiling_avoid']}\n\n" \
           f"★PPP: {stats['★PPP']} / ★Short: {stats['★PPP(Short)']} / 通常: {stats['normal_detect']}\n\n" \
           f"【詳細】\n3.溜め:\n{list_str(stats['list_tame'])}4.60日:\n{list_str(stats['list_ma60_up'])}" \
           f"長トレンド:\n{list_str(stats['list_trend_align'])}上ヒゲ:\n{list_str(stats['list_upper_shadow'])}" \
           f"天井回避:\n{list_str(stats['list_ceiling_avoid'])}"

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"📊 adoGEM レポート ({start_range}-{end_range}) 合致:{len(all_results)}件"
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("メール送信完了")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
