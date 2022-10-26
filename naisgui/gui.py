import datetime
import json
import uuid
import requests
import sys
from naisgui.nais import Nais
from naisgui.util import *
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *


g_nais = Nais()
g_job = NaisJob()


class GuiPrompt(QWidget):
    generated = Signal(str)
    DefaultScript = '''\
import random

# Random Seed, Sampler, Scale
data['parameters']['seed'] = random.randint(0, 4294967295)
data['parameters']['sampler'] = random.choice(['k_euler_ancestral', 'k_euler', 'k_lms', 'plms', 'ddim'])
data['parameters']['scale'] = random.choice([4.0, 6.0, 8.0, 10.0, 12.0])

# Scaling Up by Image Generation
# N is repeat times
# I is index
# data['parameters']['seed'] = 1
# data['parameters']['scale'] = 2.0 + (12.0 - 2.0) * I / N
'''

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Input')
        self._text = NaisCodeEditor()
        self._text.setPlainText('''\
{
  "input": "Hatsune Miku",
  "model": "nai-diffusion",
  "parameters": {
    "n_samples": 1,
    "seed": 1,
    "noise": 0.2,
    "strength": 0.7,
    "steps": 28,
    "scale": 11,
    "width": 512,
    "height": 768,
    "uc": "lowres, bad anatomy, bad hands, text, error, missing fingers, extra digit, fewer digits, cropped, worst quality, low quality, normal quality, jpeg artifacts, signature, watermark, username, blurry,",
    "sampler": "k_euler_ancestral"
  }
}
''')
        self._tweak = NaisCodeEditor()
        self._tweak.setPlainText(GuiPrompt.DefaultScript)
        self._preview = NaisCodeEditor()
        self._preview.setReadOnly(True)
        self._repeat = QSpinBox()
        self._repeat.setMinimum(1)
        self._repeat.setMaximum(5000)
        self._repeat.setSuffix(' Times')
        self._buttonStart = QPushButton('Start')
        self._buttonStart.pressed.connect(self.generate)
        self._buttonStop = QPushButton('Stop')
        self._buttonStop.pressed.connect(g_job.cancel)
        layout = QVBoxLayout()
        form = QFormLayout()
        form.addRow('Data:', self._text)
        form.addRow('Tweak:', self._tweak)
        form.addRow('Preview:', self._preview)
        form.addRow('Repeat:', self._repeat)
        layout.addLayout(form)
        layout.addWidget(self._buttonStart)
        layout.addWidget(self._buttonStop)
        self.setLayout(layout)

        self._text.textChanged.connect(self.on_context_changed)
        self._tweak.textChanged.connect(self.on_context_changed)
        self.on_context_changed()

    def newTweakScript(self):
        self._tweak.setPlainText(GuiPrompt.DefaultScript)

    def saveTweakScript(self):
        fpath, _ = QFileDialog.getSaveFileName(self, 'Save Script', g_nais.output_folder(), '*.py')
        if fpath:
            with open(fpath, 'wt') as f:
                f.write(self._tweak.toPlainText())

    def openTweakScript(self):
        fpath, _ = QFileDialog.getOpenFileName(self, 'Open Script', g_nais.output_folder(), '*.py')
        if fpath:
            self._tweak.setPlainText(read_text(fpath))

    def _job_impl(self, name, text: str):
        try:
            g_nais.save_image(name, text)
            self.generated.emit(name)
        except requests.exceptions.ChunkedEncodingError as e:
            print(e)
            pass
        except requests.exceptions.ConnectionError as e:
            print(e)
            pass
        except requests.exceptions.ReadTimeout as e:
            print(e)
            pass
        except RuntimeError:
            pass

    def on_context_changed(self):
        self._preview.setPlainText(self.gen(self._repeat.value(), 0))

    def gen(self, N, I):
        data = json.loads(self._text.toPlainText())
        try:
            exec(self._tweak.toPlainText())
        except Exception as e:
            return str(e)
        try:
            text = json.dumps(data, sort_keys=True, indent=2)
        except Exception as e:
            return str(e)
        return text

    def generate(self):
        n = self._repeat.value()
        for i in range(n):
            g_job.append(lambda x=self.gen(n, i): self._job_impl(datetime.datetime.now().strftime('%Y%m%d%H%M%S'), x))

    def setText(self, name: str, text: str):
        self._text.setPlainText(text)


