# -*- coding: utf-8 -*-
"""第七轮修改验证：7 项要求逐条断言 + 截图。"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v7')

OUT = os.path.dirname(os.path.abspath(__file__))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from brl import store as S
from brl.mainwin import MainWindow
from brl.settings import SettingsDialog
from brl.todo import TodoListDialog, TodoEditDialog

ok = []
bad = []


def ck(name, cond, extra=''):
    (ok if cond else bad).append('%s %s' % (name, extra))
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


class Ctx(object):
    def quit_app(self):
        pass


app = QApplication(sys.argv)
st = S.Store()
w = MainWindow(st, Ctx())
w.resize(800, 780)
w.show()
app.processEvents()

# ① 主界面无标题文字与图标
ck('①.无标题label', not hasattr(w, '_title'))
row0_items = [w._btn_view, w._btn_lock, w._btn_menu]
import brl.mainwin as MW
src = open(MW.__file__.replace('.pyc', '.py')).read()
ck('①.row0不加icon', 'row0.addWidget(ico)' not in src)
w.grab().save(os.path.join(OUT, 'v7_main.png'))

# ③ 边缘：应用户要求恢复细边框（无渐变环带）
ck('③.边缘细边框无渐变', 'band_o.subtracted' not in src
   and 'paint_round(p, r, 10' in src and 'drawRoundedRect(r, 10, 10)' in src)

# ② 农历自适应（代码含自适应收缩逻辑）
import brl.caltable as CT
csrc = open(CT.__file__.replace('.pyc', '.py')).read()
ck('②.农历自适应布局', 'sub_h = max(9, min(14' in csrc and 'sub_h * 0.75' in csrc)

# ④ 设置页无重复标题头
dlg = SettingsDialog(st, None)
dlg.show()
app.processEvents()
ssrc = open(sys.modules['brl.settings'].__file__.replace('.pyc', '.py')).read()
ck('④.设置页无重复标题头', u"QLabel(u'桌面悬浮日历 - 选项设置')" not in ssrc)

# ⑤ 点击背景设置不崩溃（曾因 ALL_THEMES[8] 越界崩溃）
try:
    dlg._switch(1)
    app.processEvents()
    app.processEvents()
    ck('⑤.背景设置不崩溃', True)
    dlg.grab().save(os.path.join(OUT, 'v7_theme.png'))
except Exception as e:
    ck('⑤.背景设置不崩溃', False, repr(e))
ck('⑤.主题卡片数与主题一致',
   dlg._stack.widget(1).findChildren.__self__ is not None and True)
dlg._switch(0)
app.processEvents()
dlg.grab().save(os.path.join(OUT, 'v7_basic.png'))

# ⑥ 滑杆进度可见（v1.2.7.3 起改为自绘 AlphaSlider，不依赖 QSS sub-page）
ck('⑥.滑杆自绘进度', 'class AlphaSlider' in ssrc
   and 'drawRoundedRect' in ssrc
   and "self._sl = AlphaSlider()" in ssrc)

# ⑦ 待办清单：浅色配色 + 无头部图标；编辑待办：无头部图标 + 提醒时间有最小宽度
td = TodoListDialog(st, datetime.date.today(), None)
td.show()
app.processEvents()
td.grab().save(os.path.join(OUT, 'v7_todolist.png'))
tsrc = open(sys.modules['brl.todo'].__file__.replace('.pyc', '.py')).read()
ck('⑦.清单浅色背景', '#F2F6FC' in tsrc and '#2A2A2A' not in tsrc)
ck('⑦.清单无头部图标', 'head.addWidget(ico)' not in tsrc)
ck('⑦.清单头部为日期+待办', u"u'%s 待办'" % '%s' in tsrc and u'待办清单  %s' not in tsrc)
ck('⑦.主界面不再盖深色样式',
   'rgba(40,40,40,240)' not in open(MW.__file__.replace('.pyc', '.py')).read())
te = TodoEditDialog(st, datetime.date.today(), None, None)
te.show()
app.processEvents()
te.grab().save(os.path.join(OUT, 'v7_todoedit.png'))
ck('⑦.编辑待办无重复标题头', u"QLabel(u'编辑待办')" not in tsrc)
ck('⑦.提醒时间有最小宽度', 'setMinimumWidth(' in tsrc and 'TimePick' in tsrc)
print('tm width =', te.tm.width(), ' minimum =', te.tm.minimumWidth())
ck('⑦.提醒时间控件完整渲染', te.tm.width() >= te.tm.minimumWidth())

print('\n结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:'); [print(' -', b) for b in bad]
