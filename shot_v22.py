# -*- coding: utf-8 -*-
"""本轮改动的离屏截图：关于窗口（图标主页）/ 最新版本提示 / 提醒下拉。"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl.mainwin import AboutDialog, RemindPopup
from brl.updatedlg import MsgDialog
from brl.todo import TodoEditDialog
from brl import store

dlg = AboutDialog()
dlg.show()
app.processEvents()
dlg.grab().save(os.path.join(HERE, 'v22_about.png'))

msg = MsgDialog(None, u'检查更新', u'当前已是最新版本 v1.4.3.0。')
msg.show()
app.processEvents()
msg.grab().save(os.path.join(HERE, 'v22_uptodate.png'))
msg.close()

s = store.Store()
ed = TodoEditDialog(s, __import__('datetime').date.today())
ed.cb_remind.setCurrentIndex(ed.cb_remind.findData(5))
ed.show()
app.processEvents()
ed.grab().save(os.path.join(HERE, 'v22_todoedit.png'))

pop = RemindPopup({'id': 1, 'content': u'周报要交了', 'date': '2026-11-01',
                   'remind_time': '09:00', 'lead': 7}, None)
pop.show()
app.processEvents()
pop.grab().save(os.path.join(HERE, 'v22_remind.png'))

print('saved v22_about / v22_uptodate / v22_todoedit / v22_remind')
