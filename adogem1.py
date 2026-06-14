def main():
    print("★main()関数の中に入りました！")
    
    # 範囲を 4000〜4500 に固定
    start_r = 4000
    end_r = 4501
    
    try:
        print("★[1] fetch_global_latest_date 実行前")
        fetch_global_latest_date()
        
        print("★[2] update_yesterday_results 実行前")
        update_yesterday_results()
        
        print("★[3] update_sheet2_results 実行前")
        update_sheet2_results()
        
        print("★[4] スキャンループ開始")
        for s in [str(i) for i in range(start_r, end_r)]: 
            print(f"★スキャン中: {s}")
            analyze_stock(s)
            
        print("★[5] スプレッドシート記録へ")
        record_to_spreadsheet()
        print("★すべての処理が完了しました")
        
    except Exception as e:
        print(f"★エラー発生: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("★[SYSTEM] 確実にif文を通過しました")
    main()
