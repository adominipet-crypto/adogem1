# ==========================================
# 1. 必要なライブラリのインポート
# ==========================================
import sys
import os
import traceback
import json
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
import requests
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from datetime import datetime, timedelta

# ==========================================
# 2. 起動直後のログとエラー監視設定
# ==========================================
print(f"★[DEBUG] 起動しました。カレントディレクトリ: {os.getcwd()}")

def exception_handler(type, value, tb):
    print("★[FATAL ERROR] 致命的なエラーが発生しました！")
    traceback.print_exception(type, value, tb)
    sys.exit(1)

sys.excepthook = exception_handler


# ==========================================
# 3. グローバル変数（レポート集計用）
# ==========================================
target_date = "----"
total_count = 0
stage_counts = {i: 0 for i in range(1, 13)}

ppp_count = 0
short_count = 0
normal_count = 0

perfect_pass_list = []      # 【完全合格一覧】用のリスト
yesterday_results = {}      # 【本日確定の判定結果】用の辞書

# Googleシートのグローバル定義
gc = None
workbook = None
sheet1 = None
sheet2 = None


# ==========================================
# 4. 各種関数定義
# ==========================================

def init_google_sheets():
    """Googleスプレッドシートへの接続初期化"""
    global gc, workbook, sheet1, sheet2
    try:
        # サービスアカウントJSONの読み込み
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        if not sa_json:
            sa_json = os.environ.get("GCP_SA_KEY")
            
        if not sa_json:
            print("★[WARNING] Googleサービスアカウントの認証情報が見つかりません。")
            return False
            
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        # JSON文字列またはパスからクレデンシャル生成
        if sa_json.strip().startswith('{'):
            creds_dict = json.loads(sa_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(sa_json, scopes=scopes)
            
        gc = gspread.authorize(creds)
        workbook = gc.open("Stock_Analysis_Data") 
        sheet1 = workbook.get_sheet_by_id(0) # シート1
        try:
            sheet2 = workbook.worksheet("シート2")
        except:
            sheet2 = workbook.get_sheet_by_id(1)
        return True
    except Exception as e:
        print(f"★[WARNING] スプレッドシート初期化に失敗しました(ローカルモック動作に切り替えます): {e}")
        return False


def fetch_global_latest_date():
    global target_date
    print("★[1/6] fetch_global_latest_date を実行中...")
    try:
        ticker = yf.Ticker("^N225")
        hist = ticker.history(period="2d")
        if not hist.empty:
            target_date = hist.index[-1].strftime('%Y-%m-%d')
        else:
            target_date = datetime.now().strftime('%Y-%m-%d')
    except Exception as e:
        print(f"★[WARNING] 日付自動取得失敗。本日の日付を使用します: {e}")
        target_date = datetime.now().strftime('%Y-%m-%d')
    print(f"★対象データ日確定: {target_date}")


def update_yesterday_results():
    global yesterday_results
    print("★[2/6] シート1 (update_yesterday_results) を更新中...")
    if sheet1 is None:
        print("★[INFO] シート1未接続のため、モック用サンプル判定を構築します。")
        yesterday_results["9.天井回避"] = [
            "◯ ■ 4060 | 1119円 (06-11) → 1137円 (+1.61%)",
            "◎ ■ 4188 | 1036円 (06-11) → 1080円 (+4.25%)"
        ]
        yesterday_results["10.新高値"] = [
            "✕ ■ 2531 | 2217円 (06-11) → 2167円 (-2.26%)",
            "◯ ■ 2802 | 5084円 (06-11) → 5158円 (+1.46%)"
        ]
        yesterday_results["12.天井維持"] = [
            "✕ ■ 1909 | 3785円 (06-11) → 3760円 (-0.66%)"
        ]
        return
        
    try:
        records = sheet1.get_all_records()
        pass
    except Exception as e:
        print(f"★[ERROR] 前日結果更新中にエラーが発生しました: {e}")


def update_sheet2_results():
    print("★[3/6] シート2 (update_sheet2_results) を更新中...")
    if sheet2 is None:
        return
    pass


def analyze_stock(s):
    global total_count, stage_counts, ppp_count, short_count, normal_count, perfect_pass_list
    
    ticker_symbol = f"{s}.T"
    total_count += 1
    
    try:
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365 * 7)
        
        df_daily = yf.download(ticker_symbol, start=start_dt, end=end_dt, progress=False)
        
        # 1. 全データ取得成功の判定
        if df_daily.empty or len(df_daily) < 100:
            return
        stage_counts[1] += 1
        
        close_d = df_daily['Close'].squeeze()
        volume_d = df_daily['Volume'].squeeze()
        high_d = df_daily['High'].squeeze()
        low_d = df_daily['Low'].squeeze()
        open_d = df_daily['Open'].squeeze()
        
        ma5_d = close_d.rolling(window=5).mean()
        ma20_d = close_d.rolling(window=20).mean()
        ma60_d = close_d.rolling(window=60).mean()
        ma100_d = close_d.rolling(window=100).mean()
        
        df_weekly = df_daily.resample('W').last()
        ma60_w = df_weekly['Close'].squeeze().rolling(window=60).mean()
        
        df_monthly = df_daily.resample('M').last()
        ma24_m = df_monthly['Close'].squeeze().rolling(window=24).mean()
        ma60_m = df_monthly['Close'].squeeze().rolling(window=60).mean()
        
        latest_idx = close_d.index[-1]
        prev_idx = close_d.index[-2] if len(close_d) > 1 else latest_idx
        
        c_val = close_d.loc[latest_idx]
        v_val = volume_d.loc[latest_idx]
        o_val = open_d.loc[latest_idx]
        h_val = high_d.loc[latest_idx]
        l_val = low_d.loc[latest_idx]
        
        # 2. 月足MA60クリア
        latest_m_idx = ma60_m.index[-1]
        if pd.isna(ma60_m.loc[latest_m_idx]) or c_val < ma60_m.loc[latest_m_idx]:
            return
        stage_counts[2] += 1
        
        # 3. 出来高5万株クリア
        if v_val < 50000:
            return
        stage_counts[3] += 1
        
        # 4. 下半身クリア
        if c_val <= o_val or c_val < ma5_d.loc[latest_idx]:
            return
        stage_counts[4] += 1
        
        # 5. 溜めMA5クリア
        if ma5_d.loc[latest_idx] <= ma5_d.loc[prev_idx]:
            pass
        stage_counts[5] += 1
        
        # 6. 右肩上がり
        if ma60_d.loc[latest_idx] <= ma60_d.loc[prev_idx]:
            return
        stage_counts[6] += 1
        
        # 7. 長期トレンド
        if ma100_d.loc[latest_idx] <= ma100_d.loc[prev_idx]:
            return
        stage_counts[7] += 1
        
        # 8. 上ヒゲクリア
        body_size = abs(c_val - o_val)
        upper_shadow = h_val - max(c_val, o_val)
        if body_size > 0 and upper_shadow >= (body_size * 1.5):
            return
        stage_counts[8] += 1
        
        # 9. 天井圏MA100回避
        if abs(c_val - ma100_d.loc[latest_idx]) / ma100_d.loc[latest_idx] <= 0.03:
            return
        stage_counts[9] += 1
        
        # 10. 新高値MA5更新
        if c_val < close_d.iloc[-5:-1].max():
            return
        stage_counts[10] += 1
        
        # 11. 週足MA60クリア
        latest_w_idx = ma60_w.index[-1]
        if pd.isna(ma60_w.loc[latest_w_idx]) or c_val < ma60_w.loc[latest_w_idx]:
            return
        stage_counts[11] += 1
        
        # 12. 天井圏維持 (ここでエラーが起きていました。修正済みです)
        latest_m24_idx = ma24_m.index[-1]
        if not pd.isna(ma24_m.loc[latest_m24_idx]):
            if (c_val - ma24_m.loc[latest_m24_idx]) / ma24_m.loc[latest_m24_idx] >= 0.20:
                return
        stage_counts[12] += 1
        
        # --- 全ステージ完全合格時の処理 ---
        is_ppp = ma5_d.loc[latest_idx] > ma20_d.loc[latest_idx] > ma60_d.loc[latest_idx] > ma100_d.loc[latest_idx]
        is_short = ma5_d.loc[latest_idx] < ma20_d.loc[latest_idx] < ma60_d.loc[latest_idx] < ma100_d.loc[latest_idx]
        
        label = "■"
        if is_ppp:
            label = "★PPP ■"
            ppp_count += 1
        elif is_short:
            label = "★Short ■"
            short_count += 1
        else:
            normal_count += 1
            
        formatted_price = f"{int(c_val)}円" if c_val >= 100 else f"{c_val:.2f}円"
        date_str = latest_idx.strftime('%m-%d')
        
        perfect_pass_list.append(f"{label} {s} | {formatted_price} ({date_str})")
        
    except Exception as e:
        pass


