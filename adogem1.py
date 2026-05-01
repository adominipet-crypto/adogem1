import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

# --- 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_batch(symbols):
    """100銘柄単位で一括判定するadoGEM流ロジック"""
    results = []
    # 銘柄リストをYahoo Finance形式に変換
    tickers = [f"{s}.T" for s in symbols if not (1300 <= int(s) <= 1699 or 8950 <= int(s) <= 8989)]
    
    try:
        # 一括ダウンロード（通信回数を激減させる）
        data = yf.download(tickers, period="70d", interval="1d", group_by='ticker', threads=True, progress=False)
        
        for t_str in tickers:
            try:
                df = data[t_str]
                symbol = t_str.replace(".T", "")
                
                # データが足りない、または出来高が少ない場合は削除
                if df.empty or len(df) < 60 or df['Volume'].iloc[-1] < 50000:
                    continue

                # 指標計算
                df['MA5'] = df['Close'].rolling(window=5).mean()
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()

                last = df.iloc[-1]
                prev = df.iloc[-2]
                close, open_p, high = last['Close'], last['Open'], last['High']
                ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
                close_prev, ma5_prev, ma60_prev = prev['Close'], prev['MA5'], prev['MA60']

                # --- adoGEM流：削除フィルター ---
                if close <= open_p: continue # 陽線でない
                if not (open_p < ma5 < close): continue # 下半身でない
                if close_prev >= ma5_prev: continue # 【3110対策】実体で割っていない
                if ma60 < ma60_prev: continue # 60日線が下向き

                # 勢いと天井圏の判定
                recent_5d_high = df['High'].iloc[-6:-1].max()
                if close < recent_5d_high: continue
                max_high_70d = df['High'].max()
                if close >= (max_high_70d * 0.95): continue

                # 判定合格
                results.append(f"的中候補 {symbol}: 終値{int(close)}円")
            except:
                continue
    except Exception as e:
        print(f"バッチ処理エラー: {e}")
    
    return results

def main():
    print("--- adoGEM流：一括高速スキャン（9999完走版）起動 ---")
    all_results = []
    # 1300から9999まで
    all_codes = [str(i) for i in range(1300, 10000)]
    
    # 100銘柄ずつまとめて処理
    batch_size = 100
    for i in range(0, len(all_codes), batch_size):
        batch = all_codes[i:i+batch_size]
        print(f"スキャン中... {batch[0]} - {batch[-1]}")
        
        batch_hits = analyze_batch(batch)
        all_results.extend(batch_hits)
        
        # 次のバッチまで少し休憩（サーバーに優しく）
        time.sleep(2)

    # メール送信処理（的中なし報告付き）
    # (中略：前回の送信ロジックと同じ)
    # ...
