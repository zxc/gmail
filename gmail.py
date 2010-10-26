#
# gmail.py - interact with Gmail through Python
# ---------------------------------------------
#

import imaplib
import smtplib
import email

class Gmail(object):
    # Configuration specific to Gmail
    IMAP_HOST = 'imap.gmail.com'
    IMAP_PORT = 993

    SMTP_HOST = 'smtp.gmail.com'
    SMTP_PORT = 587

    # Create a Gmail instance to login.
    # username is your gmail address, '@gmail.com' optional.
    # password is your password.
    def __init__(self, username, password):
        if '@' not in username: username += '@gmail.com'
        self.username = username

        # Create the IMAP connection for interacting with Gmail
        self.imap = imaplib.IMAP4_SSL(host=self.IMAP_HOST, port=self.IMAP_PORT)
        self.imap.login(user=username, password=password)

        # Create the SMTP connection for sending mail
        self.smtp = smtplib.SMTP(host=self.SMTP_HOST, port=self.SMTP_PORT)
        self.smtp.helo()
        self.smtp.starttls()
        self.smtp.login(user=username, password=password)

        self.search = Search(self)
        self.labels = LabelSet(self)

    # Close connections to Gmail
    def logout(self, close_imap=True, close_smtp=True):
        if close_imap:
            self.imap.close()
            self.imap.logout()
            self.imap = None
        if close_smtp:
            self.smtp.quit()
            self.smtp = None

    def fetch(self, id):
        if type(id) == int: id = str(id)
        return Message(self, imap=self.imap, id=id)

    # Send a gmail.Message object
    # If no from address is specified, your Gmail username is used
    def send(self, message):
        if self.smtp is None:     raise Exception('No SMTP connection')
        if len(message._to) == 0: raise Exception('To address required')

        if message.from_address() == '':
            message.from_address(self.username)

        self.smtp.sendmail(from_addr = message.from_address(),
                           to_addrs  = message.to_address(),
                           msg       = message.message.as_string())

class Search(object):
    def __init__(self, parent):
        self.parent = parent
        self.messages = []
        self.ids = []
        self.modified = False

    def clear(self):
        self.messages = []
        self.ids = []
        self.modified = False

    def _execute(self, *args):
        status, ids = self.parent.imap.search(None, *args)
        for id in ids[0].split():
            if id in self.ids: continue
            self.messages.append(Message(self.parent, imap=self.parent.imap, id=id))
            self.ids.append(id)
        self.modified = True
        return self

    def first(self):
        if not self.modified: raise Exception('No searches performed yet')
        if len(self.messages) == 0: return None
        return self.messages[0]

    def all(self):
        if not self.modified: self._execute('ALL')
        return self.messages

    def count(self):
        return len(self.messages)

    # Clean these up, maybe with __getattr__
    def unread(self):         return self._execute('UNSEEN')
    def read(self):           return self._execute('SEEN')
    def to(self, query):      return self._execute('TO', '"%s"' % query)
    def from_(self, query):   return self._execute('FROM', '"%s"' % query)
    def subject(self, query): return self._execute('SUBJECT', '"%s"' % query)
    def bcc(self, query):     return self._execute('BCC', '"%s"' % query)
    def cc(self, query):      return self._execute('CC', '"%s"' % query)
    def body(self, query):    return self._execute('BODY', '"%s"' % query)

    def label(self, query):   return self._execute('LABEL', '"%s"' % query)

    def since(self, date):
        pass    # 'SINCE', '"date"'

    def before(self, date):
        pass    # 'BEFORE', '"date"'

    def on(self, date):
        pass    # 'ON', '"date"'

    def __call__(self, query):
        pass

