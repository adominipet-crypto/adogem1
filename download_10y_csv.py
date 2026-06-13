import pandas as pd
import yfinance as yf
import time
import os

def main():
    filename = 'all_stocks.xls'
    
    # 文字コードを指定せず、pandasの自動判別に任せる設定
    # もしそれでもダメなら、最も汎用的な 'utf-16' を試す構成
    try:
        # まずは自動判別で試す
        df_list = pd.read_csv(filename, sep=None, engine='python', encoding_errors='ignore')
    except Exception:
        # ダメなら UTF-16 を試す（ExcelがCSV出力するときによくある形式）
        df_list = pd.read_csv(filename, encoding='utf-16', sep='\t', on_bad_lines='skip')
    
    # 念のためカラム名を表示して確認（ログで確認できます）
    print("カラム一覧:", df_list.columns.tolist())
    
    # 'コード'列が見つからない場合の対策
    col_name = 'コード' if 'コード' in df_list.columns else df_list.columns[1]
    
    codes = df_list[col_name].dropna().astype(str).tolist()
    
    os.makedirs("output", exist_ok=True)
    
    for code in codes:
        clean_code = code.replace('.0', '').strip()
        ticker = f"{clean_code}.T"
            
        print(f"取得中: {ticker}")
        try:
            df = yf.download(ticker, period="10y")
            if not df.empty:
                df.to_csv(f"output/{clean_code}.csv")
        except Exception as e:
            print(f"エラー発生 {ticker}: {e}")
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()
