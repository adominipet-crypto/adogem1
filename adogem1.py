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

def analyze_stock(symbol):
    """adoGEM流：直近高値厳格フィルター版"""
    s = int(symbol)
    if 1300 <= s <= 1699: return None 
    if 8950 <= s <= 8989: return None 

    time.sleep(0.1) # 通信安定化

    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        
        if df.empty or len(df) < 60 or df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        close, open_p = last['Close'], last['Open']
        ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
        ma60_prev = df.iloc[-2]['MA60']

        # --- adoGEM流 基本フィルター ---
        if close <= open_p: return None # 陽線必須
        if not (open_p < ma5 < close): return None # 5日線またぎ
        if ma60 < ma60_prev: return None # 60日線上向き

        # --- 【強化】直近高値フィルター（厳格モード） ---
        # 過去5営業日（今日を含まない）の最高値を取得
        recent_5d_high = df['High'].iloc[-6:-1].max()
        
        # 今日の終値が直近5日の高値を超えていない（＝戻りきっていない）なら除外
        # これにより「★直近高値割れ」を出すまでもなく、リストから消し去ります
        if close < recent_5d_high:
            return None

        # 最高値（70日間）の5%以内なら除外（天井圏回避）
        max_high_70d = df['High'].max()
        if close >= (max_high_70d * 0.95):
            return None

        # --- 詳細情報取得 ---
        info = ticker.info
        mkt_cap = info.get('marketCap', 0)
        if mkt_cap == 0: return None

        sector = info.get('sector', '不明')
        caution = "★仕手注意 " if 0 < mkt_cap < 10000000000 else ""
        is_ppp = ma5 > ma20 > ma60
        status = "★PPP" if is_ppp else ""
        
        return f"{caution}{status} {symbol}: 終値{int(close)}円 (時価:{int(mkt_cap/100000000)}億 / 業種:{sector})"
    except:
        return None

def main():
    print("--- adoGEM流スキャナー：直近高値厳格モード起動 ---")
    results = [] 
    codes = [str(i) for i in range(1300, 9999)]
    
    for i, symbol in enumerate(codes):
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】: {res}")
            results.append(res)
        if i % 100 == 0:
            print(f"スキャン中... {symbol}")

    if results:
        # メール送信（中略）
        msg = MIMEMultipart()
        msg['Subject'] = f"【厳選】adoGEM流 究極リスト({len(results)}件)"
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg.attach(MIMEText("\n".join(results), 'plain'))
        # ...送信ロジック...
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("メール送信完了！")
    else:
        print("条件に完全に一致する精鋭銘柄はありませんでした。")

if __name__ == "__main__":
    main()
