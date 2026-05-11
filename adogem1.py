def main():
    # テスト用に 7200番（自動車セクター周辺）から100銘柄に固定
    start_range = 7201 
    end_range = 7300
    
    target_codes = [str(i) for i in range(start_range, end_range)]
    
    print(f"--- 【動作確認テスト】開始: {start_range}-{end_range} ---")
    
    all_results = []
    for symbol in target_codes:
        res = analyze_stock(symbol)
        if res:
            # 的中したら画面に大きく表示
            print(f"★★★★★ 的中発見！ -> {res}")
            all_results.append(res)
        time.sleep(0.2)

    # 的中があってもなくても、動作確認メールを必ず送る設定
    subject = f"【テスト報告】adoGEM動作確認({start_range}-{end_range})"
    if all_results:
        body = "以下の銘柄が条件をクリアしました：\n\n" + "\n".join(all_results)
    else:
        body = "スキャンは正常に完了しましたが、この範囲に条件合致銘柄はありませんでした。\n（データ取得自体は成功しています）"

    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = SENDER_EMAIL
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        print("--- テストメールを送信しました ---")
        server.quit()
    except Exception as e:
        print(f"メール送信エラー: {e}")

if __name__ == "__main__":
    main()
