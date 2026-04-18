import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time

# --- 設定エリア ---
# 最新の東証銘柄リストURL（2026年時点の統計用URL）
SYMBOLS_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tv0syu00000011xl-att/data_j.xls"
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
RECEIVER_EMAIL = SENDER_EMAIL 

def get_tosho_symbols():
    try:
        # User-Agentを設定してアクセス拒否を回避
        headers = {'User-Agent': 'Mozilla/5.0'}
        df = pd.read_excel(SYMBOLS_URL)
        df['コード'] = df['コード'].astype(str).str[:4]
        return df[['コード', '銘柄名', '市場・商品区分']]
    except Exception as e:
        print(f"銘柄リスト取得失敗: {e}")
        # 取得失敗時は空のデータフレームを返し、後続処理を安全に終了させる
        return pd.DataFrame()

def analyze_stock(symbol, name, market_cat):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        if len(df) < 60: return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        
        close = last['Close']
        open_p = last['Open']
        ma5 = last['MA5']
        ma20 = last['MA20']
        ma60 = last['MA60']

        # --- 相葉流・厳選ロジック ---

        # 1. 陽線判定（陰線は除外）
        is_yang = close > open_p
        
        # 2. 下半身判定（終値が5日線を上回る ＆ 実体が半分以上抜けている）
        body_mid = (open_p + close) / 2
        is_kahanshin = close > ma5 and body_mid < ma5

        # 3. 乖離率チェック（高値掴み防止：9042対策）
        # 20日線から5%以上離れていたら「上げすぎ」として除外
        kairi_20 = (close - ma20) / ma20
        is_not_overextended = kairi_20 < 0.05 

        # 4. PPP（パンパパン）判定
        is_ppp = ma5 > ma20 > ma60

        # 全条件に合致した場合のみ抽出
        if is_yang and is_kahanshin and is_not_overextended:
            label = "【大型】" if "プライム" in str(market_cat) else "【中小型】"
            star = "★PPP" if is_ppp else ""
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
    
    header_text = "相葉流ロジック（陽線・下半身・乖離率5%未満）合致銘柄：\n\n"
    msg.attach(MIMEText(header_text + content, 'plain'))
    
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
        print("Email sent successfully.")
    except Exception as e:
        print(f"メール送信失敗: {e}")

def main():
    symbols_df = get_tosho_symbols()
    if symbols_df.empty:
        print("スキャン対象がないため終了します。")
        return

    results = []
    print("スキャン開始（陽線・低乖離に限定）...")
    
    # 銘柄数を制限してテストしたい場合は symbols_df.head(100) などに調整可能
    for _, row in symbols_df.iterrows():
        res = analyze_stock(row['コード'], row['銘柄名'], row['市場・商品区分'])
        if res:
            results.append(res)
            print(f"ヒット: {res}")
        time.sleep(1.2) # サーバー負荷対策
    
    if results:
        send_email("\n".join(results))
    else:
        print("本日の条件（陽線下半身かつ低乖離）に合う銘柄はありませんでした。")

if __name__ == "__main__":
    main()
