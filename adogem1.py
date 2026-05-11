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
    """adoGEM流：条件緩和版（より多くの初動をキャッチ）"""
    try:
        s = int(symbol)
        # ETF/REIT除外
        if 1300 <= s <= 1699 or 8950 <= s <= 8989:
            return None

        # 通信制限回避
        time.sleep(random.uniform(0.7, 1.2))
        
        end = datetime.now()
        start = end - timedelta(days=100)
        df = web.DataReader(f"{symbol}.JP", 'stooq', start, end)
        
        df = df.sort_index()

        if df is None or df.empty or len(df) < 60:
            return None
        
        # 出来高フィルター（3万株以上に緩和）
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

        # --- 判定ロジック（緩和済み） ---
        
        # 1. 陽線判定
        if close <= open_p: return None 
        
        # 2. 下半身判定（始値が5日線の下、終値が5日線の上）
        if not (open_p < ma5 < close): return None 
        
        # 3. 60日線が横ばい〜右肩上がり（極端な下落を除外）
        if ma60 < (ma60_prev * 0.998): return None 

        # 4. 【削除】直近5日高値更新の縛りを無くしました
        # 5. 【削除】天井圏の縛りも無くしました

        # 合格：PPP判定（オプション情報として表示）
        is_ppp = ma5 > last['MA20'] > ma60
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except:
        return None

def main():
    start_range = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_range = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    
    print(f"--- adoGEM 緩和スキャン開始: {start_range}-{end_range} ---")
    
    all_results = []
    codes = [str(i) for i in range(start_range, end_range)]
    
    for i, symbol in enumerate(codes):
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】{res}")
            all_results.append(res)
        
        if i % 100 == 0:
            print(f"進捗: {symbol} 付近を精査中...")

    # メール送信
    subject_prefix = "【厳選】" if all_results else "【報告】"
    subject = f"{subject_prefix}adoGEM精査({start_range}-{end_range})"
    
    if not all_results:
        body = f"{start_range}番から{end_range}番まで精査しましたが、緩和条件でも的中はありませんでした。"
    else:
        body = "条件緩和版で的中した銘柄一覧：\n\n" + "\n".join(all_results)

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
        print("完了")
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    main()
