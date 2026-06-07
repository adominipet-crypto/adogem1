import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError  

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# 実際にそのステージで「脱落（留まった）」した数を正確にカウントする辞書
stats = {
    "stage1_fetched": 0,       # データ取得失敗
    "stage2_monthly_60ma": 0,  # 月足MA60不合格
    "stage3_volume": 0,        # 出来高不合格
    "stage4_kahanshin": 0,     # 下半身不合格
    "stage5_tame": 0,          # 溜め不合格
    "stage6_ma60_up": 0,       # 右肩上がり不合格
    "stage7_trend_up": 0,      # 7. 長トレンドで脱落
    "stage8_upper_shadow": 0,  # 8. 上ヒゲクリアで脱落
    "stage9_ceiling_avoid": 0, # 9. 天井圏回避で脱落
    "stage10_new_high": 0,     # 10. 新高値更新で脱落
    "stage11_weekly_60ma": 0,  # 11. 週足60クリアで脱落
    "stage12_monthly_ma24": 0, # 12. 天井圏維持（完全クリア合格）
    "★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0
}

# 1銘柄につき確定した最終判定のみを保持する辞書
sheet1_final_log = {}
# ステージ12を完全クリアした最終規定合格銘柄のみを保持する辞書（シート2用）
selected_stocks = {}

def connect_spreadsheet(sheet_name="シート1"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    
    max_retries = 5
    backoff_factor = 5  
    
    for attempt in range(1, max_retries + 1):
        try:
            client = gspread.authorize(creds)
            return client.open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)
        except APIError as e:
            if e.response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries:
                sleep_time = attempt * backoff_factor
                print(f"【⚠️Google API制限検知 {e.response.status_code}】")
                print(f"  --> {sleep_time}秒待機して再試行します（試行 {attempt}/{max_retries}）")
                time.sleep(sleep_time)
            else:
                raise e  
        except Exception as e:
            if attempt < max_retries:
                time.sleep(attempt * backoff_factor)
            else:
                raise e

def send_error_email(error_message, start_range, end_range):
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = f"⚠️【エラー発生】adoGEM スキャン停止 ({start_range}-{end_range})"
    
    body = f"プログラムの実行中にエラーが発生し、処理が中断されました。\n" \
           f"発生日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
           f"【エラー詳細・ログ】\n" \
           f"--------------------------------------------------\n" \
           f"{error_message}\n" \
           f"--------------------------------------------------"
    
    msg.
