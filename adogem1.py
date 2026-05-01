import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import random

# --- 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """adoGEM流：制限回避＋実体判定"""
    s = int(symbol)
    if 1300 <= s <= 1699 or 8950 <= s <= 8989:
        return None

    try:
        # 通信の「人間らしさ」を出すためのランダムな微休止
        time.sleep(random.uniform(0.1, 0.5))
        
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        
        if df is None or df.empty or len(df) < 60:
            return None
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close, open_p, ma5 = last['Close'], last['Open'], last['MA5']
        close_prev, ma5_prev = prev['Close'], prev['MA5']
        ma60, ma60_prev = last['MA60'], prev['MA60']

        # --- adoGEM流：削除フィルター ---
        if close <= open_p: return None # 陽線でない
        if not (open_p < ma5 < close): return None # 下半身でない
        
        # 【3110対策】前日終値が実体で5日線を割っていないなら削除
        if close_prev >= ma5_prev: return None
        
        if ma60 < ma60_prev: return None # 60日線上向き

        # 勢いと天井圏
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        if close >= (df['High'].max() * 0.95): return None

        is_ppp = ma5 > last['MA20'] > ma60
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except:
        return None

def main():
    print("--- adoGEM流：9999完走・徹底回避モード ---")
    all_results = []
    codes = [str(i) for i in range(1300, 10000)]
    
    # 制限を回避するため、一括ではなく10銘柄ずつの小分けで進める
    chunk_size = 10
    for i in range(0, len(codes), chunk_size):
        chunk = codes[i:i+chunk_size]
        
        for symbol in chunk:
            res = analyze_stock(symbol)
            if res:
                print(f"【的中】{res}")
                all_results.append(res)
        
        # 10銘柄ごとに少し長めに休む（Yahooの目をそらす）
        time.sleep(random.uniform(1, 3))
        
        if i % 100 == 0:
            print(f"進捗: {codes[i]}付近をチェック中...")

    # 的中なし報告メール送信
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    if all_results:
        msg['Subject'] = f"【厳選】adoGEM流 究極リスト({len(all_results)}件)"
        body = "精査が完了しました：\n\n" + "\n".join(all_results)
    else:
        msg['Subject'] = "【報告】adoGEM流 スキャン完了（対象なし）"
        body = "9999番まで全銘柄を精査しましたが、実体で割り込んだ「理想の初動」はありませんでした。"

    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("完了報告を送信しました")
    except Exception as e:
        print(f"メールエラー: {e}")

if __name__ == "__main__":
    main()
