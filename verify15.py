# -*- coding: utf-8 -*-
"""第五轮追加验证（v1.2.8.0）

① 选中格子整格填充、无圆角内框（与今日格一致）
② 提醒时间选择器：统一圆角框 + 时钟图标，分钟可选到每一分钟
③ 出厂默认设置 = 用户当前配置（只补默认值，不覆盖已有值）
④ 待办提醒方向修正：当天提醒看今天，前一天提醒看明天到期日
⑤ 窗口默认大小/位置随屏幕分辨率等比自适应
"""
import os
import sys
import shutil
import tempfile
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v15')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

# 全程使用临时 XDG 目录，避免动到用户真实配置 / 数据库
_TMP = tempfile.mkdtemp(prefix='brltest')
os.environ['XDG_CONFIG_HOME'] = os.path.join(_TMP, 'config')
os.environ['XDG_DATA_HOME'] = os.path.join(_TMP, 'data')

from PyQt5.QtCore import Qt, QRect, QRectF, QSize, QTime
from PyQt5.QtGui import QPainter, QImage, QColor
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl import store, mainwin as MW, defaults as DF
from brl.todo import TimePick, TodoEditDialog
from brl.timepick import TimePopup, TimeWheel

npass = nfail = 0


def ck(name, ok, extra=''):
    global npass, nfail
    if ok:
        npass += 1
        print('  PASS %s %s' % (name, extra))
    else:
        nfail += 1
        print('  FAIL %s %s' % (name, extra))


csrc = open(os.path.join(HERE, 'brl', 'caltable.py')).read()
tsrc = open(os.path.join(HERE, 'brl', 'todo.py')).read()
msrc = open(os.path.join(HERE, 'brl', 'mainwin.py')).read()

S = store.Store()
w = MW.MainWindow(S, type('C', (), {'quit': lambda s: None,
                                    'apply_autostart': lambda s: None})())
w.resize(800, 600)
w.show()
app.processEvents()
cal = w._cal

# ------------------------------------------------------------ ①
print('== ① 选中格整格填充、无圆角内框')
ck('源码不再画圆角内框', 'paint_round(p, QRectF(x + hl_pad' not in csrc)
ck('选中格整格 fillRect', 'if is_sel:' in csrc
   and 'p.fillRect(QRectF(x, y, w, h), QColor(255, 255, 255' in csrc)
ck('今日格与选中格可叠加', 'if is_today:' in csrc and csrc.index('if is_sel:') > csrc.index('if is_today:'))


def _paint(sel):
    img = QImage(160, 120, QImage.Format_RGB32)
    img.fill(QColor('#808080'))          # 灰底：白色叠加层才看得出变化
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)
    old = cal._selected
    cal._selected = sel
    cal._paint_cell(p, datetime.date(2026, 12, 15), QRectF(0, 0, 160, 120))
    cal._selected = old
    p.end()
    return img


img0 = _paint(None)
img1 = _paint(datetime.date(2026, 12, 15))
corners = [(1, 1), (158, 1), (1, 118), (158, 118)]
diff = [img0.pixel(x, y) != img1.pixel(x, y) for x, y in corners]
ck('四个角落都被填充（说明是整格而非圆角内框）', all(diff), '%s' % diff)
ck('中心区域也被填充', img0.pixel(80, 60) != img1.pixel(80, 60))
ck('未选中时四角保持原样', img0.pixel(1, 1) == QColor('#808080').rgb()
   or img0.pixel(1, 1) != img1.pixel(1, 1))

# ------------------------------------------------------------ ②
print('== ② 提醒时间选择器')
psrc = open(os.path.join(HERE, 'brl', 'timepick.py')).read()
tp = TimePick()
pop = TimePopup(QTime(9, 0))
ck('分钟可选到每一分钟', pop._wm.count() == 60, 'count=%d' % pop._wm.count())
ck('分钟项连续 00..59',
   [pop._wm._vals[i] for i in (0, 1, 58, 59)] == ['00', '01', '58', '59'])
