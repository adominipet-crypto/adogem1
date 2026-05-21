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

stats = {
    "total_fetched": 0,
    "pass_volume": 0,
    "pass_kahanshin": 0,
    
    "pass_tame": 0,
    "list_tame": [],
    
    "pass_ma60_up": 0,
    "list_ma60_up": [],
    
    "pass_trend_align": 0,
    "list_trend_align": [],
    
    "pass_upper_shadow": 0,
    "list_upper_shadow": [],
    
    "pass_new_high": 0,
    "list_new_high": [],
    
    "pass_ceiling_avoid": 0,
    "list_ceiling_avoid": [],
    
    "★PPP": 0,
    "★PPP(Short)": 0,
    "normal_detect": 0
}

def analyze_stock(symbol):
    try:
        ticker = f"{symbol}.T"
        stock = yf.Ticker(ticker)
        df = stock.history(period="2y", timeout=10)
        
        if df is None or df.empty:
            return "NOT_FOUND"
        
        if len(df) < 100:
            return "SHORT_DATA"
        
        stats["total_fetched"] += 1

        # 1. 出来高フィルター
        if df['Volume'].iloc[-1] < 50000:
            return "SKIP"
        stats["pass_volume"] += 1

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
        
        close, open_p, high = today['Close'], today['Open'], today['High']
        ma5_today = today['MA5']
        ma20_today = today['MA20']
        ma60_today = today['MA60']
        ma100_today = today['MA100']
        ma300_today = today['MA300']
        ma60_yest = yest['MA60']
        ma100_yest = yest['MA100']

        ppp_label = ""
        if ma300_today is not None and (ma5_today > ma20_today > ma60_today > ma100_today > ma300_today):
            ppp_label = "★PPP "
        elif ma300_today is None and (ma5_today > ma20_today > ma60_today > ma100_today):
            ppp_label = "★PPP(Short) "
            
        stock_text = f"■ {symbol} | {int(close)}円"

        # 2. 下半身 ＆ 当日陽線
        if not (ma5_today < close) or close <= open_p: return "SKIP" 
        body_midpoint = open_p + (close - open_p) * 0.5
        if ma5_today > body_midpoint: return "SKIP"
        stats["pass_kahanshin"] += 1

        # 3. 2営業日前「溜め」判定
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["pass_tame"] += 1
        stats["list_tame"].append(f"  3 {ppp_label}{stock_text}")

        # 4. 中期（60日線）右肩上がり
        if ma60_today <= ma60_yest: return "SKIP" 
        stats["pass_ma60_up"] += 1
        stats["list_ma60_up"].append(f"  4 {ppp_label}{stock_text}")

        # 長期トレンド同期
        if ma100_today <= ma100_yest: return "SKIP"
        stats["pass_trend_align"] += 1
        stats["list_trend_align"].append(f"  長 {ppp_label}{stock_text}")

        # 上ヒゲ選別
        body_length = close - open_p
        upper_shadow_length = high - close
        if body_length > 0:
            if upper_shadow_length >= (body_length * 1.5): return "SKIP"
        stats["pass_upper_shadow"] += 1
        stats["list_upper_shadow"].append(f"  ヒ {ppp_label}{stock_text}")

        # 5. 5日新高値更新
        recent_high = df['High'].iloc[-6:-1].max()
        if close < recent_high: return "SKIP"
        stats["pass_new_high"] += 1
        stats["list_new_high"].append(f"  5 {ppp_label}{stock_text}")

        # 6. 天井圏の回避フィルター
        max_100 = df['High'].iloc[-100:].max()
        if close >= (max_100 * 0.97): return "SKIP"
        stats["pass_ceiling_avoid"] += 1
        stats["list_ceiling_avoid"].append(f"  最終 {ppp_label}{stock_text}")

        if "★PPP " in ppp_label: stats["★PPP"] += 1
        elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
        else: stats["normal_detect"] += 1

        return f"{ppp_label}{stock_text}"

    except Exception as e:
        return "ERROR"

