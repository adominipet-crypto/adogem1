import yfinance as yf
import pandas as pd
import time
import smtplib
import os
from email.mime.text import MIMEText
from email.utils import formatdate

def send_email(body_text):
    from_addr = os.environ.get('EMAIL_ADDRESS')
    password = os.environ.get('EMAIL_PASSWORD')
    if not from_addr or not password:
        print("メール設定未完了のためスキップします。")
        return
    msg = MIMEText(body_text)
    msg['Subject'] = "【adoGEM流】本日の抽出結果"
    msg['From'] = from_addr
    msg['To'] = from_addr
    msg['Date'] = formatdate(localtime=True)
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(from_addr, password)
        server.send_message(msg)
        server.quit()
        print("Gmail送信成功！")
    except Exception as e:
        print(f"送信失敗: {e}")

def get_jpx_list():
    try:
        url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
        df = pd.read_excel(url)
        target = ['プライム（内国株式）', 'スタンダード（内国株式）', 'グロース（内国株式）']
        return df[df['市場・商品区分'].isin(target)]
    except Exception as e:
        print(f"リスト取得失敗: {e}")
        return pd.DataFrame()

def check_aibaryu(ticker, name):
    try:
        stock = yf.Ticker(f"{ticker}.T")
        info = stock.info
        m_cap = info.get('marketCap', 0)
        if m_cap < 10000000000: return None
        if m_cap >= 100000000000: cap_label = "【大型 1000億以上】"
        elif m_cap <= 30000000000: cap_label = "【300億未満】"
        else: cap_label = "【中型 300億以上】"
        df = stock.history(period="2y")
        if len(df) < 300: return None
        close = df['Close']
        ma5 = close.rolling(5).mean()
        ma20 = close.rolling(20).mean()
        ma60 = close.rolling(60).mean()
        ma100 = close.rolling(100).mean()
        ma300 = close.rolling(300).mean()
        now_c, now_o, pre_c = close.iloc[-1], df['Open'].iloc[-1], close.iloc[-2]
        now_ma5 = ma5.iloc[-1]
        is_kahanshin = (now_c > now_o) and (pre_c < now_ma5 < now_c) and ((now_o + now_c)/2 > now_ma5)
        is_ppp = (ma5.iloc[-1] > ma20.iloc[-1] > ma60.iloc[-1] > ma100.iloc[-1] > ma300.iloc[-1])
        if is_kahanshin:
            sig = "★PPP" if is_ppp else "下半身"
            return f"{cap_label}{sig}: {ticker} {name} (時価総額: {m_cap // 100000000}億)"
        return None
    except: return None

if __name__ == "__main__":
    print("スキャン開始...")
    df_list = get_jpx_list()
    results = []
    for i, (idx, row) in enumerate(df_list.iterrows()):
        res = check_aibaryu(row['コード'], row['銘柄名'])
        if res:
            print(f"サイン: {res}")
            results.append(res)
        time.sleep(1.2)
        if i > 0 and i % 50 == 0:
            print(f"{i} 銘柄完了...")
            time.sleep(15)
    if results:
        send_email("\n".join(results))
    print("全工程終了")
