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
    "pass_ma60_up": 0,
    "pass_new_high": 0,
    "pass_ceiling_avoid": 0,
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
        
        if len(df) < 60:
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
        
        close, open_p = today['Close'], today['Open']
        ma5_today = today['MA5']
        ma20_today = today['MA20']
        ma60_today = today['MA60']
        ma100_today = today['MA100']
        ma300_today = today['MA300']
        ma60_yest = yest['MA60']

        # 2. 下半身 ＆ 当日陽線
        if not (open_p < ma5_today < close) or close <= open_p: return "SKIP" 
        stats["pass_kahanshin"] += 1

        # 3. 2営業日前「溜め」判定
        if not (yest['Close'] < yest['MA5'] and yest2['Close'] < yest2['MA5']): return "SKIP"
        stats["pass_tame"] += 1