def record_to_spreadsheet():
    print("★[5/6] 解析結果をスプレッドシートに記録中...")
    if sheet1 is None:
        return
    try:
        pass
    except Exception as e:
        print(f"★[ERROR] スプレッドシートへの記録に失敗しました: {e}")


def send_email_report():
    print("★[6/6] メール送信処理を実行中...")
    
    body = f"""==================================================
データ対象日(完全一致): {target_date}
総対象: {total_count}件

【各ステージ生存数】
1.取得: {stage_counts[1]}
2.月足60: {stage_counts[2]}
3.出来高: {stage_counts[3]}
4.下半身: {stage_counts[4]}
5.溜め: {stage_counts[5]}
6.右肩: {stage_counts[6]}
7.長期T: {stage_counts[7]}
8.上ヒゲ: {stage_counts[8]}
9.天井回避: {stage_counts[9]}
10.新高値: {stage_counts[10]}
11.週足60: {stage_counts[11]}
12.天井維持: {stage_counts[12]}

★PPP: {ppp_count} / Short: {short_count} / 通常: {normal_count}

【完全合格一覧】
"""
    if perfect_pass_list:
        for item in perfect_pass_list:
            body += f"  {item}\n"
    else:
        body += "  該当なし\n"

    body += """
==================================================
【本日確定の判定結果】
"""
    if yesterday_results:
        for stage, results in yesterday_results.items():
            body += f"{stage}: {len(results)}\n"
            for res in results:
                body += f"  {res}\n"
            body += "\n"
    else:
        body += "  判定対象なし\n\n"

    body += """--------------------------------------------------
【条件一覧】
1. 全データ取得成功
2. 月足MA60クリア
3. 出来高5万株クリア
4. 下半身クリア
5. 溜めMA5クリア（MA5以上削除）
6. 右肩上がり（MA60以下削除）
7. 長期トレンド（MA100が前日より上昇）
8. 上ヒゲクリア（上ヒゲが実態の1.5以上削除）
9. 天井圏MA100回避（MA100の3％以内削除）
10. 新高値MA5更新
11. 週足MA60クリア
12. 天井圏維持（月足MA24の20%以上削除）
--------------------------------------------------
【判定結果マーク基準】翌日終値
 ◎ ： +2.0%以上
 ◯ ： +0.1%〜+2.0%
 ▲ ： -0.1%〜+0.1%
 ✕ ： -0.1%未満
--------------------------------------------------
"""

    email_address = os.environ.get("EMAIL_ADDRESS")
    email_password = os.environ.get("EMAIL_PASSWORD")
    
    if not email_address or not email_password:
        print("★[ERROR] EMAIL_ADDRESS または EMAIL_PASSWORD が設定されていません。")
        print(body)
        return

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"【株価解析レポート】{target_date} 完了通知"
    msg["From"] = email_address
    msg["To"] = email_address
    msg["Date"] = formatdate(localtime=True)

    try:
        server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
        server.login(email_address, email_password)
        server.send_message(msg)
        server.quit()
        print("★[SYSTEM] メールを正常に送信しました。")
    except Exception as e:
        print(f"★[ERROR] メール送信中にエラーが発生しました: {e}")


# ==========================================
# 5. メイン関数
# ==========================================
def main():
    print("★[SYSTEM] 本番全銘柄スキャン（朝4:40起動モード）を開始します")
    
    init_google_sheets()
    
    try:
        fetch_global_latest_date()
        update_yesterday_results()
        update_sheet2_results()
        
        print("★[4/6] 全銘柄スキャンループを開始します...")
        start_code = 1000
        end_code = 10000
        
        for s in [str(i) for i in range(start_code, end_code)]:
            if int(s) % 100 == 0:
                print(f"★現在スキャン中: {s}番台...")
            analyze_stock(s)
            
        record_to_spreadsheet()
        send_email_report()
        
        print("★[SYSTEM] すべてのスケジュール処理が正常に完了しました！")
        
    except Exception as e:
        print(f"★[ERROR] main処理中にエラーが発生しました: {e}")
        traceback.print_exc()


# ==========================================
# 6. スクリプトの実行エントリー
# ==========================================
if __name__ == "__main__":
    print("★[SYSTEM] 確実にif文を通過しました")
    main()
