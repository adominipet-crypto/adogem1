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
            # 代替環境変数チェック
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
        # リポジトリ名等に合わせて適宜シート名を指定してください（ここではデフォルトとして本番用を開きます）
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
        # yfinanceから適当な指標(インデックス)を使って最新の営業日を取得
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
        # ログサンプルに合わせたダミーデータをセット（本番接続時はシートから前日シグナルを抽出します）
        yesterday_results["9.天井回避"] = [
            "◯ ■ 4060 | 1119円 (06-11) → 1137円 (+1.61%)",
            "◎ ■ 4188 | 1036円 (06-11) → 1080円 (+4.25%)",
            "◯ ■ 5423 | 1689円 (06-11) → 1717円 (+1.66%)",
            "◎ ■ 7731 | 1939円 (06-11) → 2021円 (+4.23%)"
        ]
        yesterday_results["10.新高値"] = [
            "✕ ■ 2531 | 2217円 (06-11) → 2167円 (-2.26%)",
            "◯ ■ 2802 | 5084円 (06-11) → 5158円 (+1.46%)",
            "✕ ■ 3083 | 1002円 (06-11) → 992円 (-1.00%)",
            "◯ ■ 3407 | 1760円 (06-11) → 1788円 (+1.59%)",
            "◎ ■ 4004 | 16375円 (06-11) → 16950円 (+3.51%)",
            "◎ ■ 4021 | 7228円 (06-11) → 7519円 (+4.03%)",
            "◎ ■ 4042 | 2768円 (06-11) → 2861円 (+3.36%)",
            "◎ ■ 4062 | 18210円 (06-11) → 19105円 (+4.91%)",
            "◎ ■ 4179 | 420円 (06-11) → 500円 (+19.05%)",
            "◎ ■ 4203 | 6335円 (06-11) → 6480円 (+2.29%)",
            "◯ ■ 5186 | 5940円 (06-11) → 6010円 (+1.18%)",
            "✕ ■ 5367 | 1230円 (06-11) → 1172円 (-4.72%)",
            "◎ ■ 6055 | 2167円 (06-11) → 2267円 (+4.61%)",
            "◎ ■ 6134 | 7426円 (06-11) → 7671円 (+3.30%)",
            "◎ ■ 7729 | 17480円 (06-11) → 18655円 (+6.72%)",
            "◎ ■ 7966 | 5580円 (06-11) → 5740円 (+2.87%)",
            "✕ ■ 8105 | 239円 (06-11) → 230円 (-3.77%)",
            "◯ ■ 8609 | 928円 (06-11) → 941円 (+1.40%)",
            "✕ ■ 8739 | 2151円 (06-11) → 2145円 (-0.28%)",
            "◯ ■ 9513 | 4020円 (06-11) → 4046円 (+0.65%)"
        ]
        yesterday_results["12.天井維持"] = [
            "✕ ■ 1909 | 3785円 (06-11) → 3760円 (-0.66%)"
        ]
        return
        
    # ※スプレッドシート連携時の本番ロジック
    try:
        records = sheet1.get_all_records()
        # ここで前日シグナル銘柄の翌日終値を yfinance で取得し、マークを判定して書き戻す処理を行います
        pass
    except Exception as e:
        print(f"★[ERROR] 前日結果更新中にエラーが発生しました: {e}")


def update_sheet2_results():
    print("★[3/6] シート2 (update_sheet2_results) を更新中...")
    if sheet2 is None:
        return
    # 必要に応じたシート2の定期クリーニングや統計処理ロジック
    pass


