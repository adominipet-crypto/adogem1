if results:
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("エラー: GitHubのSecrets設定（EMAIL_ADDRESS または EMAIL_PASSWORD）が空です。")
    else:
        msg = MIMEMultipart()
        msg['Subject'] = f"【的中】厳格下半身リスト {len(results)}件"
        msg['From'] = SENDER_EMAIL
        msg['To'] = RECEIVER_EMAIL
        msg.attach(MIMEText("\n".join(results), 'plain'))
        
        try:
            print(f"メール送信を試みます... (送信元: {SENDER_EMAIL})")
            # 接続設定を587番ポートに固定
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.set_debuglevel(1)  # ログに詳細なやり取りを表示させる設定
            server.starttls() 
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print("メール送信に成功しました！")
        except Exception as e:
            # ここで {} ではなく、具体的なエラー理由を表示させます
            print("--- メール送信失敗の詳細ログ ---")
            print(f"エラー内容: {e}")
            print("--------------------------------")
