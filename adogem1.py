import os
import sys
import glob
import time
import datetime
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from tqdm.notebook import tqdm
from google.colab import drive, userdata

# 設定
# Google Driveを使用する場合はマウント、GitHub Actionsの場合は環境変数からパスを取得
CSV_FOLDER = '/content/drive/MyDrive/nikkei/data_full' # 環境に合わせて変更してください
TARGET_DATE = datetime.datetime.now().strftime("%Y-%m-%d")

# 柔軟な列取得関数
def get_col(df, attr):
    for col in df.columns:
        if isinstance(col, tuple) and col[0] == attr: return df[col]
        elif col == attr: return df[col]
    return None

# マーク判定関数
def get_mark(pct):
    if pct >= 2.0: return "◎"
    elif pct >= 0.1: return "◯"
    elif pct >= -0.1: return "▲"
    else: return "✕"

# メール送信関数
def send_email(report_text):
    try:
        # GitHub ActionsのSecretまたはColabのuserdataから取得
        # ※GitHub Actionsの場合はos.environ.get('GMAIL_USER')等に変更してください
        sender = os.environ.get('EMAIL_ADDRESS') or userdata.get('GMAIL_USER')
        password = os.environ.get('EMAIL_PASSWORD') or userdata.get('GMAIL_APP_PASS')
        
        msg = MIMEText(report_text)
        msg['Subject'] = f"【検証レポート】{TARGET_DATE}"
        msg['From'] = sender
        msg['To'] = sender

        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, sender, msg.as_string())
        print("\n[システム] メールを送信しました。")
    except Exception as e:
        print(f"\n[システム] メール送信失敗: {e}")

def run_analysis():
    # CSV取得
    files = glob.glob(os.path.join(CSV_FOLDER, "*.csv"))
    pass_counts = {i: 0 for i in range(1, 13)}
    qualified_details = []
    
    target_dt = pd.to_datetime(TARGET_DATE).normalize()

    print(f"--- {TARGET_DATE} の検証を開始 ---\n")

    for file_path in tqdm(files, desc="検証中"):
        try:
            df = pd.read_csv(file_path, header=[0, 1], index_col=0)
            df.index = pd.to_datetime(df.index).normalize()

            if target_dt not in df.index: continue
            pass_counts[1] += 1

            c_series = get_col(df, 'Close')
            o_series = get_col(df, 'Open')
            h_series = get_col(df, 'High')
            v_series = get_col(df, 'Volume')
            if any(s is None for s in [c_series, o_series, h_series, v_series]): continue

            idx = df.index.get_loc(target_dt)
            prev_idx = idx - 1
            if prev_idx < 0: continue

            # 指標計算
            ma5 = c_series.rolling(5).mean()
            ma60 = c_series.rolling(60).mean()
            ma100 = c_series.rolling(100).mean()
            ma60_w = get_col(df, 'MA60_Weekly') if get_col(df, 'MA60_Weekly') is not None else ma60
            ma60_m = get_col(df, 'MA60_Monthly') if get_col(df, 'MA60_Monthly') is not None else ma60
            ma24_m = get_col(df, 'MA24_Monthly') if get_col(df, 'MA24_Monthly') is not None else ma60

            c, o, h, v = c_series.iloc[idx], o_series.iloc[idx], h_series.iloc[idx], v_series.iloc[idx]

            # --- ステージ判定 ---
            if c > ma60_m.iloc[idx]: pass_counts[2] += 1
            else: continue
            if v >= 50000: pass_counts[3] += 1
            else: continue
            if c > ma5.iloc[idx]: pass_counts[4] += 1
            else: continue
            if c_series.iloc[prev_idx] < ma5.iloc[prev_idx]: pass_counts[5] += 1
            else: continue
            if c > ma60.iloc[idx]: pass_counts[6] += 1
            else: continue
            if ma100.iloc[idx] > ma100.iloc[prev_idx]: pass_counts[7] += 1
            else: continue
            upper = h - max(o, c); body = abs(c - o)
            if body == 0 or (upper <= (body * 1.5)): pass_counts[8] += 1
            else: continue
            if abs(c - ma100.iloc[idx]) / ma100.iloc[idx] >= 0.03: pass_counts[9] += 1
            else: continue
            if ma5.iloc[idx] >= ma5.rolling(20).max().iloc[idx]: pass_counts[10] += 1
            else: continue
            if c > ma60_w.iloc[idx]: pass_counts[11] += 1
            else: continue

            if (c / ma24_m.iloc[idx] <= 1.2):
                pass_counts[12] += 1
                # 翌営業日判定ロジック
                if idx + 1 < len(c_series):
                    future_c = c_series.iloc[idx + 1]
                    pct = ((future_c - c) / c) * 100
                    mark = get_mark(pct)
                    ticker = os.path.basename(file_path).replace(".csv", "")
                    qualified_details.append(f"{mark} | {ticker} | {int(c)}円 ({TARGET_DATE[5:]}) → 翌営業日 | {int(future_c)}円 ({pct:+.2f}%)")
            else: continue

        except Exception: continue

    # レポート作成
    report = f"--- {TARGET_DATE} 検証結果 ---\n\n【各ステージ生存数】\n"
    stages = ["取得", "月足60", "出来高", "下半身", "溜め", "右肩", "長期T", "上ヒゲ", "天井回避", "新高値", "週足60", "天井維持"]
    for i in range(1, 13):
        report += f"{i}.{stages[i-1]}: {pass_counts[i]}件\n"

    report += "\n【確定の判定結果】\n"
    report += "\n".join(qualified_details) if qualified_details else "該当銘柄なし"

    report += "\n\n--------------------------------------------------\n【条件一覧】\n1. 全データ取得成功\n2. 月足MA60クリア\n3. 出来高5万株クリア\n4. 下半身クリア\n5. 溜めMA5クリア\n6. 右肩上がり\n7. 長期トレンド\n8. 上ヒゲクリア\n9. 天井圏MA100回避\n10. 新高値MA5更新\n11. 週足MA60クリア\n12. 天井圏維持"
    report += "\n\n【判定結果マーク基準】翌日終値\n ◎ ： +2.0%以上\n ◯ ： +0.1%〜+2.0%\n ▲ ： -0.1%〜+0.1%\n ✕ ： -0.1%未満"

    print(report)
    send_email(report)

if __name__ == "__main__":
    # GitHub Actionsで引数を渡す場合は sys.argv を使用可能
    run_analysis()
