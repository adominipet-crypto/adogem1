import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import sys

# --- 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """戦略フィルターによる銘柄精査ロジック"""
    try:
        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        # データの取得（タイムアウトを設定してハングを防止）
        df = stock.history(period="6mo", progress=False, timeout=10)
        
        if df is None or df.empty or len(df) < 60:
            return None
        
        # 1. 出来高フィルター（50,000株以上）
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        today = df.iloc[-1]
        yest = df.iloc[-2]
        yest2 = df.iloc[-3]
        
        close, open_p = today['Close'], today['Open']
        ma5_today = today['MA5']
        ma60_today, ma60_yest = today['MA60'], yest['MA60']

        # 2. テクニカル条件判定
        # 下半身 & 陽線
        if not (open_p < ma5_today < close) or close <= open_p: return None 
        # 2営業日前の溜め判定
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return None
        # 60MAのトレンド判定
        if ma60_today <= ma60_yest: return None 
        # 5日新高値
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        # 天井圏の回避
        max_100 = df['High'].iloc[-100:].max()
        if close >= (max_100 * 0.95): return None

        # 検出時の表記
        return f"■ 銘柄コード: {symbol} | 終値: {int(close)}円"
    except:
        return None

def main():
    # 引数による範囲指定、デフォルトは1300-10000
    if len(sys.argv) > 2:
        start_range = int(sys.argv[1])
        end_range = int(sys.argv[2])
    else:
        start_range = 1300
        end_range = 10000
    
    print(f"--- adoGEM Strategy Scanner Running ({start_range}-{end_range}) ---")
    
    all_results = []
    for i in range(start_range, end_range):
        res = analyze_stock(str(i))
        if res:
            all_results.append(res)
            print(f"[DETECTED] {res}")
        time.sleep(0.15)

    # --- メール構成 ---
    if all_results:
        # 検出あり：視認性を重視した構成
        subject = f"🔔【重要】選定銘柄の検出報告 ({start_range}-{end_range})"
        body = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "   adoGEM 戦略フィルター：選定銘柄レポート\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "以下の銘柄において、設定された全条件の合致を確認しました。\n\n"
            + "\n".join(all_results) + "\n\n"
            "※本メールはシステムによる自動精査の結果を通知するものです。\n"
        )
    else:
        # 検出なし：定期報告としての構成
        subject = f"📊 スキャン完了通知 ({start_range}-{end_range})"
        body = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "   adoGEM 戦略フィルター：定期スキャン完了\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"指定範囲 {start_range} ～ {end_range} の精査が終了しました。\n\n"
            "結果：現在の市場データにおいて、条件に合致する銘柄は検出されませんでした。\n"
        )

    # メール送信処理
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
        print("報告メールの送信が完了しました。")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
