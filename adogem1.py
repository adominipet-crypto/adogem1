def get_stock_data_fallback(symbol, force_check_date=True):
    try:
        # 1. ドライブ内のファイルパスを作成
        file_path = f'/content/drive/MyDrive/nikkei/data_full/{symbol}.csv'
        
        # 2. ファイルがない場合は「なし」として終了
        if not os.path.exists(file_path):
            return None
        
        # 3. ドライブのCSVを読み込む
        df = pd.read_csv(file_path, index_col=0, parse_dates=True)
        
        # 4. 日付のチェック（最新データが揃っているかの確認）
        if force_check_date and GLOBAL_LATEST_DATE:
            # データの最終日が、最新の日付より古い場合は None を返す
            if df.index[-1].date() < GLOBAL_LATEST_DATE:
                return None
        
        return df
    except Exception as e:
        print(f"読み込みエラー ({symbol}): {e}")
        return None
