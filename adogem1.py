import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

# --- 1. 設定エリア ---
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

        # 【厳格フィルター】
        if not (close > open_p): return None # 陽線
        if not (open_p < ma5 < close): return None # 5日線をまたぐ
        body_length = close - open_p
        if (close - ma5) / body_length <= 0.5: return None # 半分以上が上
        if (close - ma20) / ma20 >= 0.05: return None # 乖離
        if (high - close) >= body_length: return None # 上ヒゲ
        if ma60 < ma60_prev: return None # 60日線上向き

        is_ppp = ma5 > ma20 > ma60
        star = "★PPP" if is_ppp else ""
        return f"{star}: {symbol} (終値:{int(close)})"
    except:
        return None

# --- 3. メイン実行部 ---
# ここで results を定義しているので、これより下で if results を使います
if __name__ == "__main__":
    print("--- スキャンプロセス開始 ---")
    codes = [str(i) for i in range(1300, 9999)]
    results = [] # ここで定義

    for symbol in codes:
        res = analyze_stock(symbol)
        if res:
            print(f"的中: {res}")
            results.append(res)
        if int(symbol) % 1000 == 0:
            print(f"チェック中... {symbol}")

    print(f"スキャン終了。的中数: {len(results)}")

    # --- 4. メール送信部 ---
    if results:
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            print("エラー: GitHubのSecretsが未設定です。")
        else:
            msg = MIMEMultipart()
            msg['Subject'] = f"【的中】厳格下半身リスト {len(results)}件"
            msg['From'] = SENDER_EMAIL
            msg['To'] = RECEIVER_EMAIL
            msg.attach(MIMEText("\n".join(results), 'plain'))
            
            try:
                print("Gmail接続開始...")
                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.send_message(msg)
                server.quit()
                print("メール送信に成功しました！")
            except Exception as e:
                print(f"メール送信エラー詳細: {e}")
    else:
        print("本日の的中はありませんでした。")
