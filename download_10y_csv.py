import os
import yfinance as yf
import pandas as pd

def main():
    # 保存用ディレクトリを作成
    os.makedirs("output", exist_ok=True)
    
    # 1301から1305まで取得
    for i in range(1301, 1306):
        code = f"{i}.T"
        print(f"取得中: {code}")
        df = yf.download(code, period="10y")
        if not df.empty:
            df.to_csv(f"output/{i}.csv")
            print(f"保存完了: output/{i}.csv")

if __name__ == "__main__":
    main()
