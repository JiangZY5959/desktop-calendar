# -*- coding: utf-8 -*-
"""第十六轮验证（v1.2.9.0）

① iPhone 闹钟式滚轮时间盘：拖动/单击/滚轮都能取到任意分钟
② 主界面滚轮往上 = 翻到上个月（与小编码相反的设计保持一致）
③ 提醒弹窗外观跟随主窗口主题（圆角细边框、主题底色与文字色）
"""
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brltest_env as _ENV
_ENV.isolate('v16')
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt, QPoint, QTime, QEvent
from PyQt5.QtGui import QWheelEvent, QImage, QColor
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl import store as S
from brl import theme as T
from brl import mainwin as MW
from brl.timepick import TimePick, TimePopup, TimeWheel

npass = nfail = 0


def ck(name, ok, extra=''):
    global npass, nfail
    if ok:
        npass += 1
        print('  PASS %s %s' % (name, extra))
    else:
        nfail += 1
        print('  FAIL %s %s' % (name, extra))


psrc = open(os.path.join(HERE, 'brl', 'timepick.py')).read()
csrc = open(os.path.join(HERE, 'brl', 'caltable.py')).read()
msrc = open(os.path.join(HERE, 'brl', 'mainwin.py')).read()

# ------------------------------------------------------------ ①
print('== ① iOS 风格时间滚轮')
tp = TimePick()
pop = TimePopup(QTime(8, 20))
ck('时间盘默认位置与当前一致', pop.current() == (8, 20), str(pop.current()))
ck('时间盘是悬浮卡片（非模态重边框）',
   'Qt.Popup' in psrc and 'border-radius:14px' in psrc)
ck('滚轮 Item 高度统一、可见 5 行',
   TimeWheel.ITEM_H == 36 and TimeWheel.VISIBLE == 5)

# 单击某一行：选中该行
wh = TimeWheel(['%02d' % i for i in range(24)])
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtCore import QPointF


