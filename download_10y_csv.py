import pandas as pd
import os

def main():
    filename = 'all_stocks.xls'
    
    # 読み込みの試行
    try:
        # cp932でエラーを無視し、区切り文字を自動判定
        df = pd.read_csv(filename, encoding='cp932', errors='replace', sep=None, engine='python')
        
        # 読み込めた場合の確認
        print(f"--- 読み込み成功 ---")
        print(f"全行数: {len(df)}")
        print(f"カラム一覧: {df.columns.tolist()}")
        
        # 2列目をコードと仮定して抽出
        codes = df.iloc[:, 1].dropna().astype(str).tolist()
        
        # クリーニング
        clean_codes = [c.replace('.0', '').strip() for c in codes if len(c.replace('.0', '').strip()) >= 3]
        
        print(f"抽出された銘柄数: {len(clean_codes)}")
        print(f"最初の5件: {clean_codes[:5]}")
        
    except Exception as e:
        print(f"--- 読み込みエラー ---")
        print(f"詳細: {e}")

if __name__ == "__main__":
    main()
