# (判定処理のあとに)
        print(f"★スキャン終了。合格銘柄数: {len(final_list)}")
        
        # メール送信部分
        try:
            print("★メール送信を開始します...")
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.send_message(msg)
            server.quit()
            print("★メール送信が正常に完了しました！")
        except Exception as e:
            print(f"★メール送信でエラー発生: {e}")
