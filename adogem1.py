import yfinance as yf
import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import time
import sys

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

def analyze_stock(symbol):
    try:
        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y", timeout=10)
        
        if df is None or df.empty:
            return "NOT_FOUND"
        
        if len(df) < 60:
            return "SHORT_DATA"
        
        if df['Volume'].iloc[-1] < 50000:
            return "SKIP"

        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        df['MA100'] = df['Close'].rolling(window=100).mean()
        
        if len(df) >= 300:
            df['MA300'] = df['Close'].rolling(window=300).mean()
        else:
            df['MA300'] = None
        
        today = df.iloc[-1]
        yest = df.iloc[-2]
        yest2 = df.iloc[-3]
        
        close, open_p = today['Close'], today['Open']
        ma5_today = today['MA5']
        ma20_today = today['MA20']
        ma60_today = today['MA60']
        ma100_today = today['MA100']
        ma300_today = today['MA300']
        ma60_yest = yest['MA60']

        if not (open_p < ma5_today < close) or close <= open_p: return "SKIP" 
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        if ma60_today <= ma60_yest: return "SKIP" 
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return "SKIP"
        max_100 = df['High'].iloc[-100:].max()
        if close >= (max_100 * 0.95): return "SKIP"

        if ma300_today is not None:
            if (ma5_today > ma20_today > ma60_today > ma100_today > ma300_today):
                return f"★PPP ■ 銘柄コード: {symbol} | 終値: {int(close)}円"
        else:
            if (ma5_today > ma20_today > ma60_today > ma100_today):
                return f"★PPP(Short) ■ 銘柄コード: {symbol} | 終値: {int(close)}円"

        return f"■ 銘柄コード: {symbol} | 終値: {int(close)}円"

    except Exception as e:
        err_msg = str(e)
        if "404" in err_msg or "Not Found" in err_msg or "not found" in err_msg or "No data found" in err_msg:
            return "NOT_FOUND"
        
        print(f"[DEBUG_ERROR] {symbol}: {err_msg}")
        return "ERROR"

def get_target_symbols(start, end):
    try:
        url = "https://www.jpx.co.jp/markets/statistics-options/data/files/data_j.xls"
        tables = pd.read_html(url)
        df_jpx = tables[0]
        df_jpx.columns = df_jpx.iloc[0]
        df_jpx = df_jpx[1:]
        
        df_jpx['コード'] = df_jpx['コード'].astype(str)
        
        def filter_range(code):
            prefix = code[:4]
            return str(start) <= prefix < str(end)
            
        targets = df_jpx[df_jpx['コード'].apply(filter_range)]['コード'].unique().tolist()
        return sorted(targets)
    except Exception as e:
        print(f"JPX銘柄リスト取得失敗、連番フォールバックを実行: {e}")
        return [str(i) for i in range(start, end)]

def main():
    if len(sys.argv) > 2:
        start_range = int(sys.argv[1])
        end_range = int(sys.argv[2])
    else:
        start_range = 7003
        end_range = 10000
    
    print(f"--- Fetching Master Stock List from JPX ({start_range}-{end_range}) ---")
    symbols = get_target_symbols(start_range, end_range)
    total_count = len(symbols)
    print(f"--- adoGEM Strategy Scanner Running for {total_count} valid stocks ---")
    
    all_results = []
    error_count = 0
    not_found_count = 0
    short_data_count = 0
    skip_count = 0
    
    for symbol in symbols:
        res = analyze_stock(symbol)
        if res == "ERROR":
            error_count += 1
        elif res == "NOT_FOUND":
            not_found_count += 1
        elif res == "SHORT_DATA":
            short_data_count += 1
        elif res == "SKIP":
            skip_count += 1
        else:
            all_results.append(res)
            print(f"[DETECTED] {res}")
        time.sleep(0.50)

    scanned_count = total_count - error_count - not_found_count - short_data_count

    if all_results:
        subject = f"🔔【重要】選定銘柄の検出報告 ({start_range}-{end_range})"
        body = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "   adoGEM 戦略フィルター：選定銘柄レポート\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"総スキャン対象 : {total_count} 銘柄\n"
            f"正常精査銘柄数 : {scanned_count} 銘柄\n"
            f"存在しない銘柄（欠番）: {not_found_count} 銘柄\n"
            f"期間不足銘柄数 : {short_data_count} 銘柄\n"
            f"通信等エラー数 : {error_count} 銘柄\n"
            f"条件非合致（精査無し）: {skip_count} 銘柄\n\n"
            "以下の銘柄において、設定された全条件の合致を確認しました。\n"
            "（★PPPマーク付きは超強力トレンド銘柄です）\n\n"
            + "\n".join(all_results) + "\n\n"
            "※本メールはシステムによる自動精査の結果を通知するものです。\n"
        )
    else:
        subject = f"📊 スキャン完了通知 ({start_range}-{end_range})"
        body = (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "   adoGEM 戦略フィルター：定期スキャン完了\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"総スキャン対象 : {total_count} 銘柄\n"
            f"正常精査銘柄数 : {scanned_count} 銘柄\n"
            f"存在しない銘柄（欠番）: {not_found_count} 銘柄\n"
            f"期間不足銘柄数 : {short_data_count} 銘柄\n"
            f"通信等エラー数 : {error_count} 銘柄\n"
            f"条件非合致（精査無し）: {skip_count} 銘柄\n\n"
            f"結果：精査完了 {scanned_count} 銘柄のうち、条件に合致する銘柄（精査無し）は検出されませんでした。\n"
        )

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("報告メールの送信が完了しました。")
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
