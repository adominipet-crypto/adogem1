import pandas as pd
import yfinance as yf
import time
import os

def main():
    filename = 'all_stocks.xls'
    
    # 1. 完全にバイナリとして読み込み、Shift_JISとしてデコードを試みる
    # 2. 壊れた行があってもスキップし、NUL文字も除去して読み込む
    with open(filename, 'rb') as f:
        data = f.read().replace(b'\x00', b'') # NUL文字を物理的に削除
    
    with open('cleaned_stocks.csv', 'wb') as f:
        f.write(data) # 一旦きれいにしたファイルを書き出す
        
    # 3. きれいになったCSVをpandasで読み込む
    df_list = pd.read_csv('cleaned_stocks.csv', encoding='shift_jis', on_bad_lines='skip')
    
    # カラム名を強制的に割り当て（2列目がコードであるという前提）
    # 日付,コード,銘柄名... の順と想定
    codes = df_list.iloc[:, 1].dropna().astype(str).tolist()
    
    os.makedirs("output", exist_ok=True)
    
    print(f"抽出した銘柄数: {len(codes)}")
    
    for code in codes:
        # .0 を除去し、空白を詰める
        clean_code = code.replace('.0', '').strip()
        
        # 銘柄コードに .T を付与
        ticker = f"{clean_code}.T"
        
        print(f"取得中: {ticker}")
        try:
            df = yf.download(ticker, period="10y")
            if not df.empty:
                df.to_csv(f"output/{clean_code}.csv")
                print(f"保存完了: {clean_code}.csv")
        except Exception as e:
            print(f"エラー発生 {ticker}: {e}")
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()
