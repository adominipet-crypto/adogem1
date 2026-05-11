import yfinance as yf
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
    """adoGEM流：6大条件すべてを反映した精査ロジック"""
    try:
        s = int(symbol)
        # ETF/REIT除外
        if 1300 <= s <= 1699 or 8950 <= s <= 8989:
            return None

        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        # 過去100日分のデータを取得（天井圏判定のため）
        df = stock.history(period="6mo")
        
        if df is None or df.empty or len(df) < 60:
            return None
        
        # --- 1. 出来高フィルター（50,000株以上） ---
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close, open_p, high = last['Close'], last['Open'], last['High']
        ma5, ma60, ma60_prev = last['MA5'], last['MA60'], prev['MA60']

        # --- 2. 陽線判定 ---
        if close <= open_p: return None 
        
        # --- 3. 下半身判定（始値が5日線の下、終値が5日線の上） ---
        if not (open_p < ma5 < close): return None 
        
        # --- 4. 長期トレンド（60日線が右肩上がり） ---
        if ma60 <= ma60_prev: return None 

        # --- 5. 新高値（終値が過去5日間の最高値を更新） ---
        # 当日を含まない過去5日間の「High」の最大値と比較
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        
        # --- 6. 過熱感（直近100日間の最高値から5%以内＝天井圏は除外） ---
        max_100 = df['High'].iloc[-100:].max()
        if close >= (max_100 * 0.95): return None

        # 合格：PPP（パンパカパン）判定（付加情報）
        is_ppp = ma5 > last['MA20'] > ma60
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except:
        return None

def main():
    # GitHub Actionsからの引数を受け取る（三分割スキャン用）
    if len(sys.argv) > 2:
        start_range = int(sys.argv[1])
        end_range = int(sys.argv[2])
    else:
        start_range = 1300
        end_range = 10000
    
    print(f"--- adoGEM 厳選精査始動: {start_range}-{end_range} ---")
    
    all_results = []
    for i in range(start_range, end_range):
        symbol = str(i)
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】{symbol}")
            all_results.append(res)
        
        # サーバー負荷軽減（yfinanceは比較的丈夫ですが念のため）
        time.sleep(0.1)

    # 的中報告メール（該当がある場合のみ送信）
    if all_results:
        subject = f"【厳選】adoGEM精査報告({start_range}-{end_range})"
        body = "以下の銘柄が全6条件をクリアしました：\n\n" + "\n".join(all_results)
        
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
            print(f"報告送信完了（{len(all_results)}件）")
        except Exception as e:
            print(f"メール送信失敗: {e}")
    else:
        print("的中なし。")

if __name__ == "__main__":
    main()
