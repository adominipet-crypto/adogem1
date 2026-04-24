import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# --- 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """adoGEM流：下半身 ＋ ETF除外 ＋ 時価0除外 ＋ 高値圏/直近高値割れ判定"""
    s = int(symbol)
    if 1300 <= s <= 1699: return None 
    if 8950 <= s <= 8989: return None 

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
        prev = df.iloc[-2]
        close, open_p, high = last['Close'], last['Open'], last['High']
        ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
        ma60_prev = prev['MA60']

        # --- adoGEM流 厳格フィルター ---
        if not (close > open_p): return None 
        if not (open_p < ma5 < close): return None 
        body_len = close - open_p
        if (close - ma5) / body_len <= 0.5: return None 
        if (close - ma20) / ma20 >= 0.05: return None 
        if (high - close) >= body_len: return None 
        if ma60 < ma60_prev: return None 

        # --- 詳細判定ロジック ---
        # 1. 過去70日の最高値
        max_high = df['High'].max()
        
        # 2. 直近の高値（直近10日間の中での最高値）
        recent_max = df['High'].iloc[-10:-1].max()

        # 高値圏フィルター（最高値の3%以内なら除外）
        if close >= (max_high * 0.97):
            return None

        # 直近高値割れの判定
        is_break_high = close < recent_max
        high_caution = "★直近高値割れ " if is_break_high else ""

        # --- 的中後の詳細チェック ---
        info = ticker.info
        mkt_cap = info.get('marketCap', 0)
        if mkt_cap == 0: return None

        sector = info.get('sector', '不明')
        caution = "★仕手注意 " if 0 < mkt_cap < 10000000000 else ""
        is_ppp = ma5 > ma20 > ma60
        status = "★PPP" if is_ppp else ""
        
        return f"{high_caution}{caution}{status} {symbol}: 終値{int(close)}円 (時価:{int(mkt_cap/100000000)}億 / 業種:{sector})"
    except:
        return None

def main():
    print("--- adoGEM流スキャナー起動 (高値割れ警戒モード) ---")
    results = [] 
    codes = [str(i) for i in range(1300, 9999)]
    
    for symbol in codes:
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】: {res}")
            results.append(res)
        if int(symbol) % 1000 == 0:
            print(f"チェック中... {symbol}")

    if results:
        msg = MIMEMultipart()
        msg['Subject'] = f"【的中】adoGEM流 精鋭リスト({len(results)}件)"
        msg['From'] = SENDER_EMAIL
        msg['To'] = SENDER_EMAIL
        msg.attach(MIMEText("\n".join(results), 'plain'))
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print("メール送信に成功しました！")
        except Exception as e:
            print(f"エラー: {e}")

if __name__ == "__main__":
    main()
