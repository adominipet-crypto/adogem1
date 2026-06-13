import pandas as pd
import yfinance as yf
import time
import os

def main():
    filename = 'all_stocks.xls'
    
    # cp932 を指定することで、Shift_JISでエラーになる文字も読み込めるようになります
    # さらにエラーが出る行は無視するように設定
    try:
        df_list = pd.read_csv(filename, encoding='cp932', on_bad_lines='skip')
    except Exception as e:
        print(f"読み込み失敗: {e}")
        return

    # 'コード'列を文字列として取得
    # カラム名が正しいか念のため確認するためにリストを表示
    print("カラム一覧:", df_list.columns.tolist())
    
    # 銘柄コードの抽出
    codes = df_list['コード'].dropna().astype(str).tolist()
    
    os.makedirs("output", exist_ok=True)
    
    for code in codes:
        # ".0" を削除し、前後の空白を除去
        clean_code = code.replace('.0', '').strip()
        
        # 130Aなどの文字が含まれる場合はそのまま、そうでなければ .T を付与
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
