import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials

SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')

# 集計カウンタ（メールレポートの数値出力に使用）
stats = {
    "total_fetched": 0, "pass_delay": 0, "pass_volume": 0, "pass_kahanshin": 0, "pass_tame": 0,
    "pass_ma60_up": 0, "pass_trend_align": 0, "pass_upper_shadow": 0, "pass_new_high": 0, "pass_ceiling_avoid": 0,
    "★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0
}

# 条件4（60日線）以降を通過して、どこで止まったかを一時格納する辞書（シート1の個別ログ用）
highest_stages = {}
# 7まで完全クリアした最終合格銘柄のみを保持する辞書（シート2用）
selected_stocks = {}

def connect_spreadsheet(sheet_name="シート1"):
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    secret_key = os.environ.get('GCP_SA_KEY')
    if secret_key:
        info = json.loads(secret_key)
        creds = Credentials.from_service_account_info(info, scopes=scopes)
    else:
        creds = Credentials.from_service_account_file("google_credentials.json", scopes=scopes)
    return gspread.authorize(creds).open("26.5.23_adoGEM_検証ログ").worksheet(sheet_name)

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
    
    msg.attach(MIMEText(body, 'plain'))
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print("【システム】エラーメールを送信しました。")
    except Exception as e:
        print(f"エラーメール送信失敗: {e}")

def record_to_spreadsheet():
    """ 🌟 [完全現状維持] シート1へ、これまで通り途中で脱落したステージも含めて個別選別を記録する """
    try:
        sheet = connect_spreadsheet("シート1")
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        new_rows = []
        for code, data in highest_stages.items():
            price = data["price"]
            stage_key = data["stage_key"]
            ppp_status = data["ppp_label"].strip() if data["ppp_label"].strip() else "通常"
            
            stage_names = {
                "ma60_up": "4. 60日線右肩上がり", "trend_align": "5. 長期トレンド同期",
                "upper_shadow": "6. 上ヒゲ選別", "ceiling_avoid": "7. 天井圏回避(最終)"
            }
            stage_name = stage_names.get(stage_key, stage_key)
            new_rows.append([today_str, code, stage_name, ppp_status, price, "", "判定待ち", ""])
        if new_rows:
            new_rows.sort(key=lambda x: x[1])
            sheet.append_rows(new_rows, value_input_option='RAW')
            print(f"【シート1記録】従来通り {len(new_rows)} 件の個別ログを追記しました。")
    except Exception as e:
        print(f"シート1記録エラー: {e}")
        raise e

def record_to_sheet2():
    """ 🌟 [レイアウト固定] 画像モックのレイアウト通り、シート2へ最終合格を縦下方向（4行区切り）に追加 """
    if not selected_stocks:
        print("【シート2記録】本日「7. 天井圏回避(最終)」に合格した銘柄がないため、
