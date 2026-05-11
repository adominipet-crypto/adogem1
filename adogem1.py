import yfinance as yf # 切り替え
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
    """yfinanceを使用して確実にデータを取得する"""
    try:
        s = int(symbol)
        if 1300 <= s <= 1699 or 8950 <= s <= 8989:
            return None

        # yfinance用のシンボル（例: 7001.T）
        ticker = f"{symbol}.T"
        
        # データを取得（通信エラー対策でリトライを入れる）
        stock = yf.Ticker(ticker)
        df = stock.history(period="6mo") # 過去6ヶ月分
        
        if df is None or df.empty or len(df) < 60:
            print(f"DEBUG: {symbol} データなし")
            return None
        
        print(f"DEBUG: {symbol} 取得成功 - 最新終値: {df['Close'].iloc[-1]:.0f}")

        # 出来高フィルター（3万株）
        if df['Volume'].iloc[-1] < 30000:
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
    except Exception as e:
        print(f"DEBUG: {symbol} エラー - {e}")
        return None

def main():
    start_range = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_range = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    
    # テストとして100銘柄スキャンしてみる
    # 成功したら range(start_range, end_range) に戻してください
    target_codes = [str(i) for i in range(start_range, start_range + 100)]
    
    print(f"--- yfinance スキャン開始: {target_codes[0]}-{target_codes[-1]} ---")
    
    all_results = []
    for symbol in target_codes:
        res = analyze_stock(symbol)
        if res:
            all_results.append(res)
        # yfinanceは少し速めに回しても比較的大丈夫
        time.sleep(0.2)

    # メール送信（的中がある場合のみ）
    if all_results:
        subject = f"【的中】adoGEM精査({target_codes[0]}-{target_codes[-1]})"
        body = "以下の銘柄が条件をクリアしました：\n\n" + "\n".join(all_results)
        
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
            print("メール送信完了")
        except Exception as e:
            print(f"メール送信失敗: {e}")
    else:
        print("的中なしのためメール送信をスキップしました")

if __name__ == "__main__":
    main()
