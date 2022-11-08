import json
import os
import subprocess
import time
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
import threading


def read_text(path: str):
    try:
        with open(path, 'rt') as f:
            return f.read()
    except FileNotFoundError as e:
        print(e)
        return ''


def json_to_text(obj):
    return json.dumps(obj, sort_keys=True, indent=2)

def text_to_json(txt):
    return json.loads(txt.replace('\r', '').replace('\t', '').replace('\n', '').replace('\u3000', ' '))

class NaisJob(QThread):
    jobStatusChanged = Signal(int, int, str)

    def __init__(self):
        super().__init__()
        self._task = []
        self._exit = False
        self._canceling = False
        self._max = 0
        self._lock = threading.Lock()

    def __del__(self):
        self._exit = True
        self.stop()
        self.wait()

    def run(self):
        while not self._exit:
            if len(self._task) > 0:
                self._lock.acquire()
                num = len(self._task)
                self._lock.release()
                if num > 0:
                    self._lock.acquire()
                    prg = self._max - num
                    self.jobStatusChanged.emit(prg, num, f'Processing... {prg}/{self._max}')
                    tsk = self._task.pop(0)[1]
                    self._lock.release()
                    tsk()
                if len(self._task) == 0 and not self._canceling:
                    self.jobStatusChanged.emit(1, 1, f'Completed. {self._max}/{self._max}')
                    self._max = 0
            time.sleep(0.125)
            continue

    def append(self, ch: int, task: callable):
        self._lock.acquire()
        self._task.append((ch, task))
        num = len(self._task)
        self._max = max(self._max, num)
        prg = self._max - num
        self.jobStatusChanged.emit(prg, self._max, f'Processing... {prg}/{self._max}')
        self._lock.release()

    def cancel(self, ch: int):
        self._lock.acquire()
        self._task = [(c, task) for c, task in self._task if c != ch]
        num = len(self._task)
        self._max = max(self._max, num)
        prg = self._max - num
        self.jobStatusChanged.emit(prg, self._max, f'Processing... {prg}/{self._max}')
        self._lock.release()


class NaisLogin(QDialog):
    def __init__(self):
        super().__init__()
        self._username = QLineEdit()
        self._password = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._saveToEnv = QCheckBox()
        layout = QFormLayout()
        layout.addRow('Email:', self._username)
        layout.addRow('Password:', self._password)
        layout.addRow('Set Environment Variable', self._saveToEnv)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
        self.setLayout(layout)
        self.setWindowTitle('Login')

    def accept(self) -> None:
        if self._saveToEnv.isChecked():
            if os.name == 'posix':
                subprocess.Popen(f'export NAI_USERNAME="{self.username()}"', shell=True).wait()
                subprocess.Popen(f'export NAI_PASSWORD="{self.password()}"', shell=True).wait()
            if os.name == 'nt':
                subprocess.Popen(f'setx NAI_USERNAME "{self.username()}"', shell=True).wait()
                subprocess.Popen(f'setx NAI_PASSWORD "{self.password()}"', shell=True).wait()
        super().accept()

    def username(self):
        return self._username.text()

    def password(self):
        return self._password.text()


class NaisHighlighter(QSyntaxHighlighter):
    def __init__(self, parent):
        super().__init__(parent)
        self.rules = []
        # TODO:

    def highlightBlock(self, text):
        for rule in self.rules:
            exp = QRegExp(rule.pattern)
            index = exp.indexIn(text)
            while index >= 0:
                length = exp.matchedLength()
                self.setFormat(index, length, rule.format)
                index = text.indexOf(exp, index + length)
        self.setCurrentBlockState(0)


class NaisCodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        f = QFont('monospace')
        f.setStyleHint(QFont.Monospace)
        self.setFont(f)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._syntax = NaisHighlighter(self.document())


class NaisImage(QLabel):
    def __init__(self):
        super().__init__()
        self._pm = None
        self.setMinimumSize(QSize(8, 8))
        self.setSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.MinimumExpanding)
        self.setScaledContents(False)
        self.smoothTransformation = False

    def toImagePos(self, x, y):
        sz = self.size()
        pm = self.pixmap().size()
        x -= (int)(sz.width() / 2 - pm.width() / 2)
        y -= (int)(sz.height() / 2 - pm.height() / 2)
        ss = self._pm.size()
        return (int((x / pm.width()) * ss.width()), int((y / pm.height()) * ss.height()))

    def setImage(self, path_or_img):
        self._pm = QPixmap(path_or_img) if path_or_img is str else QPixmap.fromImage(path_or_img).copy()
        self.setPixmap(self._pm.scaled(
            self.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation if self.smoothTransformation else Qt.FastTransformation))

    def resizeEvent(self, eve):
        super().resizeEvent(eve)
        if self._pm is not None:
            self.setPixmap(self._pm.scaled(
                self.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation if self.smoothTransformation else Qt.FastTransformation))
