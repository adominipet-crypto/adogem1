import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

# --- 1. 環境変数の設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    """adoGEM流：究極の精鋭判定ロジック"""
    s = int(symbol)
    # ETF・REIT関連（1300-1699, 8950-8989）を高速スキップ
    if 1300 <= s <= 1699: return None 
    if 8950 <= s <= 8989: return None 

    # 通信負荷を抑え、2000番以降の「No data」エラーを防ぐための待機
    time.sleep(0.1)

    try:
        ticker = yf.Ticker(f"{symbol}.T")
        # データ取得のリトライ処理（最大2回）
        df = ticker.history(period="70d")
        if df.empty or len(df) < 60:
            return None
            
        # 出来高フィルター（5万株未満は除外）
        if df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        close, open_p = last['Close'], last['Open']
        ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
        ma60_prev = df.iloc[-2]['MA60']

        # --- adoGEM流 厳格フィルター ---
        if close <= open_p: return None # 陽線必須
        if not (open_p < ma5 < close): return None # 5日線またぎ（下半身）
        if ma60 < ma60_prev: return None # 60日線が上向きであること

        # --- 【強化】直近高値フィルター（戻り・勢い判定） ---
        # 過去5営業日の最高値を取得。これを超えていない（戻しが甘い）なら除外
        recent_5d_high = df['High'].iloc[-6:-1].max()
        if close < recent_5d_high:
            return None

        # 天井圏回避：過去70日最高値の5%以内なら「上がりきった」と判断し除外
        max_high_70d = df['High'].max()
        if close >= (max_high_70d * 0.95):
            return None

        # --- 判定合格後：詳細情報取得 ---
        info = ticker.info
        mkt_cap = info.get('marketCap', 0)
        
        # 時価総額0はエラーデータとして排除
        if mkt_cap == 0:
            return None

        sector = info.get('sector', '不明')
        caution = "★仕手注意 " if 0 < mkt_cap < 10000000000 else ""
        is_ppp = ma5 > ma20 > ma60
        status = "★PPP" if is_ppp else ""
        
        return f"{caution}{status} {symbol}: 終値{int(close)}円 (時価:{int(mkt_cap/100000000)}億 / 業種:{sector})"
    except:
        return None

def main():
    print("--- adoGEM流スキャナー：全コード監視・確実報告モード ---")
    results = [] 
    # 1300から9999まで全チェック
    codes = [str(i) for i in range(1300, 10000)]
    
    start_time = time.time()
    
    for i, symbol in enumerate(codes):
        res = analyze_stock(symbol)
        if res:
            print(f"【的中】: {res}")
            results.append(res)
        
        # 進行状況がわかるようログを表示
        if i % 100 == 0:
            elapsed = int(time.time() - start_time)
            print(f"スキャン中... {symbol} (経過: {elapsed}秒)")

    # --- メール作成・送信処理 ---
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL

    if results:
        msg['Subject'] = f"【厳選】adoGEM流 究極リスト({len(results)}件)"
        body = "本日の adoGEM流 厳選銘柄です。直近高値を抜けた勢いのある銘柄に絞っています：\n\n" + "\n".join(results)
    else:
        # 的中なしでも報告を送る
        msg['Subject'] = "【報告】adoGEM流 スキャン完了（対象なし）"
        body = "全銘柄をスキャンしましたが、本日は「adoGEM流」の厳しい基準をクリアする銘柄はありませんでした。\n「休むも相場」です。"

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("スキャン完了：メールを送信しました。")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
