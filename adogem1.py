import yfinance as yf
import pandas as pd
import datetime
import smtplib
from email.mime.text import MIMEText
import os
import time

# --- 設定 ---
EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def send_email(subject, body):
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = EMAIL_ADDRESS
    msg['To'] = EMAIL_ADDRESS
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as smtp:
            smtp.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            smtp.send_message(msg)
        print("Email sent successfully")
    except Exception as e:
        print(f"Failed to send email: {e}")

def get_tosho_list():
    # 東証から上場銘柄一覧を取得
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    df = pd.read_excel(url)
    return df

def scan_stocks():
    df_tosho = get_tosho_list()
    results = []
    
    # 内国株（プライム・スタンダード・グロース）を対象
    stocks = df_tosho[df_tosho['市場・商品区分'].str.contains('プライム|スタンダード|グロース', na=False)]
    
    print(f"スキャン開始... 対象: {len(stocks)} 銘柄")
    
    count = 0
    for index, row in stocks.iterrows():
        code = str(row['コード']) + ".T"
        name = row['銘柄名']
        
        count += 1
        if count % 100 == 0:
            print(f"{count} 銘柄完了...")
            
        try:
            ticker = yf.Ticker(code)
            # 6ヶ月分のデータを取得
            hist = ticker.history(period="6mo")
            if len(hist) < 100:
                continue

            # --- 1. 出来高フィルター（9059対策） ---
            # 直近5日間の平均出来高が50,000株未満なら除外
            avg_volume = hist['Volume'].tail(5).mean()
            if avg_volume < 50000:
                continue

            # 時価総額を取得
            info = ticker.info
            mcap = info.get('marketCap', 0)
            if mcap == 0: continue
            
            # ラベル分け（具体的な数字は出力しない）
            mcap_label = ""
            if mcap >= 1000 * 10**8:
                mcap_label = "【大型 1000億以上】"
            elif mcap >= 300 * 10**8:
                mcap_label = "【中型 300億以上】"
            else:
                mcap_label = "【300億未満】"

            # 指標計算
            close = hist['Close']
            ma5 = close.rolling(window=5).mean()
            ma20 = close.rolling(window=20).mean()
            ma60 = close.rolling(window=60).mean()

            last_close = close.iloc[-1]
            prev_close = close.iloc[-2]
            last_ma5 = ma5.iloc[-1]
            prev_ma5 = ma5.iloc[-2]
            last_ma20 = ma20.iloc[-1]
            last_ma60 = ma60.iloc[-1]
            
            # 下半身判定
            is_kahanshin = prev_close < prev_ma5 and last_close > last_ma5
            # PPP判定
            is_ppp = last_ma5 > last_ma20 > last_ma60

            # --- 2. 上昇日数カウント＆陰線フィルター（9042対策） ---
            days_above_ma5 = 0
            for i in range(1, 15):
                if close.iloc[-i] > ma5.iloc[-i]:
                    days_above_ma5 += 1
                else:
                    break
            
            # 上昇6日目以降で、当日が陰線（または前日比マイナス）なら除外
            if days_above_ma5 >= 6 and last_close <= prev_close:
                continue

            # --- 3. 9145 特別タグ ---
            extra_tag = ""
            if "9145" in code:
                extra_tag = " ★要チェック"

            # 結果まとめ
            if is_kahanshin:
                tag = "★PPP: " if is_ppp else "下半身: "
                res_str = f"{mcap_label}{tag}{code.replace('.T', '')} {name}{extra_tag}"
                results.append(res_str)
                
            time.sleep(1.2) # サーバー負荷軽減
            
        except Exception:
            continue

    if results:
        send_email("【adoGEM流】本日の抽出結果", "\n".join(results))
        print("Done. Email sent.")
    else:
        print("条件に合う銘柄はありませんでした。")

if __name__ == "__main__":
    scan_stocks()
