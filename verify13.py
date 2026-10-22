# -*- coding: utf-8 -*-
"""第十三轮验证（v1.2.7.3）

① 选项设置透明度滑杆进度条可见（自绘 AlphaSlider）
② 今日按钮图标为"今"字
③ 齿轮旁新增叉号按钮，点击直接隐藏日历
"""
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v13')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QImage
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl import store, mainwin as MW, settings

npass = nfail = 0


def ck(name, ok, extra=''):
    global npass, nfail
    if ok:
        npass += 1
        print('  PASS %s %s' % (name, extra))
    else:
        nfail += 1
        print('  FAIL %s %s' % (name, extra))


def bright_pixels(img, x0, y0, x1, y1, want_blue=False):
    n = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            c = img.pixel(x, y)
            r, g, b = (c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff
            if want_blue:
                if b > 150 and b - r > 40 and b - g > 40:
                    n += 1
            elif r > 180 and g > 180 and b > 180:
                n += 1
    return n


S = store.Store()

print('== ① 透明度滑杆进度可见')
src = open(os.path.join(HERE, 'brl', 'settings.py')).read()
ck('有自绘 AlphaSlider 类', 'class AlphaSlider(QSlider)' in src)
ck('编辑窗使用自绘滑杆', "self._sl = AlphaSlider()" in src)
ck('自绘包含进度填充', 'drawRoundedRect' in src and '#2F7BFF' in src)

dlg = settings.SettingsDialog(S, None)
dlg._switch(0)
dlg.show()
app.processEvents()
pms = dlg.findChildren(settings.AlphaSlider)
ck('基础设置页存在多个自绘滑杆', len(pms) >= 4, '%d 个' % len(pms))
if pms:
    sl = pms[0]
    sl.setValue(200)
    app.processEvents()
    img = sl.grab().toImage()
    blue = bright_pixels(img, 0, 0, img.width(), img.height(), want_blue=True)
    ck('滑杆已调进度有蓝色填充', blue > 30, '%d 蓝像素' % blue)
    # 拖拽模拟：点击左端再点击右端，值应大幅变化
    from PyQt5.QtCore import QEvent, QPointF, Qt as Qtt
    from PyQt5.QtGui import QMouseEvent
    w = sl.width()
    sl.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(w - 2, 11),
                                   Qtt.LeftButton, Qtt.LeftButton, Qtt.NoModifier))
    ck('点击滑杆右端值接近最大', sl.value() >= sl.maximum() - 25,
       'value=%d' % sl.value())
    sl.mousePressEvent(QMouseEvent(QEvent.MouseButtonPress, QPointF(2, 11),
                                   Qtt.LeftButton, Qtt.LeftButton, Qtt.NoModifier))
    ck('点击滑杆左端值接近最小', sl.value() <= 25, 'value=%d' % sl.value())
    dlg.grab().save(os.path.join(HERE, 'v18_settings.png'))

print('== ② 今日按钮"今"字图标')
ck('nav_today 特判绘制"今"', "u'今'" in open(os.path.join(HERE, 'brl',
   'mainwin.py')).read() and 'nav_today' in MW.MainWindow._icon_pix.__doc__)
w = MW.MainWindow(S, type('C', (), {'quit': lambda s: None,
                                    'apply_autostart': lambda s: None})())
w.show()
app.processEvents()
pm = w._icon_pix('nav_today')
ck('今字图标非空', not pm.isNull() and pm.width() == 24)
img = pm.toImage()
ink = 0
for y in range(24):
    for x in range(24):
        c = img.pixel(x, y)
        if ((c >> 16) & 0xff) > 180 and ((c >> 8) & 0xff) > 180:
            ink += 1
ck('今字有笔画像素（深色主题应为白字）', 20 < ink < 250, '%d 像素' % ink)
w.grab().save(os.path.join(HERE, 'v18_main.png'))

print('== ③ 叉号隐藏按钮')
ck('有 close 图标文件', os.path.exists(os.path.join(HERE, 'brl', 'resources',
                                                 'icons', 'tool_close.png')))
ck('齿轮旁有隐藏按钮', hasattr(w, '_btn_close'))
gmenu = w._btn_menu.geometry()
gclose = w._btn_close.geometry()
ck('叉号在齿轮右侧', gclose.x() > gmenu.x(), '%d > %d' % (gclose.x(), gmenu.x()))
ck('叉号按钮无菜单行为（直接 hide）',
   'self._btn_close.clicked.connect(self.hide)' in
   open(os.path.join(HERE, 'brl', 'mainwin.py')).read())
w._btn_close.click()
app.processEvents()
ck('点击叉号后主窗口隐藏', not w.isVisible())
w.show()
app.processEvents()
ck('重新 show 后恢复', w.isVisible())

w.deleteLater()
dlg.deleteLater()

print('\n结果: PASS=%d FAIL=%d' % (npass, nfail))
sys.exit(1 if nfail else 0)