def get_target_symbols(start, end):
    try:
        url = "https://www.jpx.co.jp/markets/statistics-options/data/files/data_j.xls"
        tables = pd.read_html(url)
        df_jpx = tables[0]
        df_jpx.columns = df_jpx.iloc[0]
        df_jpx = df_jpx[1:]
        df_jpx['コード'] = df_jpx['コード'].astype(str)
        df_jpx['市場・商品区分'] = df_jpx['市場・商品区分'].astype(str)
        df_stocks = df_jpx[df_jpx['市場・商品区分'].str.contains('内国株式')]
        def filter_range(code): return str(start) <= code[:4] < str(end)
        return sorted(df_stocks[df_stocks['コード'].apply(filter_range)]['コード'].unique().tolist())
    except Exception as e:
        return [str(i) for i in range(start, end)]

def main():
    if len(sys.argv) > 2: start_range, end_range = int(sys.argv[1]), int(sys.argv[2])
    else: start_range, end_range = 7003, 10000
    
    symbols = get_target_symbols(start_range, end_range)
    total_count = len(symbols)
    
    all_results = []
    error_count = not_found_count = short_data_count = skip_count = 0
    
    for symbol in symbols:
        res = analyze_stock(symbol)
        if res == "ERROR": error_count += 1
        elif res == "NOT_FOUND": not_found_count += 1
        elif res == "SHORT_DATA": short_data_count += 1
        elif res == "SKIP": skip_count += 1
        else: all_results.append(res)
        time.sleep(0.50)

    scanned_count = total_count - error_count - not_found_count - short_data_count

    def make_list_str(target_list):
        return "\n".join(target_list) + "\n\n" if target_list else "(該当なし)\n\n"

    # 📊 各条件の詳細リスト部分を後半へ独立して結合
    detail_lists = (
        "【3. 2営業日前「溜め」判定 銘柄】\n"
        f"{make_list_str(stats['list_tame'])}"
        "【4. 60日移動平均線 右肩上がり 銘柄】\n"
        f"{make_list_str(stats['list_ma60_up'])}"
        "【[新] 長期トレンド同期(100MA上昇) 銘柄】\n"
        f"{make_list_str(stats['list_trend_align'])}"
        "【[新] 上ヒゲ選別(1.5倍未満) 銘柄】\n"
        f"{make_list_str(stats['list_upper_shadow'])}"
        "【5. 5日新高値更新 銘柄】\n"
        f"{make_list_str(stats['list_new_high'])}"
        "【6. 天井圏回避 (100日高値97%未満) 銘柄】\n"
        f"{make_list_str(stats['list_ceiling_avoid'])}"
    )

    # 📊 前半は数値一覧のみですっきり表示
    cond_report = (
        "【通過銘柄】\n"
        f" 1. 出来高選別 (5万株) : {stats['pass_volume']}\n"
        f" 2. 下半身(実体50%) ＆ 当日陽線 : {stats['pass_kahanshin']}\n"
        f" 3. 2営業日前「溜め」判定 : {stats['pass_tame']}\n"
        f" 4. 60日移動平均線 右肩上がり : {stats['pass_ma60_up']}\n"
        f" [新] 長期トレンド同期(100MA上昇) : {stats['pass_trend_align']}\n"
        f" [新] 上ヒゲ選別(1.5倍未満) : {stats['pass_upper_shadow']}\n"
        f" 5. 5日新高値更新 : {stats['pass_new_high']}\n"
        f" 6. 天井圏回避 (100日高値97%未満) : {stats['pass_ceiling_avoid']}\n\n"
        "【選定内訳】\n"
        f"  - ★PPP 合致       : {stats['★PPP']} 銘柄\n"
        f"  - ★PPP(Short) 合致: {stats['★PPP(Short)']} 銘柄\n"
        f"  - 通常選定 合致    : {stats['normal_detect']} 銘柄\n"
    )

    subject = f"📊 adoGEM 選定報告 ({start_range}-{end_range}) 合致:{len(all_results)}件"
    body = (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "   adoGEM 戦略フィルター：選定銘柄レポート\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"総スキャン対象 : {total_count}\n"
        f"正常精査銘柄数 : {scanned_count}\n\n"
        f"{cond_report}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "   各フィルター通過銘柄 詳細リスト\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{detail_lists}"
        "以下の銘柄において、設定された全条件の合致を確認。\n"
        "（★PPPマーク付きは超強力トレンド銘柄）\n"
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
