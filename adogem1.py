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
    """データが拾えているか確認するための生存確認ログ付き"""
    try:
        s = int(symbol)
        if 1300 <= s <= 1699 or 8950 <= s <= 8989:
            return None

        # 取得間隔を少し短くしてテストを早める
        time.sleep(random.uniform(0.5, 0.8))
        
        end = datetime.now()
        start = end - timedelta(days=100)
        
        # Stooqからデータ取得
        df = web.DataReader(f"{symbol}.JP", 'stooq', start, end)
        
        if df is None or df.empty:
            # ここを通るなら通信エラーか銘柄が存在しない
            return None
        
        # --- ログ出力：ここで「データを拾えている証拠」をActionsのログに出す ---
        last_close = df['Close'].iloc[0] # Stooqは降順の場合があるため
        print(f"DEBUG: {symbol} 取得成功 - 最新終値: {last_close}")

        df = df.sort_index()
        
        # --- 超・緩和条件（とりあえず何かを出すため） ---
        # 出来高1万株以上、かつ「当日が陽線」なら全部出す
        last = df.iloc[-1]
        if df['Volume'].iloc[-1] > 10000 and last['Close'] > last['Open']:
            return f"【確認用】{symbol}: {int(last['Close'])}円 (出来高:{int(last['Volume'])})"
            
        return None
    except Exception as e:
        # エラーが出た場合はログに表示
        print(f"DEBUG: {symbol} 取得失敗 - {e}")
        return None

def main():
    start_range = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_range = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    
    print(f"--- adoGEM 生存確認スキャン: {start_range}-{end_range} ---")
    
    all_results = []
    # テストのため、最初の50銘柄だけスキャン（時間がかかるのを避けるため）
    codes = [str(i) for i in range(start_range, start_range + 50)]
    
    for symbol in codes:
        res = analyze_stock(symbol)
        if res:
            all_results.append(res)

    # メール送信
    subject = f"【生存確認】adoGEMデータ取得テスト({start_range})"
    body = "以下の銘柄のデータ取得に成功しました：\n\n" + "\n".join(all_results)

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
        print("テストメール送信完了")
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    main()
