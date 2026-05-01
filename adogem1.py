import pandas_datareader.data as web
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import random
from datetime import datetime, timedelta

# --- 設定エリア ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """adoGEM流：Stooq経由での精査ロジック"""
    s = int(symbol)
    # ETF/REITなどの除外設定
    if 1300 <= s <= 1699 or 8950 <= s <= 8989:
        return None

    try:
        # 通信制限回避のためのランダム待機（重要）
        time.sleep(random.uniform(0.5, 1.2))
        
        # Stooqからデータを取得（日本株は末尾に .JP）
        end = datetime.now()
        start = end - timedelta(days=100)
        df = web.DataReader(f"{symbol}.JP", 'stooq', start, end)
        
        # Stooqのデータは降順（新しい順）で届くため昇順に入れ替え
        df = df.sort_index()

        if df is None or df.empty or len(df) < 60:
            return None
        
        # 出来高フィルター（Stooqの単位に注意）
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        close, open_p, ma5 = last['Close'], last['Open'], last['MA5']
        close_prev, ma5_prev = prev['Close'], prev['MA5']
        ma60, ma60_prev = last['MA60'], prev['MA60']

        # --- adoGEM流：削除（フィルター）条件 ---
        
        # 1. 陽線でないなら削除
        if close <= open_p: return None 
        
        # 2. 終値が5日線をまたいでいないなら削除
        if not (open_p < ma5 < close): return None 
        
        # 3. 【3110対策】前日終値が実体で5日線を割っていないなら削除
        # ヒゲだけで触れた強いトレンドを「初動」と勘違いしないための鉄則です。
        if close_prev >= ma5_prev:
            return None
        
        # 4. 60日線が下向きなら削除
        if ma60 < ma60_prev: return None 

        # 5. 直近5日間の最高値を更新していないなら削除
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return None
        
        # 6. 天井圏判定（最高値の5%以内なら削除）
        if close >= (df['High'].max() * 0.95): return None

        # 合格判定
        is_ppp = ma5 > last['MA20'] > ma60
        return f"{'★PPP ' if is_ppp else ''}{symbol}: {int(close)}円"
    except Exception:
        return None

def main():
    print("--- adoGEM流：pandas_datareader(Stooq)モード起動 ---")
    all_results = []
    codes = [str(i) for i in range(1300, 10000)]
    
    # 全銘柄を丁寧にスキャン
    for i, symbol in enumerate(codes):
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】{res}")
            all_results.append(res)
        
        # 進捗表示
        if i % 100 == 0:
            print(f"進捗: {symbol} 付近を精査中...")

    # --- 報告メール送信（的中なしでも送信） ---
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    if all_results:
        msg['Subject'] = f"【厳選】adoGEM流 リスト({len(all_results)}件)"
        body = "Stooq経由での精査が完了しました（実体割り込み厳守）：\n\n" + "\n".join(all_results)
    else:
        msg['Subject'] = "【報告】adoGEM流 スキャン完了"
        body = "9999番まで全銘柄を精査しましたが、現在「理想の初動」にある銘柄はありませんでした。"

    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("完了報告を送信しました。")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
