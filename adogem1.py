import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

# --- 設定エリア ---
SYMBOLS_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tv0syu00000011xl-att/data_j.xls"
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
RECEIVER_EMAIL = SENDER_EMAIL 

def get_tosho_symbols():
    try:
        df = pd.read_excel(SYMBOLS_URL)
        # コードが5桁（例: 13010）の場合があるため、4桁に修正
        df['コード'] = df['コード'].astype(str).str[:4]
        # 銘柄名と時価総額判定用の市場区分を取得
        return df[['コード', '銘柄名', '市場・商品区分']]
    except Exception as e:
        print(f"銘柄リスト取得失敗: {e}")
        return pd.DataFrame()

def analyze_stock(symbol, name, market_cat):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        # 過去70日分のデータを取得（乖離率やPPP判定のため少し長めに）
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
        low = last['Low']
        ma5 = last['MA5']
        ma20 = last['MA20']
        ma60 = last['MA60']

        # --- 相葉流・厳選ロジック ---

        # 1. 陽線判定（あなたが指摘した最重要ポイント）
        is_yang = close > open_p
        
        # 2. 下半身判定（実体が半分以上抜けているか）
        body_mid = (open_p + close) / 2
        is_kahanshin = close > ma5 and body_mid < ma5

        # 3. 上げすぎ・乖離率チェック（9042対策）
        # 20日線から5%以上離れていたら「上げすぎ」とみなす
        kairi_20 = (close - ma20) / ma20
        is_not_overextended = kairi_20 < 0.05 

        # 4. PPP（パンパパン）判定
        is_ppp = ma5 > ma20 > ma60

        # 条件合致の判定
        if is_yang and is_kahanshin and is_not_overextended:
            # 時価総額の簡易ラベル付け（info取得は重いので市場区分で代用）
            label = "【大型】" if "プライム" in market_cat else "【中小型】"
            
            # PPPなら星を付ける
            star = "★PPP" if is_ppp else ""
            
            # 特定銘柄への注釈
            note = " ★要チェック" if symbol == "9145" else ""
            
            return f"{label}{star}: {symbol} {name}{note}"
        
        return None

    except:
        return None

def send_email(content):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECEIVER_EMAIL
    msg['Subject'] = "【adoGEM流】真・厳選レポート"
    
    body = "相葉流ロジック（陽線・下半身・乖離率制限）に合致した銘柄です：\n\n" + content
    msg.attach(MIMEText(body, 'plain'))
    
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)

def main():
    symbols_df = get_tosho_symbols()
    results = []
    
    print("スキャン開始...")
    for _, row in symbols_df.iterrows():
        res = analyze_stock(row['コード'], row['銘柄名'], row['市場・商品区分'])
        if res:
            results.append(res)
            print(f"ヒット: {res}")
        # 500エラー対策の待機
        time.sleep(1.2)
    
    if results:
        send_email("\n".join(results))
        print("Done. Email sent.")
    else:
        print("合致銘柄なし")

if __name__ == "__main__":
    main()
