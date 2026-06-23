def analyze_stock(symbol):
    df = get_stock_data_fallback(symbol, force_check_date=True)
    if df is None: return "SKIP"
    
    idx = len(df) - 1
    if idx < 480: return "SKIP"
    
    prev_idx = idx - 1

    c = df['Close']; o = df['Open']; h = df['High']; v = df['Volume']
    ma5 = c.rolling(5).mean()
    ma20 = c.rolling(20).mean()
    ma60 = c.rolling(60).mean()
    ma100 = c.rolling(100).mean()
    ma300 = c.rolling(300).mean()
    ma24_m = c.rolling(24*20).mean() 
    ma60_w = c.rolling(60*5).mean()

    if c.iloc[idx] > ma60.iloc[idx]: stage_survivors["stage1"] += 1; stage_survivors["stage2"] += 1
    else: return "SKIP"
    if v.iloc[idx] >= 50000: stage_survivors["stage3"] += 1
    else: return "SKIP"
    if c.iloc[idx] > ma5.iloc[idx]: stage_survivors["stage4"] += 1
    else: return "SKIP"
    if c.iloc[prev_idx] < ma5.iloc[prev_idx]: stage_survivors["stage5"] += 1
    else: return "SKIP"
    if ma60.iloc[idx] > ma60.iloc[prev_idx]: stage_survivors["stage6"] += 1
    else: return "SKIP"
    
    ppp_label = "★PPP " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx] > (ma300.iloc[idx] if pd.notna(ma300.iloc[idx]) else 0)) else ("★PPP(Short) " if (ma5.iloc[idx] > ma20.iloc[idx] > ma60.iloc[idx] > ma100.iloc[idx]) else "")
    data_date = df.index[idx].strftime("%Y-%m-%d")
    
    # ─── ここから下が切れていました ───
    if ma100.iloc[idx] > ma100.iloc[prev_idx]: stage_survivors["stage7"] += 1
    else: sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "trend_align", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    upper = h.iloc[idx] - max(o.iloc[idx], c.iloc[idx]); body = abs(c.iloc[idx] - o.iloc[idx])
    if body == 0 or (upper <= (body * 1.5)): stage_survivors["stage8"] += 1
    else: sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "upper_shadow", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    if (abs(c.iloc[idx] - ma100.iloc[idx]) / ma100.iloc[idx]) >= 0.03: stage_survivors["stage9"] += 1
    else: sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "ceiling_avoid", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    if ma5.iloc[idx] >= ma5.rolling(20).max().iloc[idx]: stage_survivors["stage10"] += 1
    else: sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "new_high_pass", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    if c.iloc[idx] > ma60_w.iloc[idx]: stage_survivors["stage11"] += 1
    else: sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "weekly_ma_pass", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    if (c.iloc[idx] / ma24_m.iloc[idx] <= 1.2): stage_survivors["stage12"] += 1
    else: sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "monthly_high_pass", "ppp_label": ppp_label, "date": data_date}; return "SKIP"
    
    sheet1_final_log[symbol] = {"price": int(c.iloc[idx]), "stage_key": "completed_pass", "ppp_label": ppp_label, "date": data_date}
    selected_stocks[symbol] = {"price": int(c.iloc[idx]), "ppp_label": ppp_label, "date": data_date}
    
    if "★PPP " in ppp_label: stats["★PPP"] += 1
    elif "★PPP(Short) " in ppp_label: stats["★PPP(Short)"] += 1
    else: stats["normal_detect"] += 1
    return "OK"
