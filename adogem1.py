import sys

# プログラムの先頭でログを強制出力
print("★[DEBUG] スクリプトの実行が開始されました")
sys.stdout.flush()

def main():
    print("★[SYSTEM] main関数が呼ばれました")
    sys.stdout.flush()

if __name__ == "__main__":
    main()
    print("★[SYSTEM] 正常に終了しました")
    sys.stdout.flush()
