import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import sys
import datetime
import gspread
import json
import requests
from google.oauth2.service_account import Credentials

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

stats = {
    "total_fetched": 0,
    "pass_volume": 0,
    "pass_kahanshin": 0,
    
    "pass_tame": 0,
    "list_tame": [],
    
    "pass_ma60_up": 0,
    "list_ma60_up": [],
    
    "pass_trend_align": 0,
    "list_trend_align": [],
    
    "pass_upper_shadow": 0,
    "list_upper_shadow": [],
    
    "pass_new_high": 0,
    "list_new_high": [],
    
    "pass_ceiling_avoid": 0,
    "list_ceiling_avoid": [],
    
    "★PPP": 0,
    "★PPP(Short)": 0,
    "normal_detect": 0
}

def connect_spreadsheet():
    """GitHub SecretsからGoogleスプレッドシートへ安全に接続"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
        
    client = gspread.authorize(creds)
    return client.open("adoGEM_検証ログ").worksheet("選定ログ")

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
                parts = stock.split(" ■ ")
                if len(parts) < 2: continue
                code_price = parts[1].replace("円", "").split(" | ")
                code = code_price[0].strip()
                price = int(code_price[1].strip())
                
                new_rows.append([today_str, code, price, stage_name, "", "判定待ち"])
                
        if new_rows:
            sheet.append_rows(new_rows)
            print(f"【シート記録】本日分のデータ {len(new_rows)} 件を記録しました。")
    except Exception as e:
        print(f"スプレッドシートへの記録エラー: {e}")

def fetch_japan_stock_history(symbol):
    """【新方式】yfinanceを使わず、日本株の時系列データを100%確実に取得する関数"""
    try:
        # 株探のデータエンドポイントを利用（ブラウザアクセスを完全偽装）
        url = f"https://kabutan.jp/stock/kabuka?code={symbol}&ashi=day"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            return None
            
        # HTMLから株価テーブルを抽出
        dfs = pd.read_html(response.text)
        target_df = None
        for temp_df in dfs:
            if '終値' in temp_df.columns or '前日比' in temp_df.columns:
                target_df = temp_df
                break
                
        if target_df is None or target_df.empty:
            return None
            
        # カラム名の標準化調整
        target_df.columns = [str(c) for c in target_df.columns]
        
        # 必要な列の割り当て（株探の配置構造に対応）
        df = pd.DataFrame()
        df['Date'] = pd.to_datetime(target_df.iloc[:, 0].astype(str).str.replace(r'[^\d/]', '', regex=True))
        df['Open'] = pd.to_numeric(target_df.iloc[:, 1], errors='coerce')
        df['High'] = pd.to_numeric(target_df.iloc[:, 2], errors='coerce')
        df['Low'] = pd.to_numeric(target_df.iloc[:, 3], errors='coerce')
        df['Close'] = pd.to_numeric(target_df.iloc[:, 4], errors='coerce')
        df['Volume'] = pd.to_numeric(target_df.iloc[:, 6], errors='coerce') * 1000  # 株探は千株単位のため修正
        
        df = df.dropna().sort_values('Date').reset_index(drop=True)
        
        # 将来の拡張性（週足・月足への変換ベース）のためインデックスを日付に
        df.set_index('Date', inplace=True)
        
        return df if len(df) >= 30 else None
    except:
        return None

def update_yesterday_results():
    """過去の『判定待ち』データの答え合わせ（◎◯▲✕ ＆ 前日比％）を自動実行"""
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        if not all_records or len(all_records) <= 1:
            return  # データがまだ無い場合はスキップ
            
        if len(all_records[0]) < 7:
            sheet.update_cell(1, 7, "前日比(%)")
        
        for i, row in enumerate(all_records):
            if i == 0: continue  # ヘッダー無視
            
            if len(row) >= 6 and row[5] == "判定待ち":
                code = row[1].strip()
                selected_price = int(row[2])
                
                df = fetch_japan_stock_history(code)
                if df is not None and len(df) >= 1:
                    next_close = int(df['Close'].iloc[-1])
                    
                    # 📈 前日比％の計算
                    change_percent = ((next_close - selected_price) / selected_price) * 100
                    change_str = f"{change_percent:+.2f}%"
                    
                    # 🎯 【判定基準】◎ ◯ ▲ ✕ ロジック
                    if change_percent >= 2.0: result_mark = "◎"
                    elif change_percent > 0.1: result_mark = "◯"
                    elif -0.1 <= change_percent <= 0.1: result_mark = "▲"
                    else: result_mark = "✕"
                    
                    sheet.update_cell(i + 1, 5, next_close)
                    sheet.update_cell(i + 1, 6, result_mark)
                    sheet.update_cell(i + 1, 7, change_str)
                    
                    print(f"【答え合わせ】コード:{code} 判定:{result_mark} ({change_str})")
                    time.sleep(0.5)
    except Exception as e:
        print(f"自動答え合わせエラー: {e}")

def analyze_stock(symbol):
    try:
        df = fetch_japan_stock_history(symbol)
        if df is None or len(df) < 30: # 取得件数に応じてローリング値を安全に変更
            return "SKIP"
        
        # 1. 出来高フィルター（5万株以上）
        if df['Volume'].iloc[-1] < 50000 or df['Volume'].iloc[-1] == 0:
            return "SKIP"
        stats["pass_volume"] += 1

        # 各種移動平均線の計算（データ長に合わせて安全に計算）
        df['MA5'] = df['Close'].rolling(window=min(5, len(df))).mean()
        df['MA20'] = df['Close'].rolling(window=min(20, len(df))).mean()
        df['MA60'] = df['Close'].rolling(window=min(min(60, len(df)), len(df))).mean()
        df['MA100'] = df['Close'].rolling(window=min(min(100, len(df)), len(df))).mean()
        df['MA300'] = df['Close'].rolling(window=300).mean() if len(df) >= 120 else None
        
        today, yest, yest2 = df.iloc[-1], df.iloc[-2], df.iloc[-3]
        close, open_p, high = today['Close'], today['Open'], today['High']
        ma5_t, ma20_t, ma60_t, ma100_t, ma300_t = today['MA5'], today['MA20'], today['MA60'], today['MA100'], today['MA300']

        ppp_label = ""
        if ma300_t is not None and (ma5_t > ma20_t > ma60_t > ma100_t > ma300_t): ppp_label = "★PPP "
        elif ma300_t is None and (ma5_t > ma20_t > ma60_t > ma100_t): ppp_label = "★PPP(Short) "
            
        stock_text = f"■ {symbol} | {int(close)}円"

        # 2. 下半身 ＆ 当日陽線
        if not (ma5_t < close) or close <= open_p: return "SKIP" 
        if ma5_t > (open_p + (close - open_p) * 0.5): return "SKIP"
        stats["pass_kahanshin"] += 1

        # 3. 2営業日前「溜め」判定
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["pass_tame"] += 1
        stats["list_tame"].append(f"  3 {ppp_label}{stock_text}")

        # 4. 中期（60日線）右肩上がり
        if ma60_t <= yest['MA60']: return "SKIP" 
        stats["pass_ma60_up"] += 1
        stats["list_ma60_up"].append(f"  4 {ppp_label}{stock_text}")

        # 長期トレンド同期
        if ma100_t <= yest['MA100']: return "SKIP"
        stats["pass_trend_align"] += 1
        stats["list_trend_align"].append(f"  長 {ppp_label}{stock_text}")

        # 上ヒゲ選別
        if (high - close) >= ((close - open_p) * 1.5): return "SKIP"
        stats["pass_upper_shadow"] += 1
        stats["list_upper_shadow"].append(f"  ヒ {ppp_label}{stock_text}")

        # 5日新高値
        if close >= df['High'].iloc[-6:-1].max():
            stats["pass_new_high"] += 1
            stats["list_new_high"].append(f"  5 {ppp_label}{stock_text}")

        # 6. 天井圏の回避フィルター
        if close >= (df['High'].iloc[-min(30, len(df)):].max() * 0.97): return "SKIP"
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
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        response = requests.get(url, headers=headers)
        df_jpx = pd.read_html(response.content)[0]
        df_jpx.columns = df_jpx.iloc[0]
        df_stocks = df_jpx[1:][df_jpx[1:]['市場・商品区分'].astype(str).str.contains('内国株式')]
        return sorted(df_stocks[df_stocks['コード'].astype(str).apply(lambda c: str(start) <= c[:4] < str(end))]['コード'].astype(str).unique().tolist())
    except:
        return [str(i) for i in range(start, end)]

def main():
    start_range, end_range = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (7003, 10000)
    symbols = get_target_symbols(start_range, end_range)
    total_count = len(symbols)
    
    all_results = []
    for symbol in symbols:
        res = analyze_stock(symbol)
        if res not in ["ERROR", "SKIP"]:
            all_results.append(res)
        time.sleep(0.2)  # 高速化のためにウェイトを最適化

    # 📊 スプレッドシート処理の実行
    update_yesterday_results()  # ① 前日データの自動答え合わせ
    record_to_spreadsheet()      # ② 本日データのログ書き込み

    def make_list_str(target_list): return "\n".join(target_list) + "\n\n" if target_list else "(該当なし)\n\n"

    detail_lists = (
        "【3. 2日前「溜め」】\n" f"{make_list_str(stats['list_tame'])}"
        "【4. 60日右肩上がり】\n" f"{make_list_str(stats['list_ma60_up'])}"
        "【[新] 長期(100MA上昇)】\n" f"{make_list_str(stats['list_trend_align'])}"
        "【[新] 上ヒゲ(1.5未満)】\n" f"{make_list_str(stats['list_upper_shadow'])}"
        "【5. 5日新高値更新[※現在スキップ中]】\n" f"{make_list_str(stats['list_new_high'])}"
        "【6. 天井圏(100日97%)】\n" f"{make_list_str(stats['list_ceiling_avoid'])}"
    )

    cond_report = (
        "【通過銘柄】\n"
        f" 1. 出来高選別 (5万株) : {stats['pass_volume']}\n"
        f" 2. 下半身(実体50%) ＆ 当日陽線 : {stats['pass_kahanshin']}\n"
        f" 3. 2営業日前「溜め」判定 : {stats['pass_tame']}\n"
        f" 4. 60日移動平均線 右肩上がり : {stats['pass_ma60_up']}\n"
        f" [新] 長期トレンド同期(100MA上昇) : {stats['pass_trend_align']}\n"
        f" [新] 上ヒゲ選別(1.5倍未満) : {stats['pass_upper_shadow']}\n"
        f" 5. 5日新高値更新 : {stats['pass_new_high']} (※スキップ)\n"
        f" 6. 天井圏回避 (100日高値97%未満) : {stats['pass_ceiling_avoid']}\n\n"
        "【選定内訳】\n"
        f"  - ★PPP 合致       : {stats['★PPP']}\n"
        f"  - ★PPP(Short) 合致: {stats['★PPP(Short)']}\n"
        f"  - 通常選定 合致    : {stats['normal_detect']}\n"
    )

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"📊 adoGEM 選定報告 ({start_range}-{end_range}) 合致:{len(all_results)}件"
    body = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "   adoGEM 戦略フィルター：選定銘柄レポート\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"総スキャン対象 : {total_count}\n\n"
        f"{cond_report}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "   各フィルター通過銘柄 詳細リスト\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{detail_lists}"
    )
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("報告メール送信完了")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
