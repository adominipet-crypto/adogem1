def main():
    print("--- プログラム開始 ---")
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN, DRIVE_FOLDER_ID]):
        print("エラー: 環境変数が不足しています")
        return

    print(f"保存先フォルダID: {DRIVE_FOLDER_ID}")
    try:
        drive_service = authenticate_drive()
        print("認証成功")
        
        # 1300から1310までループを回す
        for code in range(1300, 1311):
            print(f"銘柄コード {code} を処理中...")
            df = fetch_10y_data(str(code))
            
            if df is not None:
                print(f"データ取得成功: {len(df)}行")
                upload_csv_to_drive(drive_service, df, str(code))
                print(f"アップロード完了: {code}.csv")
            else:
                print(f"[{code}] データ取得失敗（またはデータなし）")
            
            time.sleep(1.5)
            
        print("--- 全処理完了 ---")
    except Exception as e:
        print(f"致命的なエラーが発生しました: {e}")
