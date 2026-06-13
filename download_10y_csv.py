import pandas as pd
import yfinance as yf
import time
import os

def main():
    # GitHubにアップロードしたファイル名を指定
    df_list = pd.read_csv('all_stocks.xls - Sheet1.csv') 
    
    # 'コード'列を抽出（数値として扱う）
    codes = df_list['コード'].dropna().astype(int).tolist()
    
    os.makedirs("output", exist_ok=True)
    
    # 全銘柄をダウンロード
    for code in codes:
        ticker = f"{code}.T"
        print(f"取得中: {ticker}")
        try:
            df = yf.download(ticker, period="10y")
            if not df.empty:
                df.to_csv(f"output/{code}.csv")
        except Exception as e:
            print(f"エラー: {e}")
        time.sleep(1) # サーバー負荷防止のため少し待機

if __name__ == "__main__":
    main()
