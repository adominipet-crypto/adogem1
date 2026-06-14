def main():
    # 範囲を 4000〜4500 に固定します
    start_r = 4000
    end_r = 4501  # 4500まで含めるため+1します
    
    # ... (既存の処理: fetch_global_latest_date(), update_... 呼び出し) ...
    fetch_global_latest_date()
    update_yesterday_results()
    update_sheet2_results()
    
    # 銘柄スキャンループ
    print(f"★実験開始: {start_r}番から{end_r-1}番までスキャンします")
    for s in [str(i) for i in range(start_r, end_r)]: 
        analyze_stock(s)
        
    record_to_spreadsheet()
    
    # ... (メール送信処理へ) ...
