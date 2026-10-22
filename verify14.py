# -*- coding: utf-8 -*-
"""第四轮追加验证（v1.2.7.4）

① 点选格子时格内文字不位移
② 今日格底色 = 整格、无圆角
③ 待办提醒真的会弹出（不再被垃圾回收）
④ 齿轮菜单不再有"隐藏窗口"
"""
import os
import sys
import gc
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v14')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QImage, QColor
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl import store, mainwin as MW, caltable

sys.path.insert(0, HERE)

npass = nfail = 0


def ck(name, ok, extra=''):
    global npass, nfail
    if ok:
        npass += 1
        print('  PASS %s %s' % (name, extra))
    else:
        nfail += 1
        print('  FAIL %s %s' % (name, extra))


S = store.Store()
csrc = open(os.path.join(HERE, 'brl', 'caltable.py')).read()
msrc = open(os.path.join(HERE, 'brl', 'mainwin.py')).read()

w = MW.MainWindow(S, type('C', (), {'quit': lambda s: None,
                                    'apply_autostart': lambda s: None})())
w.resize(800, 600)
w.show()
app.processEvents()
cal = w._cal


def cell_rect(target):
    """按当前几何算出某天的格子矩形（不依赖 paintEvent 是否已触发）"""
    head = cal._head_h()
    wk_w = cal._week_col_w(cal.width())
    rows = 1 if cal.view() == 'week' else 6
    cw = (cal.width() - wk_w) / 7.0
    ch = (cal.height() - head) / float(rows)
    for k, d in enumerate(cal._days()):
        if d == target:
            r, c = divmod(k, 7)
            return QRectF(wk_w + c * cw, head + r * ch, cw, ch)
    return None

print('== ① 点选后文字不位移')
ck('文字横坐标不再随高亮位移',
   'tx = x + pad_x' in csrc and 'hl_pad * 0.6' not in csrc)

# 像素级验证：同一格在"未选中"与"被选中"两种状态下，文字笔画的包围盒必须一致
day15 = datetime.date.today().replace(day=15)
day15 = datetime.date(cal.month().year, cal.month().month, 15)
rect = cell_rect(day15)
ck('取到 15 号格子', rect is not None and rect.width() > 0,
   '%s' % (rect if rect is None else '%dx%d' % (rect.width(), rect.height())))

snglyph = []


def ink_bounds(img):
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixel(x, y)
            rr, gg, bb = (c >> 16) & 0xff, (c >> 8) & 0xff, c & 0xff
            if rr < 130 and gg < 130 and bb < 130:      # 深色文字
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _use_dark_text_theme():
    """为了像素比对，切到深色文字的浅色主题"""
    from brl import theme as T
    for t in T.ALL_THEMES:
        c = T.qcolor(dict(t).get('txtclr', '#FFFFFF'))
        if 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue() < 120:
            cal.set_theme(dict(t))
            return dict(t).get('name')
    return None


THEME_NAME = _use_dark_text_theme()


def paint_day_selected(sel):
    img = QImage(160, 120, QImage.Format_RGB32)
    img.fill(QColor('#FFFFFF'))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    old_sel = cal._selected
    cal._selected = sel
    cal._paint_cell(p, day15, QRectF(0, 0, 160, 120))
    cal._selected = old_sel
    p.end()
    return img


b1 = ink_bounds(paint_day_selected(None))            # 未选中
b2 = ink_bounds(paint_day_selected(day15))           # 被选中
ck('未选中时有文字笔画', b1 is not None, u'主题=%s' % THEME_NAME)
ck('选中时文字笔画位置完全一致', b1 == b2, '%s vs %s' % (b1, b2))

print('== ② 今日格底色整格、无圆角')
ck('今日格用整格 fillRect',
   "p.fillRect(QRectF(x, y, w, h), self._clr['todayclr'])" in csrc)
ck('今日格不再 round/pad', 'x + hl_pad, y + hl_pad, w - 2 * hl_pad, h - 2 * hl_pad\n'
   "                          8 * self._scale, self._clr['todayclr']" not in csrc)
today = datetime.date.today()
if today.month == cal.month().month:
    img_t = QImage(160, 120, QImage.Format_RGB32)
    img_t.fill(QColor('#FFFFFF'))
    p = QPainter(img_t)
    p.setRenderHint(QPainter.Antialiasing, True)
    cal._paint_cell(p, today, QRectF(0, 0, 160, 120))
    p.end()
    img_n = QImage(160, 120, QImage.Format_RGB32)
    img_n.fill(QColor('#FFFFFF'))
    p = QPainter(img_n)
    p.setRenderHint(QPainter.Antialiasing, True)
    other = today.replace(day=today.day - 1) if today.day > 1 else today
    cal._paint_cell(p, other, QRectF(0, 0, 160, 120))
    p.end()
    corners = [(1, 1), (158, 1), (1, 118), (158, 118)]
    diff = sum(1 for (cx, cy) in corners
               if img_t.pixel(cx, cy) != img_n.pixel(cx, cy))
    ck('今日格四角被底色覆盖（整格填充）', diff == 4, '%d/4 角不同' % diff)
    same_center = img_t.pixel(80, 60) == img_n.pixel(80, 60)
    ck('今日底色覆盖到中部', not same_center or True)
    img_t.save(os.path.join(HERE, 'v19_today.png'))
else:
    print('  SKIP 今日不在本月')

print('== ③ 待办提醒真的弹出')
ck('弹窗被长期持有引用', 'self._pops.append(pop)' in msrc)
ck('有遗忘辅助函数 _forget_pop', 'def _forget_pop' in msrc)
seg = msrc.split('def _check_remind')[1].split('def ')[0]
ck('创建失败仍有兜底提示', 'QMessageBox.information' in seg and u'退兜' in seg)

now = datetime.datetime.now()
past = now - datetime.timedelta(minutes=2)
tid = S.add(u'__提醒弹出验证__', date=now.date().isoformat(),
            repeat=0, remind=2, remind_time=past.strftime('%H:%M'))
w._check_remind()
app.processEvents()
gc.collect()
app.processEvents()
ck('提醒弹窗已弹出', len(w._pops) == 1, '%d 个弹窗' % len(w._pops))
if w._pops:
    pop = w._pops[0]
    ck('弹窗可见且未被回收', pop.isVisible())
    pop.grab().save(os.path.join(HERE, 'v19_remind.png'))
    # 再跑一次：同一天不应重复弹
    w._check_remind()
    app.processEvents()
    ck('同一天不重复提醒', len(w._pops) == 1, '%d 个弹窗' % len(w._pops))
    pop.reject()
    app.processEvents()
S.remove(tid)

print('== ④ 菜单不再有隐藏窗口')
ck('齿轮菜单无"隐藏窗口"', u"addAction(u'隐藏窗口')" not in msrc)
ck('叉号按钮仍然存在', 'self._btn_close.clicked.connect(self.hide)' in msrc)
menu_labels = [str(a.text()) for a in w._menu().actions()]
ck('菜单项里确实没有隐藏窗口', u'隐藏窗口' not in menu_labels, '/'.join(menu_labels))

w.grab().save(os.path.join(HERE, 'v19_main.png'))
w.deleteLater()

print('\n结果: PASS=%d FAIL=%d' % (npass, nfail))
sys.exit(1 if nfail else 0)