class LabelSet(object):
    def __init__(self, parent):
        self.parent = parent
        self.labels = None
        self.current = 'INBOX'
        self.count = None
        self.switch('INBOX')

    def exists(self, label):
        if self.labels is None: self.all()
        return label in self.labels

    def switch(self, label, shortcuts_on=True):
        shortcuts = { 'all':       '[Gmail]/All Mail'
                    , 'drafts':    '[Gmail]/Drafts'
                    , 'important': '[Gmail]/Important'
                    , 'sent':      '[Gmail]/Sent Mail'
                    , 'spam':      '[Gmail]/Spam'
                    , 'starred':   '[Gmail]/Starred'
                    , 'trash':     '[Gmail]/Trash'
                    }
        if shortcuts_on and label.lower() in shortcuts:
            label = shortcuts[label.lower()]

        ret = self.parent.imap.select(label)
        self.current = label

        self.parent.search.clear()

        try:
            self.count = int(ret[1][0])
            return self.count
        except: return None

    def create(self, label):
        self.parent.imap.create(label)
        if self.labels is None: self.all()
        self.labels.append(label)

    def delete(self, label):
        self.parent.imap.delete(label)
        if self.labels is None: self.all()
        if label in self.labels: self.labels.remove(label)

    def rename(self, old, new):
        self.parent.imap.rename(old, new)
        if self.labels is None: self.all()
        if old in self.labels: self.labels.remove(label)
        self.labels.append(new)

    def all(self):
        _, ret = self.parent.imap.list()
        # ret is a list of results in the form of:
        # '(\\HasNoChildren) "/" "[Gmail]/All Mail"'
        self.labels = [a.split('"')[-2] for a in ret]
        return self.labels

class Message(object):
    def __init__(self, parent, imap=None, id=-1):
        self.parent = parent
        self.imap = imap
        self.id = id
        self._has_content = False

    def fill(self, to_addresses='', from_address='', subject='', body=''):
        self.message = email.message.Message()
        self.body(body)
        self.subject(subject)
        self.from_address(from_address)
        self.to_address(to_addresses)
        self._has_content = True
        return self

    def fetch(self):
        if self._has_content: return self
        if self.imap is None or self.id == -1:
            raise Exception('Message has id/IMAP connection')

        # to get uid: self.imap.fetch(self.id, 'UID')
        # to get flags: self.imap.fetch(self.id, 'FLAGS')
        status, data = self.imap.fetch(self.id, '(RFC822)')
        if data[0] is None: return None

        self.message = email.message_from_string(data[0][1])

        self.to_address(self.message['Delivered-To'] or self.message['To'] or '')
        self.from_address(self.message['From'] or '')
        self.body(self.message.get_payload() or '')
        self.subject(self.message['Subject'] or '')

        self._has_content = True
        return self

    def from_address(self, addr=None):
        if addr is None: 
            if self._has_content: return self._from
            else: return self.fetch().from_address()

        self._from = addr
        del self.message['From']
        self.message['From'] = addr

    def to_address(self, addr=None):
        if addr is None: 
            if self._has_content: return self._to
            else: return self.fetch().to_address()

        del self.message['To']
        if type(addr) == type([]):
            self._to = addr
            self.message['To'] = addr.join(', ')
        else:
            self._to = [s.strip() for s in addr.split(', ')]
            self.message['To'] = addr
    
    def subject(self, subj=None):
        if subj is None: 
            if self._has_content: return self._subject
            else: return self.fetch().subject()

        self._subject = subj
        del self.message['Subject']
        self.message['Subject'] = subj

    def body(self, body=None):
        if body is None: 
            if self._has_content: return self._body
            else: return self.fetch().body()

        self._body = body
        self.message.set_payload(body)

    def flag(self, flag): self.imap.store(self.id, '+FLAGS', flag)
    def unflag(self, flag): self.imap.store(self.id, '-FLAGS', flag)

    def mark_read(self): self.flag('\\Seen')
    def mark_unread(self): self.unflag('\\Seen')
    def delete(self): self.flag('\\Deleted')

    def add_label(self, label):
        if not self.parent.labels.exists(label):
            self.parent.labels.create(label)
        self.imap.copy(self.id, label)

    # Might add remove_label and move_to functions
    # Have to look into imap.uid()


