import pandas_datareader.data as web
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
    """adoGEM流：Stooq経由精査（3110などのヒゲ割れ排除ロジック）"""
    s = int(symbol)
    # ETF/REIT除外
    if 1300 <= s <= 1699 or 8950 <= s <= 8989:
        return None

    try:
        # 通信制限回避：Stooqは1件ずつ丁寧に
        time.sleep(random.uniform(0.8, 1.5))
        
        end = datetime.now()
        start = end - timedelta(days=100)
        df = web.DataReader(f"{symbol}.JP", 'stooq', start, end)
        
        df = df.sort_index()

        if df is None or df.empty or len(df) < 60:
            return None
        
        # 出来高フィルター
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
        
        # 1. 陽線でないなら削除
        if close <= open_p: return None 
        
        # 2. 終値が5日線をまたいでいないなら削除
        if not (open_p < ma5 < close): return None 
        
        # 3. 【重要：3110対策】前日終値が実体で5日線を割っていないなら削除
        # これにより「ヒゲだけで触れた強いトレンド」を確実に排除します
        if close_prev >= ma5_prev:
            return None
        
        # 4. 60日線が下向きなら削除
        if ma60 < ma60_prev: return None 

        # 5. 直近5日間の最高値を更新していないなら削除
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        
        # 6. 天井圏（最高値の5%以内）なら削除
        if close >= (df['High'].max() * 0.95): return None

        # 合格：PPP判定
        is_ppp = ma5 > last['MA20'] > ma60
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except:
        return None

def main():
    # 引数からスキャン範囲を取得 (例: python adogem1.py 1300 4000)
    # 引数がない場合は全範囲を対象にする
    start_range = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_range = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    
    print(f"--- adoGEM流 スキャン開始: {start_range}番 ～ {end_range}番 ---")
    
    all_results = []
    codes = [str(i) for i in range(start_range, end_range)]
    
    for i, symbol in enumerate(codes):
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】{res}")
            all_results.append(res)
        
        if i % 100 == 0:
            print(f"進捗: {symbol} 付近を精査中...")

    # --- メール送信 ---
    if not all_results:
        # 的中なしでも「完走したこと」を知らせるために送信
        subject = f"【報告】adoGEM精査({start_range}-{end_range}) 的中なし"
        body = f"{start_range}番から{end_range}番まで精査しましたが、条件を満たす「本物の初動」はありませんでした。"
    else:
        subject = f"【厳選】adoGEM精査({start_range}-{end_range}) 的中あり"
        body = f"以下の銘柄が条件をクリアしました：\n\n" + "\n".join(all_results)

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
        print(f"範囲 {start_range}-{end_range} の報告メールを送信しました")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
