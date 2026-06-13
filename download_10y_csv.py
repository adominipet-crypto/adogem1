def main():
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN or not DRIVE_FOLDER_ID:
        print("エラー: 設定値が読み込めていません")
        return
    
    print(f"保存先フォルダID: {DRIVE_FOLDER_ID}") # ここでIDを出力
    drive_service = authenticate_drive()
    print("認証成功！") # ここで認証を確認
    
    for code in range(1300, 1311):
        print(f"銘柄コード {code} を処理中...") # 進行状況を表示
        df = fetch_10y_data(str(code))
        if df is not None: 
            upload_csv_to_drive(drive_service, df, str(code))
        else: 
            print(f"[{code}] データなし")
        time.sleep(1.5)
