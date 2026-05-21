def update_yesterday_results():
    """過去の『判定待ち』データの答え合わせ（◎◯▲✕の判定基準カスタム版）"""
    try:
        sheet = connect_spreadsheet()
        all_records = sheet.get_all_values()
        
        if all_records and len(all_records[0]) < 7:
            sheet.update_cell(1, 7, "前日比(%)")
        
        for i, row in enumerate(all_records):
            if i == 0: continue  # ヘッダー無視
            
            if len(row) >= 6 and row[5] == "判定待ち":
                code = row[1]
                selected_price = int(row[2])
                
                ticker = yf.Ticker(f"{code}.T")
                df = ticker.history(period="2d")
                if df is not None and len(df) >= 1:
                    next_close = int(df['Close'].iloc[-1])
                    
                    # 📈 前日比％の計算
                    change_percent = ((next_close - selected_price) / selected_price) * 100
                    change_str = f"{change_percent:+.2f}%"
                    
                    # 🎯 【条件カスタム】◎ ◯ ▲ ✕ 判定ロジック
                    if change_percent >= 2.0:
                        result_mark = "◎"  # 2%以上の急騰
                    elif change_percent > 0.1:
                        result_mark = "◯"  # しっかりプラス
                    elif -0.1 <= change_percent <= 0.1:
                        result_mark = "▲"  # -0.1%〜+0.1%の微変動（変わらず）
                    else:
                        result_mark = "✕"  # -0.1%未満の下落
                    
                    # シートへの書き込み
                    sheet.update_cell(i + 1, 5, next_close)
                    sheet.update_cell(i + 1, 6, result_mark)
                    sheet.update_cell(i + 1, 7, change_str)
                    
                    print(f"【答え合わせ】コード:{code} 判定:{result_mark} ({change_str})")
                    time.sleep(0.5)
    except Exception as e:
        print(f"自動答え合わせエラー: {e}")
