import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# --- 1. 環境変数の読み込み ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """adoGEM流：下半身判定ロジック"""
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        # 判定用の履歴データを取得
        df = ticker.history(period="70d")
        
        if df.empty or len(df) < 60 or df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close, open_p, high = last['Close'], last['Open'], last['High']
        ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
        ma60_prev = prev['MA60']

        # --- 厳格フィルター ---
        if not (close > open_p): return None # 陽線
        if not (open_p < ma5 < close): return None # 5日線をまたぐ
        body_len = close - open_p
        if (close - ma5) / body_len <= 0.5: return None # 実体の半分以上が上
        if (close - ma20) / ma20 >= 0.05: return None # 乖離5%以内
        if (high - close) >= body_len: return None # 上ヒゲ制限
        if ma60 < ma60_prev: return None # 60日線が上向き

        # --- 判定合格後の処理（時価総額チェック） ---
        # 速度維持のため、合格した銘柄のみ詳細情報を取得します
        info = ticker.info
        mkt_cap = info.get('marketCap', 0)
        
        # 100億円（10,000,000,000）未満かチェック
        caution = "★仕手注意 " if 0 < mkt_cap < 10000000000 else ""
        
        is_ppp = ma5 > ma20 > ma60
        status = "★PPP" if is_ppp else ""
        
        return f"{caution}{status} {symbol}: 終値{int(close)}円 (時価総額:{int(mkt_cap/100000000)}億)"
    except:
        return None

def main():
    print("--- adoGEM流スキャナー起動 ---")
    
    results = [] 
    codes = [str(i) for i in range(1300, 9999)]
    
    for symbol in codes:
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】: {res}")
            results.append(res)
        
        if int(symbol) % 1000 == 0:
            print(f"現在 {symbol} 付近をチェック中...")

    print(f"スキャン終了。的中数: {len(results)}")

    # --- メール送信処理 ---
    if results:
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            print("エラー: Secretsが読み込めません。")
            return

        msg = MIMEMultipart()
        msg['Subject'] = f"【的中】adoGEM流 厳格下半身リスト({len(results)}件)"
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg.attach(MIMEText("\n".join(results), 'plain'))

        try:
            print("Gmailサーバーに接続します...")
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print("メール送信に成功しました！")
        except Exception as e:
            print(f"メール送信エラー詳細: {e}")
    else:
        print("条件に合う銘柄はありませんでした。")

if __name__ == "__main__":
    main()