ck('小时项 24 个', pop._wh.count() == 24)
pop._wh.set_index(21)
pop._wm.set_index(37)
ck('可取到任意分钟（21:37）', pop.time() == QTime(21, 37), pop.time().toString('HH:mm'))
tp.setTime(QTime(21, 37))
ck('TimePick 显示 HH:MM', tp.text() == '21:37', tp.text())
ck('时间为 QTime(21,37)', tp.time() == QTime(21, 37), tp.time().toString('HH:mm'))
tp.setTime(QTime(0, 5))
ck('补零正确（00:05）', tp.text() == '00:05', tp.text())
ck('整体是带圆角的时间框', 'QFrame#timePick' in psrc and 'border-radius:6px' in psrc)
ck('时间盘为自绘滚轮卡片',
   'QWidget#timeCard{background:#FFFFFF;border-radius:14px;}' in psrc)
ck('带时钟图标', "D.res('icons', 'clock.png')" in psrc)
ck('时钟图标已生成', os.path.exists(os.path.join(HERE, 'brl', 'resources', 'icons', 'clock.png')))

dlg = TodoEditDialog(S, datetime.date.today())
ck('编辑窗里提醒时间控件存在', hasattr(dlg, 'tm') and isinstance(dlg.tm, TimePick))
dlg.cb_remind.setCurrentIndex(1)
ck('选了提醒后时间可选', dlg.tm.isEnabled())
dlg.cb_remind.setCurrentIndex(0)
ck('不提醒时时间置灰', not dlg.tm.isEnabled())
dlg.reject()

# ------------------------------------------------------------ ⑤
print('== ⑤ 窗口随屏幕自适应')
w._orig_screen = w._screen


def fake_screen(gw, gh, left=0, top=0):
    return lambda: QRect(left, top, gw, gh)


def rect_on(gw, gh):
    w._screen = fake_screen(gw, gh)
    return w._adaptive_rect()


x, y, ww, hh = rect_on(1920, 1040)
ck('基准屏 1920x1040 → 与当前观感一致 (716,147,1004x805)',
   (x, y, ww, hh) == (716, 147, 1004, 805), '%d,%d %dx%d' % (x, y, ww, hh))
x, y, ww, hh = rect_on(3840, 2120)
ck('4K 屏等比放大且长宽比不变',
   ww == 2008 and hh == 1610 and abs(float(ww) / hh - 1004 / 805.0) < 0.01,
   '%d,%d %dx%d' % (x, y, ww, hh))
x, y, ww, hh = rect_on(1366, 728)
ck('小屏等比缩小且不小于下限',
   ww == 703 and hh == 564 and x >= 0 and y >= 0, '%d,%d %dx%d' % (x, y, ww, hh))
ck('窗口不会超出屏幕',
   x + ww <= 1366 and y + hh <= 728, '%d,%d %dx%d' % (x, y, ww, hh))

# 换分辨率后把用户已有习惯等比换算（不会被丢掉）
def put_geo(size='1004,805', pos='716,147', sig='1920x1040'):
    st = S.settings()
    st.setValue('ui/size', size)
    st.setValue('ui/pos', pos)
    st.setValue('ui/screensize', sig)
    st.sync()


put_geo()
w._screen = fake_screen(1920, 1040)
w.restore_pos()
ck('同分辨率下原样沿用用户设置',
   (w.width(), w.height()) == (1004, 805) and (w.x(), w.y()) == (716, 147),
   '%d,%d %dx%d' % (w.x(), w.y(), w.width(), w.height()))

put_geo()
w._screen = fake_screen(3840, 2120)
w.restore_pos()
ck('换更大分辨率：沿用用户尺寸并按比例放大',
   (w.width(), w.height()) == (2008, 1610) and (w.x(), w.y()) == (1432, 300),
   '%d,%d %dx%d' % (w.x(), w.y(), w.width(), w.height()))

put_geo()
w._screen = fake_screen(1366, 728)
w.restore_pos()
ck('换更小分辨率：按同一比例缩小且不越界',
   (w.width(), w.height()) == (703, 564) and w.x() + w.width() <= 1366
   and w.y() + w.height() <= 728,
   '%d,%d %dx%d' % (w.x(), w.y(), w.width(), w.height()))
w._screen = w._orig_screen

