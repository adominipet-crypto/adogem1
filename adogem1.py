import sys
import traceback
import os
# ... (その他import) ...

# 1. 起動デバッグ（最上部）
print(f"★[DEBUG] 起動しました。カレントディレクトリ: {os.getcwd()}")

# 2. 関数定義をすべてここに集める（mainより上にする！）
def fetch_global_latest_date():
    # ここに中身を記述
    print("★fetch_global_latest_dateを実行")

def update_yesterday_results():
    # ここに中身を記述
    print("★update_yesterday_resultsを実行")

def update_sheet2_results():
    # ここに中身を記述
    print("★update_sheet2_resultsを実行")

def analyze_stock(s):
    # ここに中身を記述
    print(f"★analyze_stock: {s}")

def record_to_spreadsheet():
    # ここに中身を記述
    print("★record_to_spreadsheetを実行")

# 3. main関数を一番下に置く
def main():
    print("★main()関数の中に入りました！")
    # ... (前回のmainコード)
    fetch_global_latest_date() # ここで正しく認識されるようになる
    # ...

# 4. 最後に起動処理
if __name__ == "__main__":
    main()
