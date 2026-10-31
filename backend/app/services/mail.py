import smtplib
import ssl
from flask import current_app
from flask_mail import Mail, Connection


class BoundedConnection(Connection):
    def configure_host(self):
        context = ssl.create_default_context()
        if self.mail.use_ssl:
            host = smtplib.SMTP_SSL(self.mail.server, self.mail.port, timeout=10, context=context)
        else:
            host = smtplib.SMTP(self.mail.server, self.mail.port, timeout=10)
        host.set_debuglevel(0)
        if self.mail.use_tls:
            host.starttls(context=context)
        if self.mail.username and self.mail.password:
            host.login(self.mail.username, self.mail.password)
        return host


class BoundedMail(Mail):
    def connect(self):
        return BoundedConnection(current_app.extensions["mail"])
