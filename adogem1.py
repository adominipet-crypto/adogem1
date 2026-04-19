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

def get_target_symbols():
    # 主要銘柄＋注目銘柄
    return [
        "9145", "9101", "9104", "9107", "9042", "2810", "1951", "6754", "6902", "7148",
        "7203", "6758", "8306", "9984", "8031", "8058", "4063", "8001", "6501", "4502",
        "7267", "6954", "7751", "7974", "6367", "6861", "4519", "2914", "3382", "6098",
        "215A", "2157", "3333", "3962", "4680", "4816", "6135", "6368", "7516", "8282"
    ]

def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        if len(df) < 60: return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        close = last['Close']
        open_p = last['Open']
        high = last['High']
        ma5 = last['MA5']
        ma20 = last['MA20']
        ma60 = last['MA60']
        ma60_prev = prev['MA60']

        # --- 相葉流・究極の厳選ロジック ---

        # 1. 陽線判定
        is_yang = close > open_p
        
        # 2. 下半身判定（実体が5日線をしっかり抜けている）
        body_mid = (open_p + close) / 2
        is_kahanshin = close > ma5 and body_mid < ma5

        # 3. 乖離率チェック（高値掴み防止: 5%未満）
        kairi_20 = (close - ma20) / ma20
        is_not_overextended = kairi_20 < 0.05 

        # 4. 【追加】上ヒゲ制限（3962対策）
        # 上ヒゲが実体より長い場合は「売り圧力が強い」と判断して除外
        body_length = close - open_p
        upper_shadow = high - close
        is_not_heavy_top = upper_shadow < body_length

        # 5. 【追加】長期線の傾き（3962対策）
        # 60日線が横ばいか上向きであることを条件にする
        is_trend_not_down = ma60 >= ma60_prev

        # 全条件合致
        if is_yang and is_kahanshin and is_not_overextended and is_not_heavy_top and is_trend_not_down:
            is_ppp = ma5 > ma20 > ma60
            star = "★PPP" if is_ppp else ""
            note = " ★要チェック" if symbol == "9145" else ""
            return f"{star}: {symbol}{note} (終値:{int(close)})"
        
        return None
    except:
        return None

def send_email(content):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = "【adoGEM流】真・究極厳選レポート"
    
    header = "相葉流（陽線・下半身・低乖離・ヒゲなし・長期上向き）合致銘柄：\n\n"
    msg.attach(MIMEText(header + content, 'plain'))
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)

def main():
    symbols = get_target_symbols()
    results = []
    
    print(f"スキャン開始（対象:{len(symbols)}銘柄）...")
    for symbol in symbols:
        res = analyze_stock(symbol)
        if res:
            results.append(res)
            print(f"ヒット: {res}")
        time.sleep(1)
    
    if results:
        send_email("\n".join(results))
        print("完了：メールを送信しました。")
    else:
        print("本日の厳しい基準をクリアした銘柄はありませんでした。")

if __name__ == "__main__":
    main()
