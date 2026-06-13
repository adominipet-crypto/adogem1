import yfinance as yf
import time
import os

def main():
    os.makedirs("output", exist_ok=True)
    downloaded_count = 0
    
    print("全銘柄チェックを開始します (1301から)...")
    
    # 1301から9999まで順次チェック
    for i in range(1301, 10000):
        ticker = f"{i}.T"
        
        try:
            # 取得を試みる
            df = yf.download(ticker, period="10y", progress=False)
            
            if not df.empty:
                df.to_csv(f"output/{i}.csv")
                downloaded_count += 1
                # ログの出力を整理（10件ごとに表示してログ量をおさえます）
                if downloaded_count % 10 == 0:
                    print(f"進捗: {downloaded_count}件取得済み (現在: {ticker})")
            
        except Exception:
            continue
            
        # 連続アクセスの制限を回避（短くして高速化します）
        time.sleep(0.1)
        
    print(f"--- 全処理完了 ---")
    print(f"合計ダウンロード数: {downloaded_count}件")

if __name__ == "__main__":
    main()
