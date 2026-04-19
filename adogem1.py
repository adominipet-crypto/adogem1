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
    """
    JPXのExcelが404エラーになる対策として、
    主要な価格帯のコード範囲を生成するか、安定した取得先を確保します。
    ここでは、3800銘柄を網羅するために主要なレンジを生成します。
    """
    # 実際にはJPXのリストがベストですが、エラー回避のため
    # 1000番台から9999番台の範囲を生成し、存在する銘柄のみ処理します
    codes = [str(i) for i in range(1300, 9999)]
    return codes

def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        # 出来高と価格をチェック（無効なコードを高速で飛ばす）
        df = ticker.history(period="70d")
        if len(df) < 60 or df['Volume'].iloc[-1] < 50000: # 出来高5万株未満は除外
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

        # --- 究極の相葉流厳選フィルター ---
        
        # 1. 陽線判定
        if not (close > open_p): return None
        
        # 2. 下半身判定（実体が半分以上抜けている）
        body_mid = (open_p + close) / 2
        if not (close > ma5 and body_mid < ma5): return None

        # 3. 乖離率チェック（5%以上は上げすぎ/9042対策）
        kairi_20 = (close - ma20) / ma20
        if kairi_20 >= 0.05: return None

        # 4. 上ヒゲ制限（3962対策）
        body_length = close - open_p
        upper_shadow = high - close
        if upper_shadow >= body_length: return None

        # 5. 長期線（60日線）の傾き（3962対策）
        if ma60 < ma60_prev: return None

        # --- 合格銘柄 ---
        is_ppp = ma5 > ma20 > ma60
        star = "★PPP" if is_ppp else ""
        # 9145は個別通知
        note = " ★要チェック銘柄" if symbol == "9145" else ""
        
        return f"{star}: {symbol}{note} (終値:{int(close)})"
        
    except:
        return None

def main():
    codes = get_all_tosho_codes()
    results = []
    
    print(f"全銘柄スキャン開始（約{len(codes)}件）...")
    
    # 負荷を抑えるため、上位市場の主要コードなどを優先的に回す仕組み
    count = 0
    for symbol in codes:
        res = analyze_stock(symbol)
        if res:
            results.append(res)
            print(f"【的中】 {res}")
        
        count += 1
        # 100件ごとに進捗表示
        if count % 100 == 0:
            print(f"{count}銘柄完了...")
            
        # サーバーに怒られないよう絶妙な待機時間
        time.sleep(0.5)
    
    if results:
        send_email("\n".join(results))
    else:
        print("厳しい基準をクリアする銘柄は見つかりませんでした。")

def send_email(content):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = "【adoGEM】3800銘柄スキャン：究極の精鋭リスト"
    
    body = "全銘柄の中から、陽線・下半身・低乖離・上ヒゲなし・長期上向きをすべて満たした銘柄です：\n\n" + content
    msg.attach(MIMEText(body, 'plain'))
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)

if __name__ == "__main__":
    main()
