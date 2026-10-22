# -*- coding: utf-8 -*-
"""截图：真机颜色选择对话框（检查中文）+ 真实自启动目录写入/移除。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.dirname(os.path.abspath(__file__))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QColor
from PyQt5.QtCore import QTimer

import brl.appctx as AC
import brl.theme as T
from brl import store as S

app = QApplication(sys.argv)
AC.install_zh_translator(app)
st = S.Store()

# 1) 真实自启动目录（不改动用户设置值，只验证可写/可删）
p = AC.autostart_path()
print('autostart path:', p)
print('write=True ->', AC.apply_autostart(st, True), 'exists:', os.path.exists(p))
print('write=False ->', AC.apply_autostart(st, False), 'exists:', os.path.exists(p))

# 2) 颜色对话框截图
dlg = T.zh_color_dialog(QColor('#2F7BFF'), None)
dlg.show()
app.processEvents()


def shoot():
    dlg.grab().save(os.path.join(OUT, 'v12_colordlg.png'))
    print('saved colordlg')
    app.quit()


QTimer.singleShot(800, shoot)
app.exec_()
