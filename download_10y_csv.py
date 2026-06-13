import pandas as pd
import yfinance as yf
import time
import os

def main():
    # ファイル名を 'all_stocks.xls' に設定
    filename = 'all_stocks.xls - Sheet1.csv' # ※GitHub上にアップロードされている実際のファイル名を確認してください
    
    # ファイルが見つかるか確認
    if not os.path.exists(filename):
        # 念のため、現在GitHubのフォルダにあるファイル一覧を表示して確認します
        print(f"エラー: {filename} が見つかりません。")
        print("フォルダ内のファイル一覧:", os.listdir('.'))
        return

    # CSVを読み込む（Shift_JISで読み込み）
    df_list = pd.read_csv(filename, encoding='shift_jis') 
    
    # 'コード'列を抽出（数値として扱う）
    codes = df_list['コード'].dropna().astype(str).tolist()
    
    os.makedirs("output", exist_ok=True)
    
    for code in codes:
        # .0 を除去
        clean_code = code.replace('.0', '')
        ticker = f"{clean_code}.T"
            
        print(f"取得中: {ticker}")
        try:
            df = yf.download(ticker, period="10y")
            if not df.empty:
                df.to_csv(f"output/{clean_code}.csv")
                print(f"保存完了: {clean_code}.csv")
        except Exception as e:
            print(f"エラー発生 {ticker}: {e}")
        
        time.sleep(1)

if __name__ == "__main__":
    main()
