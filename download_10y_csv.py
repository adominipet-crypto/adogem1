import pandas as pd
import yfinance as yf
import time
import os

def main():
    # GitHub上の正しいファイル名を指定
    filename = 'all_stocks.xls'
    
    # CSVの読み込み（UTF-8またはShift_JISで読み込み）
    try:
        df_list = pd.read_csv(filename, encoding='utf-8')
    except:
        df_list = pd.read_csv(filename, encoding='shift_jis')
    
    # 'コード'列を抽出（空行を除去し、文字列型に変換）
    codes = df_list['コード'].dropna().astype(str).tolist()
    
    os.makedirs("output", exist_ok=True)
    
    for code in codes:
        # ".0" が付いている数値を除去（例: "1301.0" -> "1301"）
        clean_code = code.replace('.0', '')
        
        # 銘柄コードに '.T' を付与
        ticker = f"{clean_code}.T"
            
        print(f"取得中: {ticker}")
        try:
            # データダウンロード
            df = yf.download(ticker, period="10y")
            if not df.empty:
                # outputフォルダにCSVとして保存
                df.to_csv(f"output/{clean_code}.csv")
                print(f"保存完了: {clean_code}.csv")
            else:
                print(f"データなし: {ticker}")
        except Exception as e:
            print(f"エラー発生 {ticker}: {e}")
        
        # 連続アクセスの制限を回避
        time.sleep(1)

if __name__ == "__main__":
    main()
