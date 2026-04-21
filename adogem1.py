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
RECEIVER_EMAIL = SENDER_EMAIL 

def get_all_tosho_codes():
    """全銘柄コードの生成"""
    # 1300番台から9999番台まで。実際には存在する銘柄のみ処理されます
    return [str(i) for i in range(1300, 9999)]

def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        
        # 銘柄が存在しない、またはデータ不足をスキップ
        if df.empty or len(df) < 60:
            return None
        
        # 出来高フィルター（直近出来高5万株未満は除外）
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        close, open_p, high = last['Close'], last['Open'], last['High']
        ma5 = last['MA5']
        ma20 = last['MA20']
        ma60 = last['MA60']
        ma60_prev = prev['MA60']

        # --- 【厳格版】判定ロジック ---
        
        # 1. 陽線判定
        if not (close > open_p): 
            return None
        
        # 2. 5日線の「またぎ」判定（浮き・スレスレを完全に排除）
        # 始値は5日線より下、かつ終値は5日線より上
        if not (open_p < ma5 < close): 
            return None
        
        # 3. 「実体の半分以上が5日線の上」判定
        body_length = close - open_p
        upper_part = close - ma5
        if (upper_part / body_length) <= 0.5: 
            return None

        # 4. 20日線乖離率チェック（5%以上は上げすぎとして除外）
        kairi_20 = (close - ma20) / ma20
        if kairi_20 >= 0.05: 
            return None

        # 5. 上ヒゲ制限（実体より長い上ヒゲは除外）
        upper_shadow = high - close
        if upper_shadow >= body_length: 
            return None

        # 6. 60日線の傾き（長期上昇トレンド確認）
        if ma60 < ma60_prev: 
            return None

        # --- 合格銘柄の装飾 ---
        is_ppp = ma5 > ma20 > ma60
        star = "★PPP" if is_ppp else ""
        note = " ★要チェック" if symbol == "9145" else ""
        
        return f"{star}: {symbol}{note} (終値:{int(close)})"
        
    except Exception:
        return None

def main():
    print("--- スキャンプロセス開始 ---")
    codes = get_all_tosho_codes()
    print(f"ターゲット銘柄数: {len(codes)}件")
    
    results = []
    count = 0
    
    for symbol in codes:
        res = analyze_stock(symbol)
        if res:
            results.append(res)
            print(f"【的中】 {res}")
        
        count += 1
        if count % 200 == 0:
            print(f"進捗: {count}銘柄完了...")
            
        # API負荷軽減のための微小待機
        time.sleep(0.2)
    
    if results:
        print(f"合計{len(results)}件の銘柄が見つかりました。メールを送信します。")
        send_email("\n".join(results))
    else:
        print("条件を満たす銘柄は見つかりませんでした。")

def send_email(content):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("エラー: メールの設定（Secrets）が見つかりません。")
        return

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = "【精鋭リスト】厳格判定版スキャン結果"
    
    body = "以下の銘柄が「厳格な下半身」の条件を満たしました：\n\n" + content
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print("メール送信完了")
    except Exception as e:
        print(f"メール送信失敗: {e}")

if __name__ == "__main__":
    main()