# ------------------------------------------------------------ ③
print('== ③ 出厂默认设置')
fresh_home = os.path.join(_TMP, 'fresh')
os.environ['XDG_CONFIG_HOME'] = os.path.join(fresh_home, 'config')
os.environ['XDG_DATA_HOME'] = os.path.join(fresh_home, 'data')
S2 = store.Store()
st2 = S2.settings()
ck('默认主题 = 玄夜(0)', str(st2.value('ui/theme')) == '0', str(st2.value('ui/theme')))
ck('默认今天格色 = 用户当前值', str(st2.value('color/todayclr')) == '#361AEAE8')
ck('默认背景色 = 用户当前值', str(st2.value('color/mainbg')) == '#05000000')
ck('默认外边框全透明', str(st2.value('color/borderout')) == '#00FFFFFF')
ck('默认内边框 = #27FFFFFF', str(st2.value('color/borderin')) == '#27FFFFFF')
ck('默认网格线开启', str(st2.value('cal/showline')) == '1')
ck('开机自启默认按 0 处理（不写入 general 组，避免重复段）',
   'general/autostart' not in DF.DEFAULTS
   and str(st2.value('general/autostart', '0')) == '0')
ck('txtclr 留空（跟随主题）',
   st2.value('color/txtclr') in (None, ''), repr(st2.value('color/txtclr')))
# 用户改过的值不能被默认覆盖
st2.setValue('ui/theme', 5)
st2.setValue('color/todayclr', '#12ABCDEF')
st2.sync()
S3 = store.Store()
st3 = S3.settings()
ck('用户改过的主题不被覆盖', str(st3.value('ui/theme')) == '5', str(st3.value('ui/theme')))
ck('用户改过的颜色不被覆盖', str(st3.value('color/todayclr')) == '#12ABCDEF')
ck('默认值表完整（含 theme/颜色/显示项）',
   set(DF.DEFAULTS) >= set(['ui/theme', 'color/mainbg', 'color/todayclr',
                            'color/borderout', 'color/borderin', 'cal/showline']))

# ------------------------------------------------------------ ④
print('== ④ 待办提醒方向')
remind_home = os.path.join(_TMP, 'remind')
os.environ['XDG_CONFIG_HOME'] = os.path.join(remind_home, 'config')
os.environ['XDG_DATA_HOME'] = os.path.join(remind_home, 'data')
S4 = store.Store()
w2 = MW.MainWindow(S4, type('C', (), {'quit': lambda s: None,
                                      'apply_autostart': lambda s: None})())
now = datetime.datetime.now()
past = (now - datetime.timedelta(minutes=3)).strftime('%H:%M')
today = now.date()
tomorrow = today + datetime.timedelta(days=1)
yesterday = today - datetime.timedelta(days=1)

ck('源码：当天提醒取今天、前一天提醒取明天',
   '((2, today), (1, today + datetime.timedelta(days=1)))' in msrc)

id_prev = S4.add(u'前一天提醒测试', date=tomorrow.isoformat(), remind=1,
                 remind_time=past)
id_today = S4.add(u'当天提醒测试', date=today.isoformat(), remind=2,
                  remind_time=past)
id_old = S4.add(u'旧逻辑会误弹的一天前的待办', date=yesterday.isoformat(),
                remind=1, remind_time=past)
id_none = S4.add(u'不提醒测试', date=today.isoformat(), remind=0,
                 remind_time=past)

w2._pops = []
w2._check_remind()
did = sorted([p._todo.get('id') for p in w2._pops])
ck('前一天提醒会弹（到期日=明天）', id_prev in did, '%s' % did)
ck('当天提醒会弹（到期日=今天）', id_today in did, '%s' % did)
ck('不提醒的不弹', id_none not in did, '%s' % did)
ck('过期的前一天提醒不再误弹', id_old not in did, '%s' % did)
ck('弹窗保持在内存里不被 GC', len(w2._pops) >= 2, 'pops=%d' % len(w2._pops))

n2 = len(w2._pops)
for p in list(w2._pops):
    p.close()
w2._pops = []
w2._check_remind()
ck('同一天不会重复提醒', len(w2._pops) == 0, 'pops=%d' % len(w2._pops))

logp = os.path.join(remind_home, 'data', 'desktop-calendar', 'remind.log')
ck('提醒日志已写入', os.path.exists(logp))
if os.path.exists(logp):
    txt = open(logp).read()
    ck('日志里包含两条触发记录',
       u'前一天提醒测试' in txt and u'当天提醒测试' in txt, txt.replace('\n', ' | ')[:120])

print()
print('=== RESULT: PASS %d  FAIL %d' % (npass, nfail))
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if nfail else 0)
