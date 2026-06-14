def update_sheet2_results():
    print("★[DEBUG] Sheet2の処理を開始します")
    try:
        sheet2 = connect_spreadsheet("シート2")
        all_records = sheet2.get_all_values()
        print(f"★[DEBUG] Sheet2のレコード取得成功: {len(all_records)}行")
        
        cell_list = []
        # 4行ごとの処理
        for i in range(0, len(all_records), 4):
            # データの安全な取得
            if len(all_records[i]) < 3: 
                continue
            
            data_date_str, code = all_records[i][0], all_records[i][1]
            if not code or data_date_str == "選定日付": 
                continue
            
            try:
                selected_price = int(all_records[i][2])
                sel_date = datetime.datetime.strptime(data_date_str, "%Y-%m-%d").date()
                
                # ここで通信（デバッグのために少し情報を出す）
                df = get_stock_data_fallback(code, force_check_date=False)
                
                if df is None:
                    print(f"★[DEBUG] {code} のデータ取得失敗")
                    continue
                
                future_df = df[df.index.date > sel_date]
                if future_df.empty: 
                    continue

                # 処理継続...（以下は元のコードと同じ）
                first_day = future_df.iloc[0]
                close_1 = int(first_day['Close'])
                pct_1 = ((close_1 - selected_price) / selected_price) * 100
                cell_list.extend([gspread.Cell(i+2, 5, close_1), gspread.Cell(i+3, 5, f"{pct_1:+.2f}%")])
                for day_idx in range(1, min(len(future_df), 15)):
                    col = day_idx + 5
                    close_curr = int(future_df.iloc[day_idx]['Close'])
                    close_prev = int(future_df.iloc[day_idx-1]['Close'])
                    pct_day = ((close_curr - close_prev) / close_prev) * 100
                    cell_list.extend([gspread.Cell(i+2, col, close_curr), gspread.Cell(i+3, col, f"{pct_day:+.2f}%")])
            
            except Exception as e:
                print(f"★[DEBUG] {code} の処理でエラー発生: {e}")
                continue
        
        if cell_list: 
            print(f"★[DEBUG] {len(cell_list)} 個のセルを更新します")
            sheet2.update_cells(cell_list, value_input_option='RAW')
        else:
            print("★[DEBUG] 更新対象のデータがありませんでした")

    except Exception as e:
        print(f"★[CRITICAL] Sheet2更新プロセス全体でエラー: {e}")
