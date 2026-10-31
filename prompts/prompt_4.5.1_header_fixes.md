Email header changes:
1. Subject: "AI & CS Daily News Digest — <Weekday, Month Day>" (Phoenix time).
2. From display name: "AI & CS News". Address stays SMTP_USER unless EMAIL_FROM is set, in which case use EMAIL_FROM as the From address.
3. To display name: "Noah Sher".
Put the subject prefix, sender name and recipient name in config.yaml so I can change them without editing code.
Use email.utils.formataddr for the headers so names with "&" are encoded correctly.
Then send one real test email.