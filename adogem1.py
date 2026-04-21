def analyze_stock(symbol):
    try:
        ticker = yf.Ticker(f"{symbol}.T")
        df = ticker.history(period="70d")
        if len(df) < 60 or df['Volume'].iloc[-1] < 50000:
            return None

        # 指標計算
        df['MA5'] = df['Close'].rolling(window=5).mean()
        df['MA20'] = df['Close'].rolling(window=20).mean()
        df['MA60'] = df['Close'].rolling(window=60).mean()
        
        last = df.iloc[-1]
        prev = df.iloc[-2]
        
        close, open_p, high = last['Close'], last['Open'], last['High']
        ma5 = last['MA5']
        ma20 = last['MA20']
        ma60 = last['MA60']
        ma60_prev = prev['MA60']

        # --- 【修正】厳格な下半身フィルター ---
        
        # 1. 陽線判定
        if not (close > open_p): return None
        
        # 2. 「またぎ」の判定（9143や9022のような浮き・スレスレを排除）
        # 始値が5日線より下、かつ、終値が5日線より上であることを必須にする
        if not (open_p < ma5 < close): return None
        
        # 3. 「半分以上が上」の判定
        # 実体の長さのうち、5日線より上に出ている部分が半分（0.5）を超えているか
        body_length = close - open_p
        upper_part = close - ma5
        if (upper_part / body_length) <= 0.5: return None

        # --- 以下、既存のフィルター ---
        
        # 4. 乖離率チェック（20日線から離れすぎを排除）
        kairi_20 = (close - ma20) / ma20
        if kairi_20 >= 0.05: return None

        # 5. 上ヒゲ制限（売り圧力を排除）
        upper_shadow = high - close
        if upper_shadow >= body_length: return None

        # 6. 長期線（60日線）の傾き
        if ma60 < ma60_prev: return None

        # --- 合格銘柄 ---
        is_ppp = ma5 > ma20 > ma60
        star = "★PPP" if is_ppp else ""
        return f"{star}: {symbol} (終値:{int(close)})"
        
    except:
        return None