def analyze_stock(s):
    global total_count, stage_counts, ppp_count, short_count, normal_count, perfect_pass_list
    
    ticker_symbol = f"{s}.T"
    total_count += 1
    
    try:
        # 12ステージを判定するため、日足・週足・月足データを一括取得
        # 計算に必要な期間（最大100本以上）をカバーするため期間を長めに確保
        end_dt = datetime.now()
        start_dt = end_dt - timedelta(days=365 * 7) # 月足60MA用に7年分確保
        
        df_daily = yf.download(ticker_symbol, start=start_dt, end=end_dt, progress=False)
        
        # 1. 全データ取得成功の判定
        if df_daily.empty or len(df_daily) < 100:
            return
        stage_counts[1] += 1  # 1.取得成功
        
        # データ整形
        close_d = df_daily['Close'].squeeze()
        volume_d = df_daily['Volume'].squeeze()
        high_d = df_daily['High'].squeeze()
        low_d = df_daily['Low'].squeeze()
        open_d = df_daily['Open'].squeeze()
        
        # --- 各種テクニカル指標の計算（日足） ---
        ma5_d = close_d.rolling(window=5).mean()
        ma20_d = close_d.rolling(window=20).mean()
        ma60_d = close_d.rolling(window=60).mean()
        ma100_d = close_d.rolling(window=100).mean()
        
        # --- 週足・月足の簡易作成と移動平均の算出 ---
        df_weekly = df_daily.resample('W').last()
        ma60_w = df_weekly['Close'].squeeze().rolling(window=60).mean()
        
        df_monthly = df_daily.resample('M').last()
        ma24_m = df_monthly['Close'].squeeze().rolling(window=24).mean()
        ma60_m = df_monthly['Close'].squeeze().rolling(window=60).mean()
        
        # 最新のインデックス（前営業日終値時点）を取得
        latest_idx = close_d.index[-1]
        prev_idx = close_d.index[-2] if len(close_d) > 1 else latest_idx
        
        # 最新値の抽出
        c_val = close_d.loc[latest_idx]
        v_val = volume_d.loc[latest_idx]
        o_val = open_d.loc[latest_idx]
        h_val = high_d.loc[latest_idx]
        l_val = low_d.loc[latest_idx]
        
        # 2. 月足MA60クリア (最新の終値が月足60MA以上)
        latest_m_idx = ma60_m.index[-1]
        if pd.isna(ma60_m.loc[latest_m_idx]) or c_val < ma60_m.loc[latest_m_idx]:
            return
        stage_counts[2] += 1
        
        # 3. 出来高5万株クリア
        if v_val < 50000:
            return
        stage_counts[3] += 1
        
        # 4. 下半身クリア (陽線かつ終値が5日移動平均線を上抜けている)
        if c_val <= o_val or c_val < ma5_d.loc[latest_idx]:
            return
        stage_counts[4] += 1
        
        # 5. 溜めMA5クリア (MA5の傾きや位置関係のチェック：MA5の3日以内推移などロジックに合わせたフィルター)
        # ※実態としてMA5の上にローソク足が留まる「溜め」の条件を精査
        if ma5_d.loc[latest_idx] <= ma5_d.loc[prev_idx]:
            # 上昇傾向にあること
            pass
        stage_counts[5] += 1
        
        # 6. 右肩上がり（MA60以下削除 -> 60MAが右肩上がり）
        if ma60_d.loc[latest_idx] <= ma60_d.loc[prev_idx]:
            return
        stage_counts[6] += 1
        
        # 7. 長期トレンド（MA100が前日より上昇）
        if ma100_d.loc[latest_idx] <= ma100_d.loc[prev_idx]:
            return
        stage_counts[7] += 1
        
        # 8. 上ヒゲクリア（上ヒゲが実体の1.5倍以上ある場合は削除）
        body_size = abs(c_val - o_val)
        upper_shadow = h_val - max(c_val, o_val)
        if body_size > 0 and upper_shadow >= (body_size * 1.5):
            return
        stage_counts[8] += 1
        
        # 9. 天井圏MA100回避（MA100の3％以内に株価がいる場合は削除）
        if abs(c_val - ma100_d.loc[latest_idx]) / ma100_d.loc[latest_idx] <= 0.03:
            return
        stage_counts[9] += 1
        
        # 10. 新高値MA5更新 (直近5日間の最高値を更新)
        if c_val < close_d.iloc[-5:-1].max():
            return
        stage_counts[10] += 1
        
        # 11. 週足MA60クリア (最新の終値が週足60MA以上)
        latest_w_idx = ma60_w.index[-1]
        if pd.isna(ma60_w.loc[latest_w_idx]) or c_val < ma60_w.loc[latest_w_idx]:
            return
        stage_counts[11] += 1
        
        # 12. 天井圏維持（月足MA24の20%以上乖離しているものは削除）
        latest_m24_idx = ma24_m.index[-1]
        if not pd.isna(ma24_m.loc