class GuiImageList(QListWidget):
    itemChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image List')
        self.setContentsMargins(0,0,0,0)
        self.setSpacing(0)
        self.setIconSize(QSize(64, 64))
        self.setViewMode(QListWidget.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.itemSelectionChanged.connect(self.on_item_selection_changed)
        self._items = {}
        for f in os.listdir(g_nais.output_folder()):
            if not f.endswith('.json'):
                continue
            self.load(os.path.splitext(f)[0])

    def on_item_selection_changed(self):
        item = self.currentItem()
        if item is None:
            return
        name = item.data(Qt.UserRole + 0)
        self.itemChanged.emit(name)

    def load(self, name: str):
        base = os.path.join(g_nais.output_folder(), name)
        self.add(name)

    def add(self, name: str):
        base = os.path.join(g_nais.output_folder(), name)
        item = QListWidgetItem()
        item.setIcon(QIcon(base + '_tm.png'))
        item.setData(Qt.UserRole + 0, name)
        self.addItem(item)

    def delete_selected_images(self):
        for i in self.selectedItems():
            name = i.data(Qt.UserRole + 0)
            base = os.path.join(g_nais.output_folder(), name)
            if os.path.exists(base + '.png'):
                os.remove(base + '.png')
            if os.path.exists(base + '.json'):
                os.remove(base + '.json')
            if os.path.exists(base + '_tm.png'):
                os.remove(base + '_tm.png')
            if os.path.exists(base + '_wc_pos.png'):
                os.remove(base + '_wc_pos.png')
            if os.path.exists(base + '_wc_neg.png'):
                os.remove(base + '_wc_neg.png')
            self.takeItem(self.row(i))


class GuiImageViewer(NaisImage):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Viewer')
        self.setMinimumSize(QSize(256, 256))

    def setImage(self, name):
        super().setImage(os.path.join(g_nais.output_folder(), name + '.png'))


class GuiImageData(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Image Data')
        self._params = NaisCodeEditor()
        self._params.setReadOnly(True)
        self._pos = NaisImage()
        self._neg = NaisImage()
        layout = QVBoxLayout()
        layout.addWidget(self._params)
        layout2 = QHBoxLayout()
        layout2.addWidget(self._pos)
        layout2.addWidget(self._neg)
        layout.addLayout(layout2)
        self.setLayout(layout)

    def setImage(self, name):
        base = os.path.join(g_nais.output_folder(), name)
        self._params.setPlainText(read_text(base + '.json'))
        self._pos.setImage(base + '_wc_pos.png')
        self._neg.setImage(base + '_wc_neg.png')


class GuiMain(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Nais GUI')
        self._job = g_job
        self._inipath = os.path.join(g_nais.output_folder(), 'layout.ini')
        self._prompt = GuiPrompt()
        self._image_list = GuiImageList()
        self._image_viewer = GuiImageViewer()
        self._image_data = GuiImageData()
        self._progress = QProgressBar()
        self._progress.setAlignment(Qt.AlignCenter)
        self._progress.setTextVisible(False)
        self._prompt.generated.connect(self._image_list.add)
        self._image_list.itemChanged.connect(self._image_viewer.setImage)
        self._image_list.itemChanged.connect(self._image_data.setImage)
        self._job.jobStatusChanged.connect(self.on_job_status_changed)
        self.statusBar().addWidget(self._progress, True)
        self.setDockOptions(QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks)
        self.dock(self._prompt, Qt.LeftDockWidgetArea)
        self.dock(self._image_viewer, Qt.RightDockWidgetArea)
        self.dock(self._image_data, Qt.RightDockWidgetArea)
        self.dock(self._image_list, Qt.RightDockWidgetArea)

        menu_file = self.menuBar().addMenu('File')
        action = QAction(self)
        action.setText('New Script')
        action.setShortcut('Ctrl+N')
        action.triggered.connect(self._prompt.newTweakScript)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Save Script')
        action.setShortcut('Ctrl+S')
        action.triggered.connect(self._prompt.saveTweakScript)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Open Script')
        action.setShortcut('Ctrl+O')
        action.triggered.connect(self._prompt.openTweakScript)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Exit')
        action.triggered.connect(self.close)
        menu_file.addAction(action)
        menu_edit = self.menuBar().addMenu('Edit')
        action = QAction(self)
        action.setText('Delete Selected Images')
        action.setShortcut('Del')
        action.triggered.connect(self._image_list.delete_selected_images)
        menu_edit.addAction(action)
        menu_window = self.menuBar().addMenu('Window')
        menu_window.addAction(self._prompt.parent().toggleViewAction())
        menu_window.addAction(self._image_list.parent().toggleViewAction())
        menu_window.addAction(self._image_data.parent().toggleViewAction())
        menu_window.addAction(self._image_viewer.parent().toggleViewAction())
        self._job.start()
        self.load_layout()

    def closeEvent(self, event) -> None:
        self.save_layout()
        super().closeEvent(event)

    def load_layout(self):
        if os.path.exists(self._inipath):
            s = QSettings(self._inipath, QSettings.IniFormat)
            self.restoreGeometry(s.value('geometry'))
            self.restoreState(s.value('state'))

    def save_layout(self):
        s = QSettings(self._inipath, QSettings.IniFormat)
        s.setValue('geometry', self.saveGeometry())
        s.setValue('state', self.saveState())

    def on_job_status_changed(self, done: int, num: int, text: str):
        self._progress.setFormat(text)
        self._progress.setMaximum(num)
        self._progress.setValue(done)

    def dock(self, widget, area):
        dock = QDockWidget()
        dock.setWidget(widget)
        dock.setWindowTitle(widget.windowTitle())
        dock.setObjectName(widget.windowTitle())
        dock.setAllowedAreas(Qt.AllDockWidgetAreas)
        self.addDockWidget(area, dock)


def NaisGui():
    app = QApplication(sys.argv)

    # LOG IN
    username = os.environ['NAI_USERNAME'] if 'NAI_USERNAME' in os.environ else ''
    password = os.environ['NAI_PASSWORD'] if 'NAI_PASSWORD' in os.environ else ''
    if not username or not password:
        dialog = NaisLogin()
        dialog.exec_()
        username = dialog.username()
        password = dialog.password()
        dialog = None
    while True:
        try:
            g_nais.login(username, password)
        except:
            dialog = NaisLogin()
            dialog.exec_()
            username = dialog.username()
            password = dialog.password()
            dialog = None
            continue
        else:
            break

    wnd = GuiMain()
    wnd.show()
    sys.exit(app.exec_())
