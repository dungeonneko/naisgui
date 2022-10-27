import json
import os
import subprocess
import time
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


def read_text(path: str):
    with open(path, 'rt') as f:
        return f.read()


def json_to_text(obj):
    return json.dumps(obj, sort_keys=True, indent=2)


class NaisJob(QThread):
    jobStatusChanged = Signal(int, int, str)

    def __init__(self):
        super().__init__()
        self._task = []
        self._exit = False
        self._canceling = False
        self._num = 0
        self._done = 0

    def __del__(self):
        self._exit = True
        self.stop()
        self.wait()

    def run(self):
        while not self._exit:
            if len(self._task) > 0:
                self._done += 1
                self.jobStatusChanged.emit(self._done, self._num, f'Processing... {self._done}/{self._num}')
                self._task.pop(0)()
                if len(self._task) == 0 and not self._canceling:
                    self.jobStatusChanged.emit(self._done, self._num, f'Completed. {self._done}/{self._num}')
                    self._done = 0
                    self._num = 0
            if self._canceling:
                self.jobStatusChanged.emit(0, 1, f'Cancelled.')
                self._done = 0
                self._num = 0
                self._canceling = False
            time.sleep(0.5)
            continue

    def append(self, task):
        self._task.append(task)
        self._num += 1
        self.jobStatusChanged.emit(self._done, self._num, f'Processing... {self._done}/{self._num}')

    def cancel(self):
        self._task.clear()
        self._canceling = True
        self.jobStatusChanged.emit(self._done, self._num, f'Cancelling... {self._done}/{self._num}')


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

    def setImage(self, path):
        self._pm = QPixmap(path)
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
