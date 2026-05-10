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
    """adoGEM流：最新精査ロジック（条件3削除版）"""
    s = int(symbol)
    # ETF/REIT除外
    if 1300 <= s <= 1699 or 8950 <= s <= 8989:
        return None

    try:
        # 通信制限回避
        time.sleep(random.uniform(0.8, 1.5))
        
        end = datetime.now()
        start = end - timedelta(days=100)
        df = web.DataReader(f"{symbol}.JP", 'stooq', start, end)
        
        df = df.sort_index()

        if df is None or df.empty or len(df) < 60:
            return None
        
        # 出来高フィルター（5万株以上）
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close, open_p, ma5 = last['Close'], last['Open'], last['MA5']
        ma60, ma60_prev = last['MA60'], prev['MA60']

        # --- adoGEM流：判定ロジック ---
        
        # 1. 陽線判定
        if close <= open_p: return None 
        
        # 2. 下半身判定（始値が5日線の下、終値が5日線の上）
        if not (open_p < ma5 < close): return None 
        
        # 【旧条件3：前日の実体割れチェックは削除されました】
        # これにより3110のような、勢いのある押し目も検知対象になります
        
        # 4. 60日線が下向きなら削除（長期トレンド重視）
        if ma60 < ma60_prev: return None 

        # 5. 直近5日間の最高値を更新（もみ合い上放れ重視）
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        
        # 6. 天井圏（最高値の5%以内）なら削除（高値掴み防止）
        if close >= (df['High'].max() * 0.95): return None

        # 合格：PPP（パンパカパン）判定
        is_ppp = ma5 > last['MA20'] > ma60
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except:
        return None

def main():
    # 引数から範囲を取得
    start_range = int(sys.argv[1]) if len(sys.argv) > 1 else 1300
    end_range = int(sys.argv[2]) if len(sys.argv) > 2 else 10000
    
    print(f"--- adoGEM流 スキャン開始: {start_range}-{end_range} ---")
    
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
        body = f"{start_range}番から{end_range}番まで精査しましたが、条件を満たす銘柄はありませんでした。"
    else:
        body = "以下の銘柄が条件をクリアしました（条件3削除版）：\n\n" + "\n".join(all_results)

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
        print("報告メールを送信しました")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
