import warnings
warnings.simplefilter('ignore', FutureWarning)

import pandas as pd
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os, time, sys, datetime, gspread, json, requests, traceback
from google.oauth2.service_account import Credentials
from gspread.exceptions import APIError  
import re

# --- 環境設定 ---
SENDER_EMAIL = os.environ.get('EMAIL_ADDRESS')
SENDER_PASSWORD = os.environ.get('EMAIL_PASSWORD')
JQ_REFRESH_TOKEN = os.environ.get('JQ_REFRESH_TOKEN') # J-Quants用リフレッシュトークン

# --- グローバル変数 ---
# 1〜9の9ステージ構成
stage_survivors = {f"stage{i}": 0 for i in range(1, 10)}  
stats = {"★PPP": 0, "★PPP(Short)": 0, "normal_detect": 0}
sheet1_final_log = {}
selected_stocks = {}
GLOBAL_LATEST_DATE = None  
ALL_STOCK_DATA_CACHE = {} # J-Quantsから一括取得した当日データを格納する辞書

# ステージ6〜9および完全合格の答え合わせ用レポート構造
stage_results_report = {
    "stage6": [],
    "stage7": [],
    "stage8": [],
    "stage9": [],
    "completed_pass": []
}

STAGE_LABELS = {
    "stage6": "6.溜め",
    "stage7": "7.右肩上がり",
    "stage8": "8.長期トレンド",
    "stage9": "9.当日陽線",
    "completed_pass": "完全合格"
}

# 6〜9の自動集計用カウンター
stage_stats_counter = {
    6: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    7: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    8: {"◎": 0, "◯": 0, "▲": 0, "✕": 0},
    9: {"◎": 0, "◯": 0, "▲": 0, "✕": 0}
}

# --- J-Quants API データ一括取得関数 ---
def fetch_all_stock_data_from_jquants():
    global GLOBAL_LATEST_DATE, ALL_STOCK_DATA_CACHE
    if not JQ_REFRESH_TOKEN:
        print("エラー: JQ_REFRESH_TOKEN が GitHub Secrets に設定されていません。")
        return False
        
    try:
        print("J-Quants API から認証IDを取得中...")
        auth_url = f"https://api.jquants.com/v1/auth/idtoken?refreshToken={JQ_REFRESH_TOKEN}"
        res = requests.post(auth_url, timeout=15)
        id_token = res.json().get("idToken")
        if not id_token:
            print("J-Quants 認証トークンの取得に失敗しました。")
            return False
            
        headers = {"Authorization": f"Bearer {id_token}"}
        
        # 【テスト用設定】日付を直近の金曜日に固定
