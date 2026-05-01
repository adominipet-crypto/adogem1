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

def analyze_batch(symbols):
    """adoGEM流：一括取得＆実体割り込み厳格判定"""
    batch_results = []
    # ETF/REIT除外
    tickers = [f"{s}.T" for s in symbols if not (1300 <= int(s) <= 1699 or 8950 <= int(s) <= 8989)]
    
    if not tickers:
        return batch_results

    try:
        # 一括ダウンロード（通信回数を1/100に減らし、制限を回避）
        data = yf.download(tickers, period="70d", interval="1d", group_by='ticker', threads=True, progress=False)
        
        for t_str in tickers:
            try:
                # 個別銘柄データの抽出と欠損値削除
                df = data[t_str].dropna()
                symbol = t_str.replace(".T", "")
                
                if df.empty or len(df) < 60:
                    continue
                
                # 出来高フィルター（5万株未満は削除）
                if df['Volume'].iloc[-1] < 50000:
                    continue

                # 指標計算
                df['MA5'] = df['Close'].rolling(window=5).mean()
                df['MA20'] = df['Close'].rolling(window=20).mean()
                df['MA60'] = df['Close'].rolling(window=60).mean()

                last = df.iloc[-1]
                prev = df.iloc[-2]
                close, open_p = last['Close'], last['Open']
                ma5, ma20, ma60 = last['MA5'], last['MA20'], last['MA60']
                close_prev, ma5_prev, ma60_prev = prev['Close'], prev['MA5'], prev['MA60']

                # --- adoGEM流：削除条件（フィルター） ---
                
                # 1. 陽線でないなら削除
                if close <= open_p: continue 
                
                # 2. 5日線またぎ（下半身）でないなら削除
                if not (open_p < ma5 < close): continue 
                
                # 3. 【重要：3110対策】前日終値が実体で5日線を割っていないなら削除
                # ヒゲで触れただけの強いトレンドは「技」の形ではないため排除
                if close_prev >= ma5_prev:
                    continue

                # 4. 60日線が下向きなら削除
                if ma60 < ma60_prev: continue 

                # 5. 直近5日間の最高値を超えていない（勢い不足）なら削除
                recent_5d_high = df['High'].iloc[-6:-1].max()
                if close < recent_5d_high: continue

                # 6. 天井圏（最高値の5%以内）なら削除
                max_high_70d = df['High'].max()
                if close >= (max_high_70d * 0.95): continue

                # 合格銘柄の判定
                is_ppp = ma5 > ma20 > ma60
                status = "★PPP" if is_ppp else ""
                batch_results.append(f"{status} {symbol}: 終値{int(close)}円")

            except Exception:
                continue
    except Exception as e:
        print(f"バッチエラー: {e}")
    
    return batch_results

def main():
    print("--- adoGEM流：一括高速スキャナー（9999完走保証版） ---")
    all_results = []
    # 1300から9999まで全対象
    codes = [str(i) for i in range(1300, 10000)]
    
    # 100銘柄ずつまとめてリクエスト
    batch_size = 100
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i+batch_size]
        print(f"スキャン中: {batch[0]} - {batch[-1]}")
        
        hits = analyze_batch(batch)
        all_results.extend(hits)
        
        # 通信間隔の調整（2秒待機）
        time.sleep(2)

    # --- 的中報告メール送信 ---
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL

    if all_results:
        msg['Subject'] = f"【厳選】adoGEM流 究極リスト({len(all_results)}件)"
        body = "本日の adoGEM流 厳選銘柄です（実体割り込み厳格判定済み）：\n\n" + "\n".join(all_results)
    else:
        # 的中なし報告
        msg['Subject'] = "【報告】adoGEM流 スキャン完了（対象なし）"
        body = "全銘柄をスキャンしましたが、adoGEM流の基準を満たす銘柄は見つかりませんでした。\n「休むも相場」です。"

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("スキャン完了、報告メールを送信しました。")
    except Exception as e:
        print(f"メールエラー: {e}")

if __name__ == "__main__":
    main()
