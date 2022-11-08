import copy
import datetime
import random
import send2trash
import sys
from naisgui.nais import *
from naisgui.util import *
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PIL.ImageQt import ImageQt


g_nais = Nais()
g_job = NaisJob()

JOB_CHANNEL_MAIN = 0
JOB_CHANNEL_VARIATIONS = 1


class GuiFromToStep(QWidget):
    def __init__(self, SpinBoxType):
        super().__init__()
        self.fr = SpinBoxType()
        self.to = SpinBoxType()
        self.step = SpinBoxType()
        layout = QHBoxLayout()
        layout.setMargin(0)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel('from:'))
        layout.addWidget(self.fr)
        layout.addWidget(QLabel('to:'))
        layout.addWidget(self.to)
        layout.addWidget(QLabel('step:'))
        layout.addWidget(self.step)
        layout.addStretch()
        self.setLayout(layout)

    def setMinimum(self, value):
        self.fr.setMinimum(value)
        self.to.setMinimum(value)

    def setMaximum(self, value):
        self.fr.setMaximum(value)
        self.to.setMaximum(value)

    def setValue(self, value):
        self.fr.setValue(value)
        self.to.setValue(value)

    def range(self):
        i = self.fr.value()
        n = self.to.value()
        s = self.step.value()
        if s > 0.0:
            while i <= n:
                yield i
                i += s


class GuiImageVariations(QWidget):
    generated = Signal(str)

    def __init__(self):
        super().__init__()
        self._data = {}
        self._input = QPlainTextEdit()
        self._scale = GuiFromToStep(QDoubleSpinBox)
        self._scale.setMinimum(1.1)
        self._scale.setMaximum(100.0)
        self._scale.setValue(11)
        self._scale.step.setMinimum(0.01)
        self._scale.step.setMaximum(100.0)
        self._scale.step.setValue(0.5)
        self._step = GuiFromToStep(QSpinBox)
        self._step.setMinimum(1)
        self._step.setMaximum(50)
        self._step.step.setMinimum(1)
        self._step.step.setMaximum(49)
        self._step.setValue(28)
        self._samplers = [
            QCheckBox('k_euler_ancestral'),
            QCheckBox('k_euler'),
            QCheckBox('k_lms'),
            QCheckBox('plms'),
            QCheckBox('ddim')]
        self._randomSeed = QCheckBox()
        self._uc = QPlainTextEdit()
        self._repeat = QSpinBox()
        self._repeat.setSuffix(' Times')
        self._repeat.setMinimum(1)
        self._buttonStart = QPushButton('Start')
        self._buttonStart.pressed.connect(self.generate)
        self._buttonStop = QPushButton('Stop')
        self._buttonStop.pressed.connect(lambda: g_job.cancel(JOB_CHANNEL_VARIATIONS))
        smplayout = QVBoxLayout()
        for smp in self._samplers:
            smplayout.addWidget(smp)
        vlayout = QVBoxLayout()
        layout = QFormLayout()
        layout.addRow('Input:', self._input)
        layout.addRow('Sampler:', smplayout)
        layout.addRow('Scale:', self._scale)
        layout.addRow('Steps:', self._step)
        layout.addRow('Random Seed:', self._randomSeed)
        layout.addRow('UC:', self._uc)
        layout.addRow('Repeat:', self._repeat)
        vlayout.addLayout(layout)
        hlayout = QHBoxLayout()
        hlayout.setMargin(0)
        hlayout.setContentsMargins(0, 0, 0, 0)
        hlayout.addWidget(self._buttonStart)
        hlayout.addWidget(self._buttonStop)
        vlayout.addLayout(hlayout)
        vlayout.addStretch()
        self.setLayout(vlayout)
        self.setWindowTitle('Variations')

    def setImage(self, name):
        try:
            base = os.path.join(g_nais.output_folder(), name)
            self._data = text_to_json(read_text(base + '.json'))
            self._input.setPlainText(self._data['input'])
            self._uc.setPlainText(self._data['parameters']['uc'])
        except json.JSONDecodeError as e:
            self._data = {}
            print(e)
        except FileNotFoundError as e:
            self._data = {}
            print(e)

    def _job_impl(self, name, text: str):
        for i in range(5):
            try:
                g_nais.save_image(name, text)
                self.generated.emit(name)
                break
            except Exception as e:
                print(e)
                time.sleep(1)
            continue

    def gen(self):
        data = copy.deepcopy(self._data)
        data['input'] = self._input.toPlainText()
        data['parameters']['uc'] = self._uc.toPlainText()
        samplers = [smp.text() for smp in self._samplers if smp.isChecked()]
        if not samplers:
            samplers = [data['parameters']['sampler']]
        for smp in samplers:
            data['parameters']['sampler'] = smp
            for scl in self._scale.range():
                data['parameters']['scale'] = scl
                for stp in self._step.range():
                    data['parameters']['steps'] = stp
                    for rep in range(self._repeat.value()):
                        if self._randomSeed.isChecked():
                            data['parameters']['seed'] = random.randint(0, 4294967295)
                        yield json_to_text(data)

    def generate(self):
        if not self._data:
            return
        for x in self.gen():
            g_job.append(JOB_CHANNEL_VARIATIONS,
                         lambda _x=x: self._job_impl(datetime.datetime.now().strftime('%Y%m%d%H%M%S'), _x))


class GuiData(QWidget):
    textChanged = Signal()

    def __init__(self):
        super().__init__()
        self._text = NaisCodeEditor()
        self._text.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self._text.textChanged.connect(self.textChanged.emit)
        self._text.setAcceptDrops(False)
        self._mask = QCheckBox('Never change n_sample, steps, width, height by Image Drop')
        self._mask.setChecked(True)
        layout = QVBoxLayout()
        layout.setContentsMargins(0,0,0,0)
        layout.setMargin(0)
        layout.addWidget(self._mask)
        layout.addWidget(self._text)
        self.setLayout(layout)
        self.setAcceptDrops(True)
        self.setToolTip('Instead of manual input, You can also drop an image with meta info from local or web browser')

    def toPlainText(self):
        return self._text.toPlainText()

    def setPlainText(self, s):
        self._text.setPlainText(s)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.setDropAction(Qt.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        url = event.mimeData().urls()[0]
        if url.isLocalFile():
            src, ret = nais_data_from_local_image(url.toLocalFile())
        else:
            src, ret = nais_data_from_uploaded_image(url.toString())

        data = {}
        try:
            data = text_to_json(self.toPlainText())
        except Exception as e:
            pass

        if 'input' in src:
            data['input'] = src['input']
        if 'parameters' in src:
            for k, v in src['parameters'].items():
                if self._mask.isChecked() and k in ['n_samples', 'steps', 'width', 'height']:
                    continue
                data['parameters'][k] = v

        self.setPlainText(json_to_text(data))


class GuiPrompt(QWidget):
    generated = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('Input')
        self._text = GuiData()
        self._tweak = NaisCodeEditor()
        self._preview = NaisCodeEditor()
        self._preview.setReadOnly(True)
        self._preview.setLineWrapMode(QPlainTextEdit.WidgetWidth)
        self._repeat = QSpinBox()
        self._repeat.setMinimum(1)
        self._repeat.setMaximum(50000)
        self._repeat.setSuffix(' Times')
        self._buttonStart = QPushButton('Start')
        self._buttonStart.pressed.connect(self.generate)
        self._buttonStop = QPushButton('Stop')
        self._buttonStop.pressed.connect(lambda: g_job.cancel(JOB_CHANNEL_MAIN))
        layout = QVBoxLayout()
        form = QFormLayout()
        form.addRow('Data:', self._text)
        form.addRow('Tweak:', self._tweak)
        form.addRow('Preview:', self._preview)
        form.addRow('Repeat:', self._repeat)
        layout.addLayout(form)
        hlayout = QHBoxLayout()
        hlayout.setMargin(0)
        hlayout.setContentsMargins(0,0,0,0)
        hlayout.addWidget(self._buttonStart)
        hlayout.addWidget(self._buttonStop)
        layout.addLayout(hlayout)
        self.setLayout(layout)
        self._text.textChanged.connect(self.on_context_changed)
        self._tweak.textChanged.connect(self.on_context_changed)
        self.loadDfaultInput()
        self.newTweakScript()
        self.on_context_changed()

    def loadDfaultInput(self):
        text = read_text(os.path.join(g_nais.output_folder(), 'defaultinput.json'))
        if not text:
            text = '''\
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
'''
        self._text.setPlainText(text)

    def saveDefaultInput(self):
        try:
            text = json_to_text(text_to_json(self._text.toPlainText()))
            with open(os.path.join(g_nais.output_folder(), 'defaultinput.json'), 'wt') as f:
                f.write(text)
        except json.JSONDecodeError as e:
            print(e)

    def newTweakScript(self):
        text = read_text(os.path.join(g_nais.output_folder(), 'defaultscript.py'))
        if not text:
            text = '''\
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
        self._tweak.setPlainText(text)

    def saveDefaultScript(self):
        with open(os.path.join(g_nais.output_folder(), 'defaultscript.py'), 'wt') as f:
            f.write(self._tweak.toPlainText())

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
        while True:
            try:
                g_nais.save_image(name, text)
                self.generated.emit(name)
                break
            except Exception as e:
                print(e)
                time.sleep(1)
            continue

    def on_context_changed(self):
        self._preview.setPlainText(self.gen(self._repeat.value(), 0))

    def gen(self, N, I):
        try:
            data = text_to_json(self._text.toPlainText())
            exec(self._tweak.toPlainText())
        except Exception as e:
            return str(e)
        try:
            text = json_to_text(data)
        except Exception as e:
            return str(e)
        return text

    def generate(self):
        n = self._repeat.value()
        for i in range(n):
            g_job.append(JOB_CHANNEL_MAIN, lambda x=self.gen(n, i): self._job_impl(datetime.datetime.now().strftime('%Y%m%d%H%M%S'), x))

    def setText(self, name: str, text: str):
        self._text.setPlainText(text)


class GuiImageList(QWidget):
    itemChanged = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle('List')
        self._filter = QLineEdit()
        self._filter.textChanged.connect(self.on_filter_changed)
        self._list = QListWidget()
        self._list.setAcceptDrops(False)
        self._list.setContentsMargins(0,0,0,0)
        self._list.setSpacing(0)
        self._list.setIconSize(QSize(64, 64))
        self._list.setViewMode(QListWidget.IconMode)
        self._list.setResizeMode(QListWidget.ResizeMode.Adjust)
        self._list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._list.itemSelectionChanged.connect(self.on_item_selection_changed)
        self._list.customContextMenuRequested.connect(self.on_custom_menu_requested)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.startDrag = self.startDrag
        self.actionDeleteSelectedImages = QAction(self)
        self.actionDeleteSelectedImages.setText('Delete Selected Images')
        self.actionDeleteSelectedImages.setShortcut('Del')
        self.actionDeleteSelectedImages.triggered.connect(self.delete_selected_images)
        self.actionSaveSelectedImages = QAction(self)
        self.actionSaveSelectedImages.setText('Save Selected Images into Zip')
        self.actionSaveSelectedImages.triggered.connect(self.save_selected_images_in_zip)
        self.actionShowInExplorer = QAction(self)
        self.actionShowInExplorer.setText('Show in Explorer')
        self.actionShowInExplorer.setShortcut('Ctrl+E')
        self.actionShowInExplorer.triggered.connect(self.show_in_explorer)
        self.actionRefresh = QAction(self)
        self.actionRefresh.setText('Refresh Image List')
        self.actionRefresh.setShortcut('Ctrl+R')
        self.actionRefresh.triggered.connect(self.refresh)
        layout = QVBoxLayout()
        layout.setContentsMargins(2,2,2,2)
        layout.setMargin(2)
        layout.setSpacing(2)
        hlayout = QHBoxLayout()
        hlayout.addWidget(QLabel('Filter:'))
        hlayout.addWidget(self._filter)
        layout.addLayout(hlayout)
        layout.addWidget(self._list)
        self.setLayout(layout)
        self.refresh()

    def on_custom_menu_requested(self, pos):
        menu = QMenu()
        menu.addAction(self.actionShowInExplorer)
        menu.addAction(self.actionRefresh)
        menu.addAction(self.actionSaveSelectedImages)
        menu.addAction(self.actionDeleteSelectedImages)
        menu.exec_(self._list.mapToGlobal(pos))

    def on_filter_changed(self):
        tags = self._filter.text().split(',')
        for i in range(self._list.count() - 1):
            item = self._list.item(i)
            data = item.data(Qt.UserRole + 1)
            input_tags = data['input']
            hidden = False
            for t in tags:
                t = t.strip()
                if not t:
                    continue
                if t not in input_tags:
                    hidden = True
                    break
            item.setHidden(hidden)

    def on_item_selection_changed(self):
        item = self._list.currentItem()
        if item is None:
            return
        name = item.data(Qt.UserRole + 0)
        self.itemChanged.emit(name)

    def load(self, name: str):
        base = os.path.join(g_nais.output_folder(), name)
        self.add(name)

    def add(self, name: str):
        base = os.path.join(g_nais.output_folder(), name)
        try:
            data = text_to_json(read_text(base + '.json'))
        except json.JSONDecodeError as e:
            print(e)
            return
        item = QListWidgetItem()
        item.setIcon(QIcon(base + '_tm.png'))
        item.setData(Qt.UserRole + 0, name)
        item.setData(Qt.UserRole + 1, data)
        self._list.addItem(item)

    def refresh(self):
        self._list.clear()
        self._items = {}
        for f in os.listdir(g_nais.output_folder()):
            if not f.endswith('.json'):
                continue
            self.load(os.path.splitext(f)[0])

    def delete_selected_images(self):
        for i in self._list.selectedItems():
            name = i.data(Qt.UserRole + 0)
            base = os.path.join(g_nais.output_folder(), name)
            if os.path.exists(base + '.png'):
                send2trash.send2trash(base + '.png')
            if os.path.exists(base + '.json'):
                send2trash.send2trash(base + '.json')
            if os.path.exists(base + '_tm.png'):
                send2trash.send2trash(base + '_tm.png')
            self._list.takeItem(self._list.row(i))

    def save_selected_images_in_zip(self):
        if len(self._list.selectedItems()) == 0:
            return
        fpath, _ = QFileDialog.getSaveFileName(self, 'Save Selected Images into Zip', g_nais.output_folder(), '*.zip')
        if not fpath:
            return

        prog = QProgressDialog()
        prog.setMinimum(0)
        prog.setMaximum(0)
        prog.open()
        prog.update()

        preprocess = read_text(os.path.join(g_nais.output_folder(), 'archive_preprocess.txt'))
        import shutil, tempfile
        temp_dir = os.path.join(g_nais.output_folder(), '.temp')
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        for i in self._list.selectedItems():
            name = i.data(Qt.UserRole + 0)
            src = os.path.join(g_nais.output_folder(), name + '.png')
            dst = os.path.join(temp_dir, name + '.png')
            if preprocess:
                os.system(preprocess.format(src, dst))
            else:
                shutil.copy(src, dst)
            prog.update()
        shutil.make_archive(os.path.splitext(fpath)[0], format='zip', root_dir=temp_dir)
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

        prog.autoClose()

    def show_in_explorer(self):
        item = self._list.currentItem()
        if not item:
            return
        name = item.data(Qt.UserRole + 0)
        path = os.path.join(g_nais.output_folder(), name) + '.png'
        import platform
        plat = platform.system()
        if plat == 'Windows':
            subprocess.Popen(f'explorer /select,"{path}"')
        elif plat == 'Darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])

    def startDrag(self, supportedActions:Qt.DropActions) -> None:
        item = self._list.currentItem()
        pathabs = os.path.abspath(os.path.join(g_nais.output_folder(), item.data(Qt.UserRole + 0) + '.png'))
        path = QUrl.fromLocalFile(pathabs)
        drag = QDrag(self._list)
        mime = QMimeData()
        mime.setUrls([path])
        drag.setMimeData(mime)
        drag.exec_()


class GuiImageViewer(NaisImage):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Viewer')
        self.setMinimumSize(QSize(256, 256))
        self.smoothTransformation = True
        self._base_path = ''
        self._image = None
        self._rate = 0.125

    def setImage(self, name):
        try:
            self._base_path = os.path.join(g_nais.output_folder(), name)
            self._image = Image.open(self._base_path + '.png')
            tm = self._image.copy()
            tm.thumbnail((64, 64), Image.ANTIALIAS)
            tm.save(f'{self._base_path}_tm.png', "PNG")
            super().setImage(ImageQt(self._image))
        except FileNotFoundError as e:
            print(e)


class GuiImageData(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Data')
        self._params = NaisCodeEditor()
        self._params.setReadOnly(True)
        layout = QVBoxLayout()
        layout.addWidget(self._params)
        layout2 = QHBoxLayout()
        layout.addLayout(layout2)
        self.setLayout(layout)

    def setImage(self, name):
        try:
            base = os.path.join(g_nais.output_folder(), name)
            self._params.setPlainText(read_text(base + '.json'))
        except FileNotFoundError as e:
            print(e)


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
        self._image_var = GuiImageVariations()
        self._image_var.generated.connect(self._image_list.add)
        self._progress = QProgressBar()
        self._progress.setAlignment(Qt.AlignCenter)
        self._progress.setTextVisible(False)
        self._prompt.generated.connect(self._image_list.add)
        self._image_list.itemChanged.connect(self._image_viewer.setImage)
        self._image_list.itemChanged.connect(self._image_data.setImage)
        self._image_list.itemChanged.connect(self._image_var.setImage)
        self._job.jobStatusChanged.connect(self.on_job_status_changed)
        self.statusBar().addWidget(self._progress, True)
        self.setDockOptions(QMainWindow.AllowNestedDocks | QMainWindow.AllowTabbedDocks)
        self.dock(self._prompt, Qt.LeftDockWidgetArea)
        self.dock(self._image_viewer, Qt.RightDockWidgetArea)
        self.dock(self._image_var, Qt.RightDockWidgetArea)
        self.dock(self._image_data, Qt.RightDockWidgetArea)
        self.dock(self._image_list, Qt.RightDockWidgetArea)

        menu_file = self.menuBar().addMenu('File')
        action = QAction(self)
        action.setText('Load Default Input')
        action.setShortcut('Ctrl+N')
        action.triggered.connect(self._prompt.loadDfaultInput)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Save Default Input')
        action.triggered.connect(self._prompt.saveDefaultInput)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Load Default Script')
        action.setShortcut('Ctrl+Shift+N')
        action.triggered.connect(self._prompt.newTweakScript)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Save Default Script')
        action.triggered.connect(self._prompt.saveDefaultScript)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Save Script')
        action.setShortcut('Ctrl+Shift+S')
        action.triggered.connect(self._prompt.saveTweakScript)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Open Script')
        action.setShortcut('Ctrl+Shift+O')
        action.triggered.connect(self._prompt.openTweakScript)
        menu_file.addAction(action)
        action = QAction(self)
        action.setText('Exit')
        action.triggered.connect(self.close)
        menu_file.addAction(action)
        menu_edit = self.menuBar().addMenu('Edit')
        menu_edit.addAction(self._image_list.actionRefresh)
        menu_edit.addAction(self._image_list.actionSaveSelectedImages)
        menu_edit.addAction(self._image_list.actionDeleteSelectedImages)
        action = QAction(self)
        action.setText('Edit Archive Preprocess')
        action.triggered.connect(self.edit_archive_preprocess)
        menu_edit.addAction(action)
        menu_window = self.menuBar().addMenu('Window')
        menu_window.addAction(self._prompt.parent().toggleViewAction())
        menu_window.addAction(self._image_list.parent().toggleViewAction())
        menu_window.addAction(self._image_data.parent().toggleViewAction())
        menu_window.addAction(self._image_viewer.parent().toggleViewAction())
        menu_window.addAction(self._image_var.parent().toggleViewAction())
        self._job.start()
        self.load_layout()

    def edit_archive_preprocess(self) -> None:
        path = os.path.join(g_nais.output_folder(), 'archive_preprocess.txt')
        txt = read_text(path)
        if not txt:
            txt = 'realesrgan-ncnn-vulkan.exe -i {} -o {}'
        txt, ok = QInputDialog.getText(self, 'Edit Archive Preprocess', 'Command:', QLineEdit.Normal, txt)
        if ok:
            with open(path, 'wt') as f:
                f.write(txt)

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

    # CLEANUP OLD FILES
    for f in os.listdir(g_nais.output_folder()):
        if f.endswith('_wc_pos.png') or f.endswith('_wc_neg.png'):
            path = os.path.join(g_nais.output_folder(), f)
            send2trash.send2trash(path)

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
