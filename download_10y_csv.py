# --- CSVをGoogleドライブへアップロード（修正版） ---
def upload_csv_to_drive(drive_service, df, symbol):
    # 修正箇所: StringIO から BytesIO に変更し、文字列をエンコードする
    csv_buffer = io.BytesIO(df.to_csv().encode('utf-8'))
    
    file_name = f"{symbol}.csv"
    file_metadata = {
        'name': file_name,
        'parents': [DRIVE_FOLDER_ID]
    }
    
    # 修正箇所: resumable=True だとメモリ消費が激しい場合があるため、一旦 False で試します
    media = MediaIoBaseUpload(csv_buffer, mimetype='text/csv', resumable=False)
    
    try:
        query = f"name='{file_name}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
        results = drive_service.files().list(q=query, fields="files(id, name)").execute()
        items = results.get('files', [])
        
        if items:
            file_id = items[0]['id']
            drive_service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            print(f"[{symbol}] 既存のCSVを更新しました。")
        else:
            drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            print(f"[{symbol}] 新規CSVを作成しました。")
            
    except Exception as e:
        print(f"[{symbol}] ドライブ保存エラー: {e}")
