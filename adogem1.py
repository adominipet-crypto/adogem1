import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import random

# --- 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """adoGEM流：実体割り込み厳格判定 ＋ 安定スキャン"""
    s = int(symbol)
    if 1300 <= s <= 1699: return None 
    if 8950 <= s <= 8989: return None 

    # 【重要】サーバー制限回避のため、ランダムな待機時間を挿入
    time.sleep(random.uniform(0.1, 0.3))

    try:
        ticker = yf.Ticker(f"{symbol}.T")
        # リトライ回数を増やし、失敗時は長く待機する
        df = None
        for attempt in range(3):
            df = ticker.history(period="70d")
            if not df.empty: break
            time.sleep(1.0 * (attempt + 1))

        if df is None or df.empty or len(df) < 60:
            return None
            
        if df['Volume'].iloc[-1] < 50000: return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close, open_p = last['Close'], last['Open']
        ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
        close_prev, ma5_prev = prev['Close'], prev['MA5']
        ma60_prev = prev['MA60']

        # --- adoGEM流：削除フィルター ---
        if close <= open_p: return None # 陰線削除
        if not (open_p < ma5 < close): return None # 5日線またぎ（下半身）のみ

        # 【追加】実体割り込み厳守 (3110削除)
        # 前日の終値が実体で5日線を割っていない（強い上昇中のヒゲタッチ）は削除
        if close_prev >= ma5_prev:
            return None

        if ma60 < ma60_prev: return None # 60日線が右肩下がりなら削除

        # 勢い判定（直近5日間の高値を抜けているか）
        recent_5d_high = df['High'].iloc[-6:-1].max()
        if close < recent_5d_high: return None
        
        # 天井圏回避 (70日高値から5%以内なら削除)
        max_high_70d = df['High'].max()
        if close >= (max_high_70d * 0.95): return None

        # 詳細取得
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
    print("--- adoGEM流スキャナー：9999完走保証版 起動 ---")
    results = [] 
    codes = [str(i) for i in range(1300, 10000)]
    
    start_time = time.time()
    for i, symbol in enumerate(codes):
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】: {res}")
            results.append(res)
        
        if i % 100 == 0:
            elapsed = int(time.time() - start_time)
            print(f"現在 {symbol} 付近をチェック中... (経過: {elapsed}秒)")

    # 的中なし報告メール送信
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    if results:
        msg['Subject'] = f"【厳選】adoGEM流 究極リスト({len(results)}件)"
        body = "\n".join(results)
    else:
        msg['Subject'] = "【報告】adoGEM流 スキャン完了（的中なし）"
        body = "全銘柄スキャンしましたが、adoGEM流の基準を満たす「実体割り込み後」の銘柄はありませんでした。"

    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("報告完了")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
