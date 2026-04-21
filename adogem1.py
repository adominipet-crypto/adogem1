import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

# --- 1. 設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
RECEIVER_EMAIL = SENDER_EMAIL 

# --- 2. 判定ロジック ---
def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        if df.empty or len(df) < 60 or df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        close, open_p, high = last['Close'], last['Open'], last['High']
        ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
        ma60_prev = prev['MA60']

        # --- 【修正版】厳格な相葉流フィルター ---
        # 1. 陽線
        if not (close > open_p): return None
        # 2. 5日線を「またぐ」（始値 < 5日線 < 終値） ※9143/9022対策
        if not (open_p < ma5 < close): return None
        # 3. 実体の半分以上が5日線の上にある
        body_length = close - open_p
        if (close - ma5) / body_length <= 0.5: return None
        # 4. 20日線乖離 5%未満
        if (close - ma20) / ma20 >= 0.05: return None
        # 5. 上ヒゲ制限（実体より短い）
        if (high - close) >= body_length: return None
        # 6. 60日線が上向き
        if ma60 < ma60_prev: return None

        is_ppp = ma5 > ma20 > ma60
        star = "★PPP" if is_ppp else ""
        return f"{star}: {symbol} (終値:{int(close)})"
    except:
        return None

# --- 3. メイン処理 (if文を使わず確実に実行) ---

print("--- スキャンプロセス開始 ---")
codes = [str(i) for i in range(1300, 9999)]
results = []

for symbol in codes:
    res = analyze_stock(symbol)
    if res:
        print(f"的中: {res}")
        results.append(res)
    # 進捗ログ（1000件ごと）
    if int(symbol) % 1000 == 0:
        print(f"チェック中... {symbol}")

print(f"スキャン終了。的中数: {len(results)}")

if results:
    msg = MIMEMultipart()
    msg['Subject'] = "【精鋭】厳格判定スキャン結果"
    msg.attach(MIMEText("\n".join(results), 'plain'))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print("メールを送信しました。")
    except Exception as e:
        print(f"メール送信エラー: {e}")
