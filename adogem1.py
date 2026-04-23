import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

# --- 1. 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
RECEIVER_EMAIL = SENDER_EMAIL 

# --- 2. 判定ロジック ---
def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        
        # データ不足や出来高の少ない銘柄をスキップ
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

        # --- 相葉流：厳格下半身判定 ---
        # 1. 陽線
        if not (close > open_p): return None
        # 2. 5日線を「またぐ」 (9143等対策)
        if not (open_p < ma5 < close): return None
        # 3. 実体の半分以上が5日線より上
        body_length = close - open_p
        if (close - ma5) / body_length <= 0.5: return None
        # 4. 20日線乖離 5%未満
        if (close - ma20) / ma20 >= 0.05: return None
        # 5. 上ヒゲ制限
        if (high - close) >= body_length: return None
        # 6. 60日線が上向き
        if ma60 < ma60_prev: return None

        is_ppp = ma5 > ma20 > ma60
        star = "★PPP" if is_ppp else ""
        return f"{star}: {symbol} (終値:{int(close)})"
    except:
        return None

# --- 3. メイン処理 ---
def main():
    print("--- スキャンプロセス開始 ---")
    
    # 銘柄リスト作成
    codes = [str(i) for i in range(1300, 9999)]
    results = [] # ここで定義されるためNameErrorが防げます

    for symbol in codes:
        res = analyze_stock(symbol)
        if res:
            print(f"的中: {res}")
            results.append(res)
        
        # 進捗確認ログ (1000件ごと)
        if int(symbol) % 1000 == 0:
            print(f"チェック中... {symbol}")

    print(f"スキャン終了。的中数: {len(results)}")

    # --- 4. メール送信部 ---
    if results:
        if not SENDER_EMAIL or not SENDER_PASSWORD:
            print("エラー: GitHubのSecretsが設定されていません。")
            return

        msg = MIMEMultipart()
        msg['Subject'] = f"【的中】厳格下半身リスト {len(results)}件"
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg.attach(MIMEText("\n".join(results), 'plain'))
        
        try:
            print("Gmailサーバーへ接続します...")
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print("メール送信に成功しました！")
        except Exception as e:
            print(f"メール送信エラー: {e}")
    else:
        print("本日の的中銘柄はありませんでした。")

# スクリプト実行の入り口
if __name__ == "__main__":
    main()
