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
    """
    adoGEM流：最新精査ロジック
    条件：出来高5万以上、当日陽線、下半身(始値下・終値上)、
    2営業日前まで5MA下(溜め)、60MA右肩上がり、5日新高値、天井圏回避
    """
    try:
        s = int(symbol)
        # ETF/REIT除外
        if 1300 <= s <= 1699 or 8950 <= s <= 8989:
            return None

        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        # 判定に必要な期間（約半年分）を取得
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
        
        # データの抽出
        today = df.iloc[-1]
        yest = df.iloc[-2]   # 1営業日前
        yest2 = df.iloc[-3]  # 2営業日前
        
        close, open_p = today['Close'], today['Open']
        ma5_today = today['MA5']
        ma60_today, ma60_yest = today['MA60'], yest['MA60']

        # --- 2. 当日の下半身 ＆ 陽線(プラス引け) 判定 ---
        # 始値 < 5日線 < 終値 かつ 終値 > 始値
        if not (open_p < ma5_today < close): return None
        if close <= open_p: return None 
        
        # --- 3. 2営業日前までの「溜め」判定 ---
        # 前日と前々日の終値が、それぞれの日の5日線の下にあること
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']):
            return None

        # --- 4. 長期トレンド（60日線が右肩上がり） ---
        if ma60_today <= ma60_yest: return None 

        # --- 5. 新高値（終値が過去5日間の最高値を更新） ---
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        
        # --- 6. 過熱感回避（直近100日最高値から5%以内の天井圏は除外） ---
        max_100 = df['High'].iloc[-100:].max()
        if close >= (max_100 * 0.95): return None

        # 合格：PPP（パンパカパン）判定
        is_ppp = ma5_today > today['MA20'] > ma60_today
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except:
        return None

def main():
    # GitHub Actionsの三分割設定（引数）を読み込み
    if len(sys.argv) > 2:
        start_range = int(sys.argv[1])
        end_range = int(sys.argv[2])
    else:
        start_range = 1300
        end_range = 10000
    
    print(f"--- adoGEM 厳選精査始動({start_range}-{end_range}) ---")
    
    all_results = []
    for i in range(start_range, end_range):
        symbol = str(i)
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】{symbol}")
            all_results.append(res)
        
        # yfinanceへの負荷を考慮したスリープ
        time.sleep(0.15)

    # 的中報告メール（該当がある場合のみ送信）
    if all_results:
        subject = f"【厳選】adoGEM精査報告({start_range}-{end_range})"
        body = "以下の銘柄が『2日間の溜め』を含む全条件をクリアしました：\n\n" + "\n".join(all_results)
        
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
            print(f"報告送信完了（的中:{len(all_results)}件）")
        except Exception as e:
            print(f"メール送信失敗: {e}")
    else:
        print("的中なし。")

if __name__ == "__main__":
