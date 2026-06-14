def init_google_sheets():
    global gc, workbook, sheet1, sheet2
    try:
        # 必要な権限（スコープ）を明示的に指定します
        scopes = [
            'https://www.googleapis.com/auth/spreadsheets',
            'https://www.googleapis.com/auth/drive'
        ]
        
        sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") or os.environ.get("GCP_SA_KEY")
        if not sa_json: 
            print("★[ERROR] 認証情報が見つかりません")
            return False
            
        # 認証情報にスコープをセットして作成します
        if sa_json.strip().startswith('{'):
            creds_dict = json.loads(sa_json)
            creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        else:
            creds = Credentials.from_service_account_file(sa_json, scopes=scopes)
            
        gc = gspread.authorize(creds)
        
        # ワークブックのオープン
        workbook = gc.open("Stock_Analysis_Data") 
        sheet1 = workbook.get_sheet_by_id(0)
        
        # シート2の取得（存在しない場合はエラーになるので例外処理）
        try:
            sheet2 = workbook.worksheet("シート2")
        except:
            sheet2 = workbook.add_worksheet(title="シート2", rows=100, cols=20)
            
        return True
    except Exception as e:
        print(f"★[ERROR] 初期化失敗: {e}")
        # 詳細なエラーを確認するためにトレースバックを表示
        traceback.print_exc()
        return False