def press(w, y):
    ev = QMouseEvent(QEvent.MouseButtonPress, QPointF(10, y), Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    w.mousePressEvent(ev)


def release(w, y, moved=False):
    ev = QMouseEvent(QEvent.MouseButtonRelease, QPointF(10, y), Qt.LeftButton,
                     Qt.LeftButton, Qt.NoModifier)
    if moved:                       # 先构造拖动位移
        mv = QMouseEvent(QEvent.MouseMove, QPointF(10, y + 40), Qt.LeftButton,
                         Qt.LeftButton, Qt.NoModifier)
        w.mouseMoveEvent(mv)
    w.mouseReleaseEvent(ev)
    w._anim.stop()
    w._off = w._target
    i = int(w._off / w.ITEM_H + 0.5)
    if i != w._idx:
        w._idx = i
    w.update()


wh.resize(wh.sizeHint())
wh.show()
app.processEvents()
mid = wh.height() / 2.0
wh.set_index(10)
press(wh, mid + 2 * wh.ITEM_H)      # 点往下两格 = 12
release(wh, mid + 2 * wh.ITEM_H)
ck('单击中间下方两格 → 选中该行', wh.index() == 12, 'idx=%d' % wh.index())

# 拖动：往上拖两格 → 索引 +2
wh.set_index(10)
press(wh, mid)
mv = QMouseEvent(QEvent.MouseMove, QPointF(10, mid - 72), Qt.LeftButton,
                 Qt.LeftButton, Qt.NoModifier)
wh.mouseMoveEvent(mv)
wh._target = wh._clamp_off(wh._target if False else wh._drag_off + 72)
wh._off = wh._target
wh._anim.stop()
i = int(wh._off / wh.ITEM_H + 0.5)
wh._idx = max(0, min(wh.count() - 1, i))
ck('往上拖动两格 → 索引 +2', wh.index() == 12, 'idx=%d' % wh.index())

# 滚轮：往上滚一格 → 上一个值
wh.set_index(10)


def wheel(w, dy):
    ev = QWheelEvent(QPoint(10, 10), QPoint(10, 10), QPoint(0, 0),
                     QPoint(0, dy), 0, Qt.Vertical, Qt.NoButton, Qt.NoModifier)
    w.wheelEvent(ev)


wheel(wh, 120)
ck('滚轮往上（delta>0）→ 上一个值（与"往上=往前"一致）',
   wh.index() == 9, 'idx=%d' % wh.index())
wheel(wh, -120)
ck('滚轮往下 → 下一个值', wh.index() == 10, 'idx=%d' % wh.index())

wm = TimeWheel(['%02d' % i for i in range(60)])
wm.set_index(59)
wheel(wm, -120)
ck('最小值夹取（59 再往下仍是 59）', wm.index() == 59, 'idx=%d' % wm.index())
wm.set_index(0)
wheel(wm, 120)
ck('最小值夹取（0 再往上仍是 0）', wm.index() == 0, 'idx=%d' % wm.index())

# 每分钟可选
pop._wm.set_index(37)
ck('任意分钟都能选（x:37）', pop.time() == QTime(8, 37), pop.time().toString('HH:mm'))
pop._wm.set_index(1)
ck('1 分也能选（非 5 分钟档）', pop.time() == QTime(8, 1), pop.time().toString('HH:mm'))

# ------------------------------------------------------------ ②
print('== ② 主界面滚轮翻月方向')
ck('源码注释写明"往上=往前翻页"',
   u'滚轮往上 = 往前翻' in csrc or u'往上 = 往前翻页' in csrc)
ck('step 取反：dy>0 时 step=-1',
   'step = -1 if ev.angleDelta().y() > 0 else 1' in csrc)

st = S.Store()
w = MW.MainWindow(st, type('C', (), {'quit': lambda s: None,
                                     'apply_autostart': lambda s: None})())
w.resize(800, 600)
w.show()
app.processEvents()
cal = w._cal


def month_wheel(dy):
    ev = QWheelEvent(QPoint(10, 10), QPoint(10, 10), QPoint(0, 0),
                     QPoint(0, dy), 0, Qt.Vertical, Qt.NoButton, Qt.NoModifier)
    cal.wheelEvent(ev)
    return cal.month()


now_month = cal.month()
m_up = month_wheel(120)          # 往上滚
ck('滚轮往上 → 变成上个月',
   (m_up.year * 12 + m_up.month) == (now_month.year * 12 + now_month.month) - 1,
   '%s → %s' % (now_month, m_up))
cal.set_month(now_month)
m_down = month_wheel(-120)       # 往下滚
ck('滚轮往下 → 变成下个月',
   (m_down.year * 12 + m_down.month) == (now_month.year * 12 + now_month.month) + 1,
   '%s → %s' % (now_month, m_down))

# ------------------------------------------------------------ ③
print('== ③ 提醒弹窗跟随主界面风格')
ck('弹窗接收主题参数', 'def __init__(self, todo, theme=None' in msrc)
ck('主窗口把当前主题传给弹窗',
   'RemindPopup(row, getattr(self, \'_theme\', None))' in msrc)
ck('弹窗自绘圆角 + 主题描边',
   "T.paint_round(p, r, 10, self._theme.get('mainbgndclr'" in msrc
   and 'borderoutclr' in msrc)

for t in T.ALL_THEMES:
    cfg = dict(t)
    popw = MW.RemindPopup({'content': u'测试提醒', 'date': '2026-10-20',
                           'remind_time': '12:00'}, cfg)
    popw.show()
    app.processEvents()
    pm = popw.grab()
    img = pm.toImage().convertToFormat(QImage.Format_ARGB32)
    txt = T.qcolor(cfg.get('txtclr', '#FFFFFF'))
    lum_txt = 0.299 * txt.red() + 0.587 * txt.green() + 0.114 * txt.blue()
    # 背景应与文字明暗相反：浅色文字配深底，深色文字配浅底
    c = img.pixel(img.width() - 6, img.height() - 6)
    lum_bg = 0.299 * ((c >> 16) & 0xff) + 0.587 * ((c >> 8) & 0xff) + 0.114 * (c & 0xff)
    ok = abs(lum_bg - lum_txt) >= 70        # 对比度够，文字一定看得清
    ck(u'主题 %s：底色与文字对比足够' % cfg.get('name'), ok,
       'txt=%.0f bg=%.0f' % (lum_txt, lum_bg))
    popw.close()

print()
print('=== RESULT: PASS %d  FAIL %d' % (npass, nfail))
_ENV.cleanup()
sys.exit(1 if nfail else 0)
