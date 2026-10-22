# -*- coding: utf-8 -*-
"""第 18 轮专项验证：①PS 风格选色盘 ②weekclr 改名 ③锁定贴底。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import brltest_env as _ENV
_ENV.isolate('verify18')

_n = [0]
_fails = [0]


def ck(name, ok, detail=''):
    _n[0] += 1
    if not ok:
        _fails[0] += 1
    print('  %s %s%s' % ('PASS' if ok else 'FAIL', name,
                         ('' if ok else '  <- %s' % (detail,))))


print('== ② weekclr 改名 ==')
from brl.settings import COLOR_DEFS
lab = dict((k, l) for k, l, _a in COLOR_DEFS)['weekclr']
ck('weekclr 显示名', lab == u'星期标题栏字体颜色', lab)
ck('weekclr 无旧文案', u'周末字体颜色' not in
   open('brl/settings.py').read())

print('== ① PS 风格选色盘 ==')
from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtGui import QColor
from PyQt5.QtCore import Qt
app = QApplication(sys.argv)
from brl.colorpick import ColorDialog
import brl.theme as T

d = ColorDialog(QColor('#80102040'), None)
ck('①.对话框可创建', d is not None)
d.show()
app.processEvents()
ck('①.初始十六进制无前导零丢失', d._fields['hex'].text() == '102040',
   d._fields['hex'].text())
# SV 区点击 -> 纯黑
d._sv._apply(d._sv.rect().bottomRight() - d._sv.rect().topLeft())
ck('①.SV区右下角=黑', d._c.name() == '#000000', d._c.name())
# 色相/饱和/明度设置
d.set_ssv(200, 255, 255)
ck('①.色相-饱和-明度生效', d._c.name() == '#00aaff', d._c.name())
ck('①.SV底图跟随色相', d._sv._img_h == 200, d._sv._img_h)
# 色板点击
d.on_swatch(QColor('#ff8000'))
ck('①.基础色板生效', d._c.name() == '#ff8000', d._c.name())
# 字段输入 RGB
d._fields['r'].blockSignals(True)
d._fields['r'].setText('16')
d._fields['r'].blockSignals(False)
d._on_field('r')
ck('①.红字段输入生效', d._c.red() == 16, d._c.red())
# 字段输入十六进制（含前导零校验）
d._fields['hex'].blockSignals(True)
d._fields['hex'].setText('1AEAE8')
d._fields['hex'].blockSignals(False)
d._on_field('hex')
ck('①.十六进制输入生效', d._c.name() == '#1aeae8', d._c.name())
ck('①.十六进制回填补零', d._fields['hex'].text() == '1AEAE8',
   d._fields['hex'].text())
# 非法输入回退
d._fields['hex'].blockSignals(True)
d._fields['hex'].setText('zzz')
d._fields['hex'].blockSignals(False)
d._on_field('hex')
ck('①.非法输入回退原值', d._fields['hex'].text() == '1AEAE8',
   d._fields['hex'].text())
# alpha 保留
d.setCurrentColor(QColor('#80102040'))
cc = d.currentColor()
ck('①.currentColor保留alpha', cc.alpha() == 0x80 and cc.name() == '#102040',
   '%s a=%d' % (cc.name(), cc.alpha()))
# 添加自定义色
d._add_custom()
ck('①.添加自定义色', len(d._custom) >= 1 and d._custom[0] == '#102040',
   d._custom)
d._add_custom()
ck('①.重复添加去重', len(d._custom) == 1, d._custom)
# theme 工厂返回新对话框
dlg2 = T.zh_color_dialog(QColor('#ff0000'), None, u'测试')
ck('①.zh_color_dialog已替换', isinstance(dlg2, ColorDialog), type(dlg2))
ck('①.兼容setCurrentColor', dlg2.currentColor().name() == '#ff0000')

print('== ③ 锁定贴底 ==')
import brl.appctx as A
from brl import x11fix as X11
ctx = A.Context(app)
w = A.MainWindow(ctx.store, ctx)
w.show()
app.processEvents()
wid = w._win_id()
w._locked = True
w._apply_lock_flags()
app.processEvents()
ck('③.锁定=贴底(BELOW)', 'BELOW' in X11.state_names(wid),
   X11.state_names(wid))
ck('③.锁定后窗口可见', w.isVisible())
ck('③.锁定保留无边框', bool(w.windowFlags() & Qt.FramelessWindowHint))
w._locked = False
w._apply_lock_flags()
app.processEvents()
ck('③.解锁无BELOW', 'BELOW' not in X11.state_names(wid),
   X11.state_names(wid))
ck('③.解锁后窗口可见', w.isVisible())
# _on_lock 走完整链路
w._on_lock()
app.processEvents()
ck('③.按钮切换->贴底', 'BELOW' in X11.state_names(wid),
   X11.state_names(wid))
w._on_lock()
app.processEvents()
ck('③.再切->恢复', 'BELOW' not in X11.state_names(wid),
   X11.state_names(wid))
# 任务栏隐藏声明
X11.skip_taskbar(wid)
ck('③.任务栏隐藏(SKIP_TASKBAR)',
   'SKIP_TASKBAR' in X11.state_names(wid), X11.state_names(wid))

print('== 自定义色板持久化 ==')
from PyQt5.QtCore import QSettings
st = QSettings()
val = st.value('colorpick/custom')
ck('①.自定义色已存盘', isinstance(val, list) and val == ['#102040'], val)

print('结果: %d 项, 失败 %d 项' % (_n[0], _fails[0]))
print('FAILED: %s' % ('none' if not _fails[0] else '%d 项' % _fails[0]))
