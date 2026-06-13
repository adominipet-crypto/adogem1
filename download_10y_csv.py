import pandas as pd
import yfinance as yf
import time
import os

def main():
    filename = 'all_stocks.xls'
    
    # 読み込みの試行：1. Excel形式 -> 2. UTF-8 -> 3. Shift_JIS -> 4. 許容モード
    try:
        try:
            # まずExcel形式として試す
            df_list = pd.read_excel(filename)
        except:
            # ダメならCSVとして試す（日本語によくあるShift_JISで）
            df_list = pd.read_csv(filename, encoding='shift_jis', on_bad_lines='skip')
    except Exception as e:
        print(f"致命的な読み込みエラー: {e}")
        return
    
    # 'コード'列を抽出（列名にスペースがないか確認してください）
    # もしエラーが出る場合は、df_list.columns で列名を確認すると確実です
    codes = df_list['コード'].dropna().astype(str).tolist()
    
    os.makedirs("output", exist_ok=True)
    
    for code in codes:
        # ".0" やスペースを除去
        clean_code = code.replace('.0', '').strip()
        
        # 銘柄コードに '.T' を付与
        ticker = f"{clean_code}.T"
            
        print(f"取得中: {ticker}")
        try:
            df = yf.download(ticker, period="10y")
            if not df.empty:
                df.to_csv(f"output/{clean_code}.csv")
        except Exception as e:
            print(f"エラー発生 {ticker}: {e}")
        
        time.sleep(0.5) # 少しだけ早めました

if __name__ == "__main__":
    main()
