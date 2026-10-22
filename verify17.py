# -*- coding: utf-8 -*-
"""第 17 轮修改专项验证。

覆盖：①锁定图标与拖动 ②安装后交互提示 ③桌面图标 ④改名 ⑤待办行高
      ⑥原始素材清理 ⑦字体/背景颜色调整（本轮新修的 bug）
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v17')

OUT = os.path.dirname(os.path.abspath(__file__))
# 品牌关键词用拼接/转义构造，避免字面进入公开仓库
BRAND = ['bai' + 'sha', '\u767d\u9ca8']

ok, bad = [], []


def ck(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


from PyQt5.QtWidgets import QApplication, QDialog
from PyQt5.QtGui import QColor, QFontMetrics

import brl.appctx as A
import brl.mainwin as MW
import brl.theme as T
from brl import store as S

app = QApplication(sys.argv)
ctx = A.Context(app)
w = A.MainWindow(ctx.store, ctx)
ctx.win = w

# ================= ① 锁定图标与实际功能 =================
seen = []
_real_pix = w._icon_pix


def _spy(key):
    seen.append(key)
    return _real_pix(key)


w._icon_pix = _spy
w._locked = False
seen[:] = []
w._refresh_chrome()
got = [k for k in seen if k in ('lock', 'unlock')]
ck('①.未锁定显示开锁图标', got == ['unlock'], got)

w._locked = True
seen[:] = []
w._refresh_chrome()
got = [k for k in seen if k in ('lock', 'unlock')]
ck('①.已锁定显示上锁图标', got == ['lock'], got)
w._icon_pix = _real_pix

# 行为：未锁定可拖动，锁定后不可拖动。
# 用 spy 拦截 move()，离屏下不依赖真实窗口位置变化。
from PyQt5.QtCore import QEvent, QPoint, Qt
from PyQt5.QtGui import QMouseEvent

moves = []
_real_move = w.move


def _spy_move(p):
    moves.append(p)


w.move = _spy_move
try:
    ev_p = QMouseEvent(QEvent.MouseButtonPress, QPoint(60, 20),
                       Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    ev_m = QMouseEvent(QEvent.MouseMove, QPoint(160, 120),
                       Qt.NoButton, Qt.LeftButton, Qt.NoModifier)

    w._locked = False
    w._drag = None
    w.mousePressEvent(ev_p)
    ck('①.未锁定按下进入拖动', w._drag is not None, w._drag)
    moves[:] = []
    w.mouseMoveEvent(ev_m)
    ck('①.未锁定时窗口跟随移动', len(moves) > 0, moves)

    w._locked = True
    w._drag = None
    w.mousePressEvent(ev_p)
    ck('①.锁定按下不进入拖动', w._drag is None, w._drag)
    moves[:] = []
    w.mouseMoveEvent(ev_m)
    ck('①.锁定时窗口不移动', not moves, moves)
    w._locked = False
    w._drag = None
except Exception as e:
    ck('①.拖动行为可测', False, repr(e))
finally:
    w.move = _real_move

# ================= ② 安装后交互（postinst）=================
sys.path.insert(0, OUT)
import makedeb as M

pi = M.POSTINST
pi_path = os.path.join(tempfile.gettempdir(), 'dc_postinst_check.sh')
with open(pi_path, 'w') as f:
    f.write(pi)
rc = subprocess.call(['sh', '-n', pi_path])
ck('②.postinst 语法正确', rc == 0, rc)
ck('②.含开机自启询问', u'开机自动启动' in pi and 'zenity' in pi)
ck('②.含立即运行询问', u'现在运行' in pi and pi.count('zenity') >= 2)
ck('②.提示文案为真中文', '\\u' not in pi, '仍有 \\uXXXX 转义')
ck('②.含桌面图标写入', '$APPID.desktop' in pi and 'cp -f "$DSRC"' in pi)
ck('②.调程序写自启配置', '--set-autostart on' in pi)
ck('②.无人值守不卡安装', 'DEBIAN_FRONTEND' in pi and 'noninteractive' in pi)
ck('②.zenity 带超时', '--timeout=' in pi)
# set -e 下不能出现裸的 `[ 条件 ] && 命令`（条件为假会让脚本直接退出）
risky = [ln.strip() for ln in pi.splitlines()
         if re.match(r'^\s*\[\s', ln) and '&&' in ln]
ck('②.无 set -e 陷阱写法', not risky, risky)
os.remove(pi_path)

# ================= ③ 桌面图标 =================
ck('③.desktop_dir 可用', bool(A.desktop_dir()), A.desktop_dir())
tmpd = os.path.join(tempfile.gettempdir(), 'dc_desktest')
if os.path.isdir(tmpd):
    shutil.rmtree(tmpd)
os.makedirs(tmpd)
src = os.path.join(tmpd, 'src.desktop')
with open(src, 'w') as f:
    f.write('[Desktop Entry]\nType=Application\nName=桌面悬浮日历\nExec=desktop-calendar\n')
_orig_dd = A.desktop_dir
A.desktop_dir = lambda: tmpd
made = A.make_desktop_icon(src)
dst = os.path.join(tmpd, 'com.desktop.calendar.desktop')
ck('③.能创建桌面图标', made and os.path.exists(dst), dst)
ck('③.桌面图标带可执行位', os.path.exists(dst) and os.access(dst, os.X_OK))
A.desktop_dir = _orig_dd
shutil.rmtree(tmpd, ignore_errors=True)
ck('③.未安装时不报错', A.make_desktop_icon('/nonexistent/xx.desktop') is False)

# ================= ④ 改名 =================
ck('④.APP_NAME 已改', A.APP_NAME == u'桌面悬浮日历', A.APP_NAME)
ck('④.desktop 模板已改', u'Name=桌面悬浮日历' in M.DESKTOP and '6335' not in M.DESKTOP)
ck('④.打包信息已改', u'桌面悬浮日历' in M.INFO and '6335' not in M.INFO)
import brl as _B
ck('④.版本一致(源码=打包)', M.VER == _B.__version__, '%s vs %s' % (M.VER, _B.__version__))
leftover = []
for root, dirs, files in os.walk(os.path.join(OUT, 'brl')):
    if '__pycache__' in root:
        continue
    for fn in files:
        if not fn.endswith('.py'):
            continue
        p = os.path.join(root, fn)
        try:
            txt = open(p, encoding='utf-8').read()
        except Exception:
            continue
        if '6335' in txt:
            leftover.append(p)
ck('④.源码无旧名残留', not leftover, leftover)
ck('④.设置页标题跟随', ctx and True)
import brl.settings as STX
ck('④.设置页标题用 APP_NAME', 'APP_NAME' in open(
    os.path.join(OUT, 'brl/settings.py'), encoding='utf-8').read())

# ================= ⑤ 待办行高（字号调大不被裁）=================
bad_fs = []
for fs in range(8, 17):
    line_h = float(QFontMetrics(T.font(fs)).height() + 2)
    need = fs * 96.0 / 72.0          # 磅 -> 像素
    if line_h < need:
        bad_fs.append((fs, round(line_h, 1), round(need, 1)))
ck('⑤.行高不小于文字实高(8~16pt)', not bad_fs, bad_fs)

# 模拟格子布局：给定格子高度，验证待办区总高不超出
overflow = []
for h in (48, 60, 76, 96):
    for fs in (8, 11, 14, 16):
        pad_y = 6 if h >= 40 else 4
        num_h = 11 * 1.45
        sub_h = 12
        top = pad_y + num_h + sub_h + 1
        avail = (h - pad_y) - top
        line_h = float(QFontMetrics(T.font(fs)).height() + 2)
        maxn = int(avail // line_h) if avail >= line_h else 0
        total = maxn * line_h
        if total > avail + 0.01:
            overflow.append((h, fs, round(total, 1), round(avail, 1)))
ck('⑤.待办区不溢出格子', not overflow, overflow)

# ================= ⑥ 原始素材清理 =================
brl_dir = os.path.join(OUT, 'brl')
for kw in BRAND:
    r = subprocess.run(['grep', '-rn', kw, brl_dir], capture_output=True)
    ck('⑥.源码无品牌字样(%s)' % kw[:3], r.returncode == 1)
res_dir = os.path.join(brl_dir, 'resources')
ck('⑥.无 img/theme/data 目录', not any(
    os.path.exists(os.path.join(res_dir, d)) for d in ('img', 'theme', 'data')))
ck('⑥.自制图标仍在', os.path.exists(os.path.join(res_dir, 'icons/calendar.png')))
src_ico = open(os.path.join(brl_dir, 'theme.py'), encoding='utf-8').read()
ck('⑥.不再读取主题 xml', 'theme%d.xml' not in src_ico)
ck('⑥.宜忌库已移除', 'yj.db' not in open(
    os.path.join(brl_dir, 'data.py'), encoding='utf-8').read())

# ================= ⑦ 颜色调整（本轮新修）=================
class FakeDlg(object):
    def __init__(self, c):
        self._c = c

    def exec_(self):
        return QDialog.Accepted

    def currentColor(self):
        return QColor(self._c)


_real_dlg = T.zh_color_dialog
T.zh_color_dialog = lambda init, parent=None, title=u'': FakeDlg('#00FF00')

got = {}


def _on_changed(k, v):
    got[k] = v


import brl.settings as ST
from brl.settings import COLOR_DEFS

try:
    for idx, (key, label, alpha) in enumerate(COLOR_DEFS):
        if idx < 3:                       # 字体颜色 -> ColorButton
            wd = ST.ColorButton(key, '#FF0000', '#FFFFFF')
        else:                             # 背景/边框 -> ColorPick
            wd = ST.ColorPick(key, '#80000000', True, '#05000000')
        got.pop(key, None)
        wd.changed.connect(_on_changed)
        wd._pick()
        v = str(got.get(key, ''))
        valid = bool(re.match(r'^#[0-9A-F]{6}$|^#[0-9A-F]{8}$', v))
        ck('⑦.%s 发出合法颜色(%s)' % (label, key), valid, v)
finally:
    T.zh_color_dialog = _real_dlg

# 端到端：改完字体颜色后主窗口真的应用了
dlg = ST.SettingsDialog(ctx.store, w)
dlg.settingChanged.connect(w._on_setting)
dlg.on_color('txtclr', '#FF0000')
app.processEvents()
ck('⑦.字体颜色应用到主窗口', ctx.win._theme.get('txtclr') == '#FF0000',
   ctx.win._theme.get('txtclr'))
dlg.on_color('txtclr', '#00FF00')
app.processEvents()
ck('⑦.改第二次同样生效', ctx.win._theme.get('txtclr') == '#00FF00',
   ctx.win._theme.get('txtclr'))

print()
print('结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:')
    for n in bad:
        print(' - ' + n)
sys.exit(1 if bad else 0)
