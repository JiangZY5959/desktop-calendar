# -*- coding: utf-8 -*-
"""v1.4.5.0 改动截图：启动默认锁定 + 设置页「星期标题栏背景颜色」标签。"""
import os
import sys
import tempfile

TD = tempfile.mkdtemp(prefix='shotv24-')
os.environ['XDG_DATA_HOME'] = os.path.join(TD, 'data')
os.environ['XDG_CONFIG_HOME'] = os.path.join(TD, 'cfg')
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
for _d in (os.environ['XDG_DATA_HOME'], os.environ['XDG_CONFIG_HOME']):
    os.makedirs(os.path.join(_d, 'desktop-calendar'))

from PyQt5.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)

from brl import store as S
from brl import mainwin as MW
from brl.settings import SettingsDialog

st = S.STORE
w = MW.MainWindow(st, None)
w.show()
app.processEvents()

print('启动默认锁定:', w._locked)
print('锁按钮图标(1=上锁):', 'lock' if w._locked else 'unlock')
w.grab().save('v24_main_locked.png')

dlg = SettingsDialog(st, None)
dlg.show()
app.processEvents()
dlg.grab().save('v24_settings_label.png')
print('saved')
