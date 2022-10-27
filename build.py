import os
import shutil


if __name__ == '__main__':
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
    os.system('python -m PyInstaller naisgui.spec')
    os.makedirs('dist/bin/naisgui', exist_ok=True)
    shutil.copy('dist/naisgui.exe', 'dist/bin/naisgui/naisgui.exe')
    shutil.make_archive('dist/naisgui-v1.0', 'zip', 'dist/bin')