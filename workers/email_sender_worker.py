"""
Email Sender Worker — 通过 Gmail SMTP 批量发送邮件
使用 Google App Password 认证
"""
import smtplib
import time
import random
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import db
from workers.base_worker import BaseWorker

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


class EmailSenderWorker(BaseWorker):
    def __init__(self, log_callback, progress_callback=None,
                 message_name="", subject="", body="",
                 source=None, daily_limit=50, interval_min=30, interval_max=60):
        super().__init__(log_callback, progress_callback)
        self.message_name = message_name
        self.subject = subject
        self.body = body
        self.source = source
        self.daily_limit = daily_limit
        self.interval_min = interval_min
        self.interval_max = interval_max

    def run(self):
        # 读取 Gmail 设置
        gmail_address = db.get_setting("gmail_address", "")
        gmail_app_password = db.get_setting("gmail_app_password", "")

        if not gmail_address or not gmail_app_password:
            self.log("请先在「设置」页填写 Gmail 地址和 App Password")
            return

        if not self.subject or not self.body:
            self.log("邮件主题或正文为空，请先在「文案」页配置邮件模板")
            return

        # 获取待发送邮箱
        emails = db.get_unsent_emails(source=self.source)
        if not emails:
            self.log("没有待发送的邮箱")
            return

        # 限制每日发送量
        if self.daily_limit > 0 and len(emails) > self.daily_limit:
            self.log(f"待发 {len(emails)} 封，限制本次发送 {self.daily_limit} 封")
            emails = emails[:self.daily_limit]

        self.log(f"待发 {len(emails)} 封邮件，发件人：{gmail_address}")

        # 连接 SMTP
        try:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
            server.ehlo()
            server.starttls()
            server.login(gmail_address, gmail_app_password)
            self.log("SMTP 登录成功")
        except Exception as e:
            self.log(f"SMTP 登录失败：{e}")
            return

        sent = 0
        failed = 0

        try:
            for idx, to_email in enumerate(emails):
                if self._stop:
                    self.log("已停止")
                    break

                self.log(f"[{idx+1}/{len(emails)}] {to_email}")

                try:
                    msg = MIMEMultipart("alternative")
                    msg["From"] = gmail_address
                    msg["To"] = to_email
                    msg["Subject"] = self.subject
                    msg.attach(MIMEText(self.body, "plain", "utf-8"))

                    server.sendmail(gmail_address, to_email, msg.as_string())
                    db.log_send(to_email, "email", self.source or "email", self.message_name)
                    sent += 1
                    self.log(f"  ✓ 已发送")

                except smtplib.SMTPRecipientsRefused:
                    self.log(f"  ✗ 地址无效，跳过")
                    failed += 1
                except smtplib.SMTPServerDisconnected:
                    self.log("  SMTP 断开，重新连接…")
                    try:
                        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
                        server.ehlo()
                        server.starttls()
                        server.login(gmail_address, gmail_app_password)
                        self.log("  重连成功")
                        # 重试当前邮件
                        server.sendmail(gmail_address, to_email, msg.as_string())
                        db.log_send(to_email, "email", self.source or "email", self.message_name)
                        sent += 1
                        self.log(f"  ✓ 重试发送成功")
                    except Exception as e2:
                        self.log(f"  ✗ 重连失败：{str(e2)[:60]}")
                        failed += 1
                except Exception as e:
                    self.log(f"  ✗ 发送失败：{str(e)[:60]}")
                    failed += 1

                self.progress(idx + 1, len(emails))

                # 发送间隔
                if idx < len(emails) - 1 and not self._stop:
                    wait = random.uniform(self.interval_min, self.interval_max)
                    self.log(f"  等待 {wait:.0f} 秒…")
                    # 分段 sleep 以便响应停止信号
                    slept = 0
                    while slept < wait and not self._stop:
                        time.sleep(min(2, wait - slept))
                        slept += 2

        finally:
            try:
                server.quit()
            except Exception:
                pass

        self.log(f"\n完成！发送 {sent} 封，失败 {failed} 封")
