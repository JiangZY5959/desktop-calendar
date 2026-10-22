# -*- coding: utf-8 -*-
"""在真实桌面上逐条验证 8 项修改要求。"""
import os
import re
import sys
import time
import subprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl'))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('all')


fails = []


def ck(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))
    if not cond:
        fails.append(name)


# ---------- 静态/代码层检查 ----------
import brl
import brl.appctx as A
import brl.mainwin as MW
import brl.caltable as CT
import brl.settings as ST
import brl.theme as T

ck('①悬浮条.模块已删除', not os.path.exists(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl', 'barwin.py')))
ck('①悬浮条.皮肤资源已删除', not os.path.exists(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 'brl', 'resources', 'skins')))
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'brl', 'mainwin.py'), encoding='utf-8').read()
ck('①悬浮条.菜单无该项', u'悬浮时钟' not in src)
ck('①悬浮条.无 bar 设置键', 'bar/enabled' not in src)
ck('①悬浮条.Context 无 bar 属性', 'self.bar' not in open(
    os.path.join(os.path.dirname(os.path.abspath(__file__)),
                 'brl', 'appctx.py'), encoding='utf-8').read())

ck('②主题.数量为8', len(T.ALL_THEMES) == 8, len(T.ALL_THEMES))
prev_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'brl', 'resources', 'img', 'theme')
prevs = sorted(os.listdir(prev_dir))
ck('②主题.预览8张', len(prevs) == 8, prevs)
names = [c['name'] for c in T.ALL_THEMES]
ck('②主题.原创命名', all(n in (u'玄夜', u'星空蓝', u'石墨灰', u'曙光橙', u'青瓷',
                            u'蜜桃粉', u'原野绿', u'樱紫') for n in names), names)

ct = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'brl', 'caltable.py'), encoding='utf-8').read()
ck('③宜忌.主界面已移除', u'宜' not in src, u'宜' in src)
ck('③宜忌.日历tips已移除', u'宜：' not in ct and u'忌：' not in ct)

ck('④改名.APP_NAME', A.APP_NAME == u'桌面悬浮日历', A.APP_NAME)
ck('④改名.版本', brl.__version__ == '1.2.0.0', brl.__version__)

keys = [k for k, _l, _a in ST.COLOR_DEFS]
ck('⑤边框.外边框可调', 'borderout' in keys, keys)
ck('⑤边框.内边框可调', 'borderin' in keys)
ck('⑤边框.主题含默认值', all('borderoutclr' in c and 'borderinclr' in c
                        for c in T.ALL_THEMES))
ck('⑤边框.日历引用内边框色', 'borderin' in ct)

st_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'brl', 'settings.py'), encoding='utf-8').read()
ck('⑥按钮.无自定义关闭按钮', 'btn_close' not in st_src)
ck('⑥按钮.页签为2个', u'基础设置 / 背景设置' in st_src[:200])

ck('⑦关于.菜单已添加', u'关于' in src and u'退出软件' in src)
i_about = src.index("m.addAction(u'关于'")
i_set = src.index("m.addAction(u'选项设置'")
i_quit = src.index("m.addAction(u'退出软件'")
ck('⑦关于.位于设置与退出之间', i_set < i_about < i_quit)

# ---------- 真实桌面运行检查 ----------
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

# 模拟用户旧窗口位置（部分超出屏幕）与超大尺寸，验证会被拉回屏内
st = A.S.STORE.settings()
st.setValue('ui/pos', '3000,3000')
st.setValue('ui/size', '1200,1100')
st.sync()

ctx = A.Context(app)
ctx.start()
app.processEvents()
win = ctx.win
win.show()
app.processEvents()
print('窗口几何:', win.x(), win.y(), win.width(), win.height())

# 用 xwininfo 读取真实映射后的窗口几何
out = subprocess.check_output(
    ['xwininfo', '-root', '-tree'], env=dict(os.environ, DISPLAY=':0')).decode('utf-8', 'replace')
pat = re.compile(r'(0x[0-9a-f]+)\s+"([^"]*)":\s+\("[^"]*"\s+"[^"]*"\)\s+'
                 r'(-?\d+)x(-?\d+)\+(-?\d+)\+(-?\d+)')
wins = [m for m in pat.finditer(out) if u'桌面悬浮日历' in m.group(2)]
ck('⑧.窗口已映射', len(wins) > 0, out.count(u'桌面悬浮日历'))
if wins:
    m = wins[0]
    w, h, x, y = (int(m.group(3)), int(m.group(4)),
                  int(m.group(5)), int(m.group(6)))
    print('  xwininfo: %dx%d+%d+%d' % (w, h, x, y))
    # 屏幕尺寸
    s = subprocess.check_output(
        ['xwininfo', '-root'], env=dict(os.environ, DISPLAY=':0')).decode('utf-8', 'replace')
    gs = re.search(r'geometry\s+(\d+)x(\d+)', s)
    SW, SH = int(gs.group(1)), int(gs.group(2))
    print('  屏幕: %dx%d' % (SW, SH))
    if '  +0+0' in s or ('X' not in s):
        pass
    ck('⑧.宽度不超屏', w <= SW, '%d<=%d' % (w, SW))
    ck('⑧.高度不超屏', h <= SH, '%d<=%d' % (h, SH))
    ck('⑧.左边界在屏内', x >= 0, x)
    ck('⑧.上边界在屏内', y >= 0, y)
    ck('⑧.右边界在屏内', x + w <= SW, '%d<=%d' % (x + w, SW))
    ck('⑧.下边界在屏内', y + h <= SH, '%d<=%d' % (y + h, SH))
else:
    fails.append('⑧.窗口未映射')

# 设置窗：页签数与颜色项
dlg = ST.SettingsDialog(ctx.store, None)
ck('⑧.设置页2页签', dlg._stack.count() == 2, dlg._stack.count())
ck('⑤.设置含边框颜色控件', 'borderout' in dlg._color_picks and 'borderin' in dlg._color_picks)

# 菜单项顺序
mw = ctx.win
menu = mw._menu()
acts = [a.text() for a in menu.actions()]
print('  菜单:', acts)
ck('⑦.菜单含关于', u'关于' in acts)
ck('①.菜单无悬浮时钟', u'悬浮时钟' not in acts)

print()
print('FAILED:', fails if fails else 'none')
sys.exit(1 if fails else 0)
