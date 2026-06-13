def main():
    # ここで3つすべてチェックするように書き換えます
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN or not DRIVE_FOLDER_ID:
        print("エラー: 設定値が読み込めていません")
        return
    
    drive_service = authenticate_drive()
    
    # あとは元の処理と同じです
    for code in range(1300, 1311):
        df = fetch_10y_data(str(code))
        if df is not None: 
            upload_csv_to_drive(drive_service, df, str(code))
        else: 
            print(f"[{code}] データなし")
        time.sleep(1.5)
