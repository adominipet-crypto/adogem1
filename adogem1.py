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
    """adoGEM流：下半身判定 ＋ ETF/REIT除外"""
    # 【高速化】コード番号でETF/REITの可能性が高いものを即スキップ
    s = int(symbol)
    if 1300 <= s <= 1699: return None # ETF関連をスキップ
    if 8950 <= s <= 8989: return None # REIT関連をスキップ

    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        
        # 出来高フィルター（5万株未満はスキップ）
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
        if not (close > open_p): return None # 陽線
        if not (open_p < ma5 < close): return None # 5日線をまたぐ
        body_len = close - open_p
        if (close - ma5) / body_len <= 0.5: return None # 実体の半分以上が上
        if (close - ma20) / ma20 >= 0.05: return None # 乖離5%以内
        if (high - close) >= body_len: return None # 上ヒゲ制限
        if ma60 < ma60_prev: return None # 60日線が上向き

        # --- 的中後の詳細チェック ---
        info = ticker.info
        
        # セクターを取得して「REIT/ETF」が含まれていたら除外（二段構えのガード）
        sector = info.get('sector', '不明')
        if sector in ['Financial', 'None', None] and 'REIT' in info.get('longBusinessSummary', ''):
            return None

        mkt_cap = info.get('marketCap', 0)
        caution = "★仕手注意 " if 0 < mkt_cap < 10000000000 else ""
        is_ppp = ma5 > ma20 > ma60
        status = "★PPP" if is_ppp else ""
        
        # 業種（sector）を表示に含める
        return f"{caution}{status} {symbol}: 終値{int(close)}円 (時価:{int(mkt_cap/100000000)}億 / 業種:{sector})"
    except:
        return None

def main():
    print("--- adoGEM流スキャナー起動 (ETF/REIT除外設定) ---")
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

    if results:
        msg = MIMEMultipart()
        msg['Subject'] = f"【的中】adoGEM流 厳格下半身リスト({len(results)}件)"
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
            print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
