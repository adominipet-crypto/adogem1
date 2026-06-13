import yfinance as yf
import time
import os

def main():
    filename = 'all_stocks.xls'
    codes = []
    
    print("ファイルを直接解析中...")
    
    # 1行ずつ読み込む（バイナリモードで開き、デコードエラーは無視）
    with open(filename, 'rb') as f:
        for line in f:
            try:
                # バイナリをデコード（失敗しても無視）
                line_str = line.decode('cp932', errors='ignore')
                # カンマで分割
                parts = line_str.split(',')
                # 2番目の要素（コード想定）をチェック
                if len(parts) > 1:
                    code = parts[1].strip().replace('.0', '').replace('"', '')
                    # 3-4桁の数字のみをリストへ
                    if code.isdigit() and 3 <= len(code) <= 4:
                        codes.append(code)
            except:
                continue
                
    # 重複を除去
    codes = sorted(list(set(codes)))
    print(f"抽出した銘柄数: {len(codes)}")
    print(f"最初の5件: {codes[:5]}")
    
    # ダウンロード処理
    os.makedirs("output", exist_ok=True)
    for code in codes:
        ticker = f"{code}.T"
        print(f"取得中: {ticker}")
        try:
            df = yf.download(ticker, period="10y", progress=False)
            if not df.empty:
                df.to_csv(f"output/{code}.csv")
        except Exception as e:
            print(f"失敗: {ticker}")
        time.sleep(0.3)

if __name__ == "__main__":
    main()
