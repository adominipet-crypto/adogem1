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

def analyze_batch(symbols):
    """制限回避を最優先したバッチ処理"""
    batch_results = []
    tickers = [f"{s}.T" for s in symbols if not (1300 <= int(s) <= 1699 or 8950 <= int(s) <= 8989)]
    
    if not tickers:
        return batch_results

    try:
        # threads=Falseにして負荷を下げ、制限を回避
        data = yf.download(tickers, period="70d", group_by='ticker', threads=False, progress=False)
        
        for t_str in tickers:
            try:
                df = data[t_str].dropna()
                if df.empty or len(df) < 60 or df['Volume'].iloc[-1] < 50000:
                    continue

                # adoGEM流ロジック
                df['MA5'] = df['Close'].rolling(window=5).mean()
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()

                last, prev = df.iloc[-1], df.iloc[-2]
                close, open_p, ma5 = last['Close'], last['Open'], last['MA5']
                close_prev, ma5_prev = prev['Close'], prev['MA5']
                ma60, ma60_prev = last['MA60'], prev['MA60']

                # --- 削除条件 ---
                if close <= open_p: continue 
                if not (open_p < ma5 < close): continue 
                if close_prev >= ma5_prev: continue  # 3110対策（実体割り込み必須）
                if ma60 < ma60_prev: continue 
                
                recent_high = df['High'].iloc[-6:-1].max()
                if close < recent_high: continue
                if close >= (df['High'].max() * 0.95): continue # 天井削除

                is_ppp = ma5 > last['MA20'] > ma60
                batch_results.append(f"{'★PPP ' if is_ppp else ''}{t_str.replace('.T', '')}: {int(close)}円")
            except:
                continue
    except Exception as e:
        print(f"警告: 制限の可能性があります ({e})")
        time.sleep(30) # 制限気味なら30秒休止
    
    return batch_results

def main():
    print("--- adoGEM流：通信制限・徹底回避モード起動 ---")
    all_results = []
    codes = [str(i) for i in range(1300, 10000)]
    
    # バッチサイズを50に縮小
    batch_size = 50
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        print(f"現在地: {batch[0]}付近を慎重に精査中...")
        
        hits = analyze_batch(batch)
        all_results.extend(hits)
        
        # 休憩時間を「ランダム」にして人間らしく振る舞う
        wait_time = random.uniform(5, 12)
        time.sleep(wait_time)

    # メール送信（中略）
    # (的中なしでも「全件完走」を報告するロジックは維持)
