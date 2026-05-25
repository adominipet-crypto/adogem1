import yfinance as yf
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
from google.oauth2.service_account import Credentials

# --- Yahoo Finance 新仕様・アクセス制限回避対策 ---
yf.set_tz_cache_location(os.getcwd())

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
    """GitHub SecretsまたはローカルファイルからGoogleスプレッドシートへ安全に接続"""
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    
    # GitHub Secrets（環境変数）に鍵があるか確認
    secret_key = os.environ.get('GCP_SA_KEY')
    
    if secret_key:
        # 暗号保管庫の文字列から認証情報を作成（安全な方式）
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        # ローカル検証用（手元のパソコンで動かす時用）
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

def update_yesterday_results():
    """過去の『判定待ち』データの答え合わせ（◎◯▲✕ ＆ 前日比％）を自動実行"""
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        
        if all_records and len(all_records[0]) < 7:
            sheet.update_cell(1, 7, "前日比(%)")
        
        for i, row in enumerate(all_records):
            if i == 0: continue  # ヘッダー無視
            
            if len(row) >= 6 and row[5] == "判定待ち":
                code = row[1]
                selected_price = int(row[2])
                
                ticker = yf.Ticker(f"{code}.T")
                df = ticker.history(period="2d")
                if df is not None and len(df) >= 1:
                    next_close = int(df['Close'].iloc[-1])
                    
                    # 📈 前日比％の計算
                    change_percent = ((next_close - selected_price) / selected_price) * 100
                    change_str = f"{change_percent:+.2f}%"
                    
                    # 🎯 【判定基準】◎ ◯ ▲ ✕ ロジック
                    if change_percent >= 2.0:
                        result_mark = "◎"  # 2%以上の急騰
                    elif change_percent > 0.1:
                        result_mark = "◯"  # プラス圏
                    elif -0.1 <= change_percent <= 0.1:
                        result_mark = "▲"  # -0.1%〜+0.1%の微変動（トントン）
                    else:
                        result_mark = "✕"  # -0.1%未満の下落
                    
                    sheet.update_cell(i + 1, 5, next_close)
                    sheet.update_cell(i + 1, 6, result_mark)
                    sheet.update_cell(i + 1, 7, change_str)
                    
                    print(f"【答え合わせ】コード:{code} 判定:{result_mark} ({change_str})")
                    time.sleep(0.5)
    except Exception as e:
        print(f"自動答え合わせエラー: {e}")

def analyze_stock(symbol):
    try:
        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y", timeout=10)
        
        if df is None or df.empty or len(df) < 100:
            return "SKIP"
        
        # 🛡️ 【上場廃止・幽霊銘柄対策】1週間以上データ更新がない銘柄を排除
        if (pd.Timestamp.now() - df.index[-1]).days > 7:
            return "SKIP"

        # 1. 出来高フィルター（取引停止・出来高なしの銘柄も同時に排除）
        if df['Volume'].iloc[-1] < 50000 or df['Volume'].iloc[-1] == 0:
            return "SKIP"
        stats["pass_volume"] += 1

        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA100'] = df['Close'].rolling(window=100).mean()
        df['MA300'] = df['Close'].rolling(window=300).mean() if len(df) >= 300 else None
        
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

        # 🛑 5日新高値はカウントのみでスクロップさせない
        if close >= df['High'].iloc[-6:-1].max():
            stats["pass_new_high"] += 1
            stats["list_new_high"].append(f"  5 {ppp_label}{stock_text}")

        # 6. 天井圏の回避フィルター
        if close >= (df['High'].iloc[-100:].max() * 0.97): return "SKIP"
        stats["pass_ceiling_avoid"] += 1
        stats
