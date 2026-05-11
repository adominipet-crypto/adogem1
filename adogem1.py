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
    """yfinanceを使用してデータを取得し、判定する道具"""
    try:
        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        # 過去6ヶ月分を取得
        df = stock.history(period="6mo")
        
        if df is None or df.empty or len(df) < 60:
            return None
        
        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close, open_p, ma5 = last['Close'], last['Open'], last['MA5']
        ma60, ma60_prev = last['MA60'], prev['MA60']

        # --- 判定ロジック（緩和版） ---
        if close <= open_p: return None  # 陽線
        if not (open_p < ma5 < close): return None # 下半身
        if ma60 < (ma60_prev * 0.998): return None # 60日線

        is_ppp = ma5 > last['MA20'] > ma60
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except:
        return None

def main():
    # テスト用に 7200番台（実在銘柄が多い範囲）に固定
    start_range = 7201 
    end_range = 7250 # 50銘柄に絞って素早くテスト
    
    print(f"--- 【動作確認テスト】開始: {start_range}-{end_range} ---")
    
    all_results = []
    for i in range(start_range, end_range):
        symbol = str(i)
        res = analyze_stock(symbol)
        if res:
            print(f"DEBUG: {symbol} 的中！")
            all_results.append(res)
        else:
            # ログを出して動いていることを確認
            if i % 10 == 0: print(f"DEBUG: {symbol} 付近を精査中...")
        time.sleep(0.3)

    # テスト報告メール
    subject = f"【テスト】adoGEM動作確認({start_range})"
    if all_results:
        body = "以下の銘柄がヒットしました：\n\n" + "\n".join(all_results)
    else:
        body = "スキャン完了。この範囲に合致銘柄はありませんでしたが、システムは正常です。"

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("--- テスト完了・メール送信成功 ---")
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    main()
