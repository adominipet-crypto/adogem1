def update_sheet2_results():
    try:
        sheet2 = connect_spreadsheet("シート2")
        all_records = sheet2.get_all_values()
        print(f"DEBUG: Sheet2の全レコード数: {len(all_records)}") # ログ出力追加
        
        cell_list = []
        # 4行ごとの処理
        for i in range(0, len(all_records), 4):
            # データの安全な取得
            row_data = all_records[i]
            if len(row_data) < 3: 
                continue
            
            data_date_str, code = row_data[0], row_data[1]
            if not code or data_date_str == "選定日付": 
                continue
            
            print(f"DEBUG: {code} ({data_date_str}) を解析中...")
            
            try:
                selected_price = int(row_data[2])
                sel_date = datetime.datetime.strptime(data_date_str, "%Y-%m-%d").date()
                
                df = get_stock_data_fallback(code, force_check_date=False)
                if df is None: 
                    print(f"DEBUG: {code} のデータ取得失敗")
                    continue
                
                future_df = df[df.index.date > sel_date]
                if future_df.empty: 
                    print(f"DEBUG: {code} に未来データなし")
                    continue
                
                # データの準備
                first_day = future_df.iloc[0]
                close_1 = int(first_day['Close'])
                pct_1 = ((close_1 - selected_price) / selected_price) * 100
                
                # セル追加
                cell_list.extend([gspread.Cell(i+2, 5, close_1), gspread.Cell(i+3, 5, f"{pct_1:+.2f}%")])
                
                for day_idx in range(1, min(len(future_df), 15)):
                    col = day_idx + 5
                    close_curr = int(future_df.iloc[day_idx]['Close'])
                    close_prev = int(future_df.iloc[day_idx-1]['Close'])
                    pct_day = ((close_curr - close_prev) / close_prev) * 100
                    cell_list.extend([gspread.Cell(i+2, col, close_curr), gspread.Cell(i+3, col, f"{pct_day:+.2f}%")])
            
            except Exception as e:
                print(f"DEBUG: {code} の処理中に個別エラー: {e}")
        
        # 書き込み実行
        if cell_list: 
            print(f"DEBUG: {len(cell_list)} 個のセルを更新します")
            sheet2.update_cells(cell_list, value_input_option='RAW')
            print("DEBUG: 更新完了")
        else:
            print("DEBUG: 更新対象のデータがありませんでした")

    except Exception as e:
        print(f"★[ERROR] Sheet2更新プロセス全体の失敗: {e}")
        # スタックトレースを表示して原因を確定させる
        traceback.print_exc()
