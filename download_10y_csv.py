import yfinance as yf
import time
import os
import re

def main():
    filename = 'all_stocks.xls'
    
    # バイナリモード（'rb'）で読み込み、NUL文字やゴミを無視して直接解析する
    codes = []
    print("ファイルから銘柄コードを直接抽出中...")
    
    with open(filename, 'rb') as f:
        content = f.read().decode('utf-8', errors='ignore')
        
    # 「日付,コード,銘柄名...」の並びから、コード部分（4桁の数字など）を正規表現で抽出
    # 20260531.0,1301.0,極洋... のような形式から 1301 を抜き出します
    # パターン: カンマの直後にある4桁以上の数字
    found_codes = re.findall(r',(\d{3,4})[.0]*,', content)
    
    # 重複を除去しつつリスト化（最初の行の日付などは除外）
    codes = sorted(list(set(found_codes)))
    print(f"抽出したコード数: {len(codes)}")
    
    os.makedirs("output", exist_ok=True)
    
    for code in codes:
        # 1301 などに .T を付与
        ticker = f"{code}.T"
        
        print(f"取得中: {ticker}")
        try:
            df = yf.download(ticker, period="10y")
            if not df.empty:
                df.to_csv(f"output/{code}.csv")
                print(f"保存完了: {code}.csv")
        except Exception as e:
            print(f"エラー発生 {ticker}: {e}")
        
        time.sleep(0.5)

if __name__ == "__main__":
    main()
