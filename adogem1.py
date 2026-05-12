import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import random
from datetime import datetime, timedelta
import sys

# --- 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """adoGEM流：最新精査ロジック（ログ強化版）"""
    try:
        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        # 欠番エラーを画面に出さないように quiet=True 設定（もしあれば）
        df = stock.history(period="6mo", progress=False)
        
        if df is None or df.empty or len(df) < 60:
            return None
        
        # --- 【追加】実在する銘柄を拾った証拠をログに出す ---
        print(f"CHECKING: {symbol} を精査中...")

        # 1. 出来高フィルター（50,000株以上）
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        today = df.iloc[-1]
        yest = df.iloc[-2]
        yest2 = df.iloc[-3]
        
        close, open_p = today['Close'], today['Open']
        ma5_today = today['MA5']
        ma60_today, ma60_yest = today['MA60'], yest['MA60']

        # 2. 当日の下半身 ＆ 陽線判定
        if not (open_p < ma5_today < close) or close <= open_p: return None 
        
        # 3. 2営業日前までの「溜め」判定
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return None

        # 4. 60MA右肩上がり
        if ma60_today <= ma60_yest: return None 

        # 5. 5日新高値
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        
        # 6. 天井圏回避
        max_100 = df['High'].iloc[-100:].max()
        if close >= (max_100 * 0.95): return None

        print(f"★★★ 的中！ {symbol} ★★★")
        return f"{symbol}: {int(close)}円"
    except:
        return None

def main():
    if len(sys.argv) > 2:
        start_range = int(sys.argv[1])
        end_range = int(sys.argv[2])
    else:
        start_range = 1300
        end_range = 10000
    
    print(f"--- adoGEM 稼働中 ({start_range}-{end_range}) ---")
    
    all_results = []
    for i in range(start_range, end_range):
        res = analyze_stock(str(i))
        if res:
            all_results.append(res)
        time.sleep(0.15)

    if all_results:
        subject = f"【厳選】adoGEM精査報告({start_range}-{end_range})"
        body = "的中銘柄：\n\n" + "\n".join(all_results)
        msg = MIMEMultipart(); msg['From'] = SENDER_EMAIL; msg['To'] = SENDER_EMAIL; msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587); server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD); server.send_message(msg); server.quit()
        except: pass

if __name__ == "__main__":
    main()
