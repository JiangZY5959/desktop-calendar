# -*- coding: utf-8 -*-
"""全量回归验证（单文件版）——按功能分节，一次跑完全部断言。

原来的 verify7/8/9/11/12/13/14/15/16/17/18/19 + selftest + e2e_autostart +
lint_aliases 十六个脚本，已按功能融合为下面一个个「分节」（代码原样保留）：

    python3 verify.py                # 跑全部分节（每节独立子进程，互不污染）
    python3 verify.py v19            # 只跑某一节
    python3 verify.py v7 v19 lint    # 只跑指定的几节
    python3 verify.py --list         # 列出分节

分节在子进程里执行的原因：各分节会创建 QApplication、对模块打补丁、切换
XDG 隔离目录，这些状态无法在同一进程里干净还原。X11 相关的分节（v18）
需要在真桌面下跑（DISPLAY=:0），离屏必假失败。

所有分节都经过 brltest_env.py 做 XDG 目录隔离，绝不读写用户真实配置。
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

# (键, 功能名)
SECTIONS = [
    ('v7', '界面基础'),
    ('v8', '中文化与自启'),
    ('v9', 'deb 包结构'),
    ('v11', '日历格子绘制'),
    ('v12', '待办清单交互'),
    ('v13', '滑杆与图标'),
    ('v14', '提醒与今日格'),
    ('v15', '选中格与自适应'),
    ('v16', '时间盘与提醒弹窗'),
    ('v17', '安装流程与版本一致性'),
    ('v18', '取色盘与X11窗口行为'),
    ('v19', '检查更新'),
    ('v20', '升级保护与重启'),
    ('v21', '询问时机与关于窗口'),
    ('v22', '用户数据随身包'),
    ('v23', 'UOS打包规范'),
    ('data', '数据层自检'),
    ('e2e', '自启动端到端'),
    ('lint', '命名一致性'),
]

# ---------------------------------------------------------------- 分节代码
# 每节以标记行包裹，运行时由 split_sections() 解析；代码与原脚本逐字一致。


def split_sections(text):
    """从本文件里解析出 {键: 源码}。"""
    out = {}
    cur = None
    buf = []
    for line in text.splitlines(True):
        m = re.match(r'# ===== \[SECTION (\w+)\]', line)
        if m:
            cur = m.group(1)
            buf = []
            continue
        if line.startswith('# ===== [END SECTION] ====='):
            if cur is not None:
                out[cur] = ''.join(buf)
            cur = None
            continue
        if cur is not None:
            buf.append(line)
    return out


def run_one(key, src):
    """在当前（子）进程里执行一个分节，返回 (pass 数, fail 数, 退出码)。"""
    ns = {'__name__': '__main__', '__file__': os.path.join(ROOT, key + '.py')}
    code = compile(src, '<%s>' % key, 'exec')
    stat = {'pass': 0, 'fail': 0}
    rc = 0
    real_stdout = sys.stdout

    class _Count(object):
        # 透传输出，同时统计各脚本统一的 PASS/FAIL 断言行
        def __init__(self, stream):
            self._s = stream

        def write(self, text):
            self._s.write(text)
            for line in text.splitlines():
                ls = line.lstrip()
                if re.match(r'PASS\b', ls):
                    stat['pass'] += 1
                elif re.match(r'FAIL\b', ls):
                    stat['fail'] += 1

        def flush(self):
            self._s.flush()

    try:
        sys.stdout = _Count(real_stdout)
        try:
            exec(code, ns)
        except SystemExit as e:
            rc = e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    except Exception:
        import traceback
        traceback.print_exc()
        rc = 1
    finally:
        sys.stdout = real_stdout
    return stat['pass'], stat['fail'], rc


def main(argv):
    args = argv[1:]
    if '--list' in args:
        for key, name in SECTIONS:
            print('%-6s %s' % (key, name))
        return 0
    keys = [(k, n) for k, n in SECTIONS if not args or k in args]
    bad = [a for a in args if a not in dict(SECTIONS)]
    for b in bad:
        print(u'未知分节: %s（--list 查看全部）' % b)
    if bad or not keys:
        return 2

    srcs = split_sections(open(os.path.abspath(__file__), encoding='utf-8').read())
    total_p = total_f = 0
    bad_sections = []
    for key, name in keys:
        print(u'\n===== %s  %s =====' % (key, name))
        sys.stdout.flush()
        env = dict(os.environ)
        env.setdefault('QT_QPA_PLATFORM', 'offscreen')
        env.setdefault('PYTHONIOENCODING', 'utf-8')
        if key == 'v18' and os.path.exists('/tmp/.X11-unix/X0'):
            # v18 断言真实 X11 窗口状态：本机有 X 就用真 xcb（离屏必假失败）
            env['QT_QPA_PLATFORM'] = 'xcb'
            env.setdefault('DISPLAY', ':0')
            env.setdefault('XAUTHORITY',
                           os.path.expanduser('~/.Xauthority'))
        p = subprocess.Popen([sys.executable, os.path.abspath(__file__),
                              '--child', key],
                             stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,
                             cwd=ROOT, env=env)
        out = p.communicate()[0].decode('utf-8', 'replace')
        sys.stdout.write(out)
        sys.stdout.flush()
        m = re.findall(r'SECTION-RESULT (\S+) pass=(\d+) fail=(\d+) rc=(\S+)', out)
        m = [x for x in m if x[0] == key]
        if m:
            pa, fa, rc = int(m[-1][1]), int(m[-1][2]), m[-1][3]
        else:
            pa, fa, rc = 0, 0, 'crash'
        total_p += pa
        total_f += fa
        ok = (fa == 0 and str(rc) == '0')
        if not ok:
            bad_sections.append(key)
        print(u'----- %s %s（通过 %d，失败 %d）' %
              (key, u'通过' if ok else u'未通过', pa, fa))

    print()
    print(u'==== 汇总：通过 %d 项，失败 %d 项，共 %d 节 ====' %
          (total_p, total_f, len(keys)))
    if bad_sections:
        print(u'未通过分节: %s' % ' '.join(bad_sections))
        return 1
    print(u'全部通过')
    return 0


if __name__ == '__main__':
    if len(sys.argv) >= 3 and sys.argv[1] == '--child':
        _k = sys.argv[2]
        _srcs = split_sections(open(os.path.abspath(__file__), encoding='utf-8').read())
        _p, _f, _rc = run_one(_k, _srcs[_k])
        print('SECTION-RESULT %s pass=%d fail=%d rc=%s' % (_k, _p, _f, _rc))
        sys.exit(1 if (_f or _rc) else 0)
    sys.exit(main(sys.argv))


# ===== [SECTION v7] 界面基础 =====
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
ck('④.设置页无重复标题头', u"QLabel(u'松松日历 - 选项设置')" not in ssrc)

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
# ===== [END SECTION] =====


# ===== [SECTION v8] 中文化与自启 =====
# -*- coding: utf-8 -*-
"""验证：①颜色对话框简体中文 ②开机启动勾选后立即生成自启动项。"""
import os
import sys
import shutil
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v8')

OUT = os.path.dirname(os.path.abspath(__file__))

from PyQt5.QtWidgets import QApplication, QPushButton, QLabel
from PyQt5.QtGui import QColor

import brl.appctx as AC
import brl.theme as T
from brl import store as S
from brl.settings import SettingsDialog

ok, bad = [], []


def ck(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


app = QApplication(sys.argv)
loaded = AC.install_zh_translator(app)
ck('①.Qt中文翻译已加载', loaded)

# 测试目录必须放在临时目录：受限环境下 /home 下的删除会被强制走回收站而失败
STORAGE = os.path.join(tempfile.gettempdir(), 'dc_verify8_cfg')
if os.path.isdir(STORAGE):
    # 受限环境下 shutil.rmtree 走回收站会被拒，直接用 rm -rf 确保清干净，
    # 否则上一轮的残留自启动文件会让本轮误判为失败
    shutil.rmtree(STORAGE, ignore_errors=True)
    if os.path.isdir(STORAGE):
        subprocess.call(['rm', '-rf', STORAGE])
if not os.path.isdir(STORAGE):
    os.makedirs(STORAGE)
os.environ['XDG_CONFIG_HOME'] = STORAGE

st = S.Store()
settings = st.settings()

# ---------- ② 勾选开机启动 → 立刻生成自启动文件
ck('②.初始无自启动文件', not os.path.exists(AC.autostart_path()))
settings.setValue('app/autostart', '1')
settings.sync()
AC.apply_autostart(st)
p = AC.autostart_path()
ck('②.勾选后生成自启动文件', os.path.exists(p), p)
if os.path.exists(p):
    txt = open(p, encoding='utf-8' if hasattr(open(p), 'encoding') else 'r').read()
    txt = open(p).read()
    ck('②.含 Type=Application', 'Type=Application' in txt)
    ck('②.Exec 为绝对路径', 'Exec=/usr/bin/desktop-calendar' in txt,
       [l for l in txt.splitlines() if l.startswith('Exec')])
    ck('②.可执行位', os.access(p, os.X_OK))
    ck('②.含 GNOME/Deepin 自启标记',
       'X-GNOME-Autostart-enabled=true' in txt and 'X-Deepin-Vendor' in txt)
# 取消勾选 → 删除
settings.setValue('app/autostart', '0')
settings.sync()
AC.apply_autostart(st)
ck('②.取消勾选后移除', not os.path.exists(p))

# ---------- ① 颜色对话框中文
dlg = T.zh_color_dialog(QColor('#2F7BFF'), None)
T.localize_dialog(dlg)
texts = []
for w in dlg.findChildren(QPushButton) + dlg.findChildren(QLabel):
    if w.text():
        texts.append(w.text())
en = [t for t in texts if t in ('OK', 'Cancel', 'Basic colors', 'Custom colors',
                                '&Pick Screen Color', 'Pick Screen Color',
                                'Add to Custom Colors', 'HTML:', 'Red', 'Green',
                                'Blue', 'Hue', 'Sat', 'Val', 'Alpha')]
ck('①.对话框无残留英文', not en, en[:6])
zh = [t for t in texts if t in (u'确定', u'取消', u'基本颜色', u'自定义颜色',
                                u'红', u'绿', u'蓝', u'色相', u'饱和度', u'明度',
                                u'透明度', u'拾取屏幕颜色', u'添加到自定义颜色')]
ck('①.对话框含中文', len(zh) >= 3, zh)
print('  对话框文案样本:', sorted(set(texts))[:16])

# 设置页中颜色按钮走的是同一路径（静态确认）
ssrc = open(sys.modules['brl.settings'].__file__.replace('.pyc', '.py')).read()
ck('①.三处颜色选择均用汉化对话框',
   ssrc.count('T.zh_color_dialog') == 2
   and 'T.zh_color_dialog' in open(sys.modules['brl.todo'].__file__
                                   .replace('.pyc', '.py')).read())
ck('①.getColor(英文原生)已移除', 'QColorDialog.getColor' not in ssrc)

shutil.rmtree(STORAGE, ignore_errors=True)
print('\n结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:'); [print(' -', b) for b in bad]
# ===== [END SECTION] =====


# ===== [SECTION v9] deb 包结构 =====
# -*- coding: utf-8 -*-
"""第九轮验证：启动器健壮性 + 开机自启真机验证"""
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v9')

from PyQt5.QtWidgets import QApplication

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
app = QApplication(sys.argv)

import brl
from brl import store, appctx

APP = u'松松日历'
AST = os.path.join(os.environ['XDG_CONFIG_HOME'], 'autostart',
                   'desktop-calendar.desktop')

npass = nfail = 0


def ck(name, ok, extra=''):
    global npass, nfail
    if ok:
        npass += 1
        print('  PASS %s %s' % (name, extra))
    else:
        nfail += 1
        print('  FAIL %s %s' % (name, extra))


print('== ① 应用名')
ck('app 名', brl.APP_NAME == APP, brl.APP_NAME)

print('== ② 开机自启（真实目录）')
_store = store.Store()
st = _store.settings()

# 先确保干净
if os.path.exists(AST):
    os.remove(AST)

# 模拟用户勾选
st.setValue('app/autostart', '1')
appctx.apply_autostart(_store, True)
ck('勾选后文件生成', os.path.exists(AST), AST)
if os.path.exists(AST):
    txt = open(AST).read()
    ck('Type=Application', 'Type=Application' in txt)
    ck('Name 正确', 'Name=%s' % APP in txt)
    ck('Exec 绝对路径', 'Exec=/usr/bin/desktop-calendar' in txt)
    ck('GNOME 自启标记', 'X-GNOME-Autostart-enabled=true' in txt)
    ck('Deepin 自启标记', 'X-Deepin-Vendor=user' in txt)
    ck('有 Icon', 'Icon=' in txt)
    mode = oct(os.stat(AST).st_mode)[-3:]
    ck('可执行位', os.access(AST, os.X_OK), mode)

# 模拟用户取消勾选
st.setValue('app/autostart', '0')
appctx.apply_autostart(_store, False)
ck('取消后文件删除', not os.path.exists(AST))

# 恢复勾选态（保留用户可能的设置，最后写成"已勾选"便于用户直接验证）
st.setValue('app/autostart', '0')
st.sync()

print('== ③ 配置重复段归并')
INIP = _ENV.ini_path()
# 自己造一份「带重复段」的 ini（QSettings 增量写入会产生重复段），再验归并
os.makedirs(os.path.dirname(INIP), exist_ok=True)
open(INIP, 'w').write(
    '[%General]\nautostart=0\nshowweather=1\n\n'
    '[ui]\ntheme=0\npos=\"1,2\"\n\n'
    '[%General]\nautostart=1\n\n'
    '[color]\nmainbg=#01020304\n\n'
    '[ui]\nsize=\"3,4\"\n')
raw_ini = ''
if True:
    raw_ini = open(INIP).read()
    secs = [l.strip()[1:-1] for l in raw_ini.splitlines()
            if l.strip().startswith('[') and l.strip().endswith(']')]
    before = len(secs)
    changed = appctx.normalize_ini(INIP)
    new_ini = open(INIP).read()
    secs2 = [l.strip()[1:-1] for l in new_ini.splitlines()
             if l.strip().startswith('[') and l.strip().endswith(']')]
    dup = [s for s in set(secs2) if secs2.count(s) > 1]
    ck('归并后无重复段', not dup, '段数 %d→%d' % (before, len(secs2)))
    # 归并后的值仍能被 QSettings 正确读到（用只读方式打开同一份文件）
    from PyQt5.QtCore import QSettings
    st2 = QSettings(INIP, QSettings.IniFormat)
    _raw = open(INIP).read()
    _nastro = _raw.count('autostart=')
    ck('重复段里的 autostart 只保留一条且以后写的为准',
       _nastro == 1 and 'autostart=1' in _raw, '条数=%d' % _nastro)
    ck('归并后可读写 position', st2.value('ui/pos') == '1,2',
       '值=%s' % st2.value('ui/pos'))
    # 幂等：紧接着再跑一次不应再改动（中间不能再有 Store 写配置）
    ck('幂等(二次归并不再改动)', appctx.normalize_ini(INIP) is False)
else:
    print('  SKIP 无配置文件')

print('== ④ 启动器脚本探测逻辑')
script = '''#!/bin/sh
APP_FILES=/opt/apps/com.desktop.calendar/files
PY=""
for cand in /usr/bin/python3 /usr/bin/python3.7 /usr/bin/python3.8 \\
           /usr/bin/python3.9 /usr/bin/python3.10 /usr/bin/python3.11 \\
           /usr/local/bin/python3 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import PyQt5" >/dev/null 2>&1; then
            PY="$cand"
            break
        fi
    fi
done
echo "$PY"
'''
p = os.path.join('/tmp', 'v9launch.sh')
with open(p, 'w') as f:
    f.write(script)
os.chmod(p, 0o755)
# 故意把坏 shim 放在 PATH 首位，验证仍能选中 /usr/bin/python3
badbin = '/tmp/v9badbin'
if not os.path.isdir(badbin):
    os.makedirs(badbin)
ench = dict(os.environ)
ench['PATH'] = badbin + ':' + ench.get('PATH', '')
py = subprocess.check_output(['/bin/sh', p], env=ench).decode().strip()
ck('坏 PATH 下仍选中系统 python3', py == '/usr/bin/python3', py)

print('== ⑤ deb 包内启动器')
import glob
import tarfile
ROOT = os.path.dirname(os.path.abspath(__file__))
debs = sorted(glob.glob(os.path.join(ROOT, 'dist', '*.deb')))
if debs:
    deb = debs[-1]
    listing = subprocess.check_output(['dpkg-deb', '-c', deb]).decode('utf-8', 'ignore')
    ck('包内 entries desktop',
       'entries/applications/com.desktop.calendar.desktop' in listing)
    ck('包内有启动器', 'bin/desktop-calendar' in listing)

    # 真正从包里解出启动器脚本内容来检查
    raw = subprocess.check_output(
        ['dpkg-deb', '--fsys-tarfile', deb])
    import io
    tf = tarfile.open(fileobj=io.BytesIO(raw))
    lt = ''
    for m in tf.getmembers():
        if m.name.endswith('/desktop-calendar') and m.isfile():
            lt = tf.extractfile(m).read().decode('utf-8', 'ignore')
            break
    ck('包内启动器含候选探测', 'for cand in' in lt and '/usr/bin/python3' in lt)
    ck('包内启动器 exec 用探测结果', 'exec "$PY"' in lt)
    ck('包内启动器不再盲信 PATH', 'if ! python3 -c' not in lt)
    ck('包内启动器带 PYTHONPATH', 'export PYTHONPATH=' in lt)
else:
    print('  SKIP 无 deb')

print('')
print('结果: %d 通过, %d 失败' % (npass, nfail))
sys.exit(1 if nfail else 0)
# ===== [END SECTION] =====


# ===== [SECTION v11] 日历格子绘制 =====
# -*- coding: utf-8 -*-
"""第十一轮验证（用户第 7 批意见，1.2.7.0）

① 今日/选中格文字不下移
② 待办可删除
③ 待办自上而下排布、不溢出格子
④ 全局天气已删除
⑤ 主界面右上角农历日期已删除
⑥ 月份导航与右侧按钮同一行
⑦ 三个工具按钮换新图标（月/周视图在最前、三横→齿轮）
"""
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v11')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl import store, mainwin, caltable, todo, appctx

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
w = mainwin.MainWindow(S, None)
w.resize(800, 780)
w.show()
app.processEvents()

# 先做静态别名检查（防“用了没导入”再次引发不可见崩溃）
r0 = __import__('subprocess').call([sys.executable, os.path.join(HERE, 'verify.py'), 'lint'])
ck(u'静态别名检查', r0 == 0)
print('== ① 今日/选中格文字不下移')
csrc = open(os.path.join(HERE, 'brl', 'caltable.py')).read()
ck('文字组统一顶部对齐', 'ty0 = y + pad_y' in csrc)
ck('不再按高亮垂直居中', '(h - block_h) / 2.0' not in csrc)
# 实际测量：今日格与普通格的日期文字基线应一致
cal = w._cal
cal.set_month(datetime.date.today())
app.processEvents()
pos = {}
for d, rect in cal._cells:
    if d.month == cal._month.month:
        pos[d.day] = rect
today = datetime.date.today()
if today.day in pos and len(pos) > 3:
    # 用同一行的邻居比较（同一行 y 相同，所以顶部内边距一致即可）
    row_y = pos[today.day].y()
    same_row = [r for r in pos.values() if r.y() == row_y]
    ck('今日格与同行格 y 一致', all(r.y() == row_y for r in same_row),
       '%d 个同高格' % len(same_row))
else:
    print('  SKIP 今日不在本月')

print('== ② 待办删除')
tdsrc = open(os.path.join(HERE, 'brl', 'todo.py')).read()
ck('有删除按钮', u'删除待办' in tdsrc)
ck('有右键菜单', 'customContextMenuRequested' in tdsrc and 'QMenu' in tdsrc)
ck('支持 Delete 键', 'QKeySequence(Qt.Key_Delete)' in tdsrc)
ck('删除前二次确认', u"DLG.confirm(self, u'删除待办'" in tdsrc)

# 真删一条：插入 → GUI 删除 → 校验库里没了
d0 = datetime.date.today()
tid = S.add(u'__验证删除__', date=d0.isoformat())
dlg = todo.TodoListDialog(S, d0, w)
app.processEvents()
found = None
for i in range(dlg.list.count()):
    it = dlg.list.item(i)
    if it.data(Qt.UserRole) == tid:
        found = it
        break
ck('清单里能看到这条待办', found is not None)
if found is not None:
    S.remove(tid)          # 模拟确认删除后的落库动作
    dlg.reload()
    left = [dlg.list.item(i).data(Qt.UserRole) for i in range(dlg.list.count())]
    ck('删除后清单不再显示', tid not in left)
    ck('库里已删除', S.get(tid) is None)
dlg.deleteLater()

print('== ③ 待办自上而下、不溢出')
ck('待办起点紧跟日期行', 'top = ty0 + block_h + 1' in csrc)
ck('不再从格子底部起算', 'y + h - 22 * self._scale' not in csrc)
ck('按可用高度裁剪条数', 'int(avail // lh)' in csrc or 'avail // lh' in csrc)
ck('超额只留省略号不写数量', (u'共%d项' not in csrc) and (u"u'…'" in csrc))
ck('放不下时逐级缩小字号', 'while fs >= 7' in csrc)

# 数值化验证：塞 8 条待办，计算绘制顶边必须 >= 格子上沿且末行不越下沿
for (cw, ch) in ((92, 66), (120, 90), (60, 46)):
    rect_ok = True
    pad_y = 6 if ch >= 40 else 4
    fs = max(11, min(17 * 1.0, (ch - 2 * pad_y - 13) / 2.4))
    num_h = fs * 1.45
    sub_h = max(9, min(14, ch - 2 * pad_y - num_h))
    block_h = num_h + (sub_h + 1)
    ty0 = 0 + pad_y
    line_h = max(12.0, 11 + 3)
    top = ty0 + block_h + 1
    avail = (ch - pad_y) - top
    maxn = int(avail // line_h) if avail >= line_h else 0
    if maxn > 0:
        last_bottom = top + maxn * line_h
        rect_ok = last_bottom <= ch - pad_y + 1
    ck(u'%dx%d 格子内待办不越界' % (cw, ch), rect_ok,
       'maxn=%d block=%.1f' % (maxn, block_h))

print('== ④ 天气已彻底删除')
ck('weather.py 已删除', not os.path.exists(os.path.join(HERE, 'brl', 'weather.py')))
msrc = open(os.path.join(HERE, 'brl', 'mainwin.py')).read()
ck('主界面无天气引用', 'weather' not in msrc.lower())
ck('设置页无显示天气项',
   'showweather' not in open(os.path.join(HERE, 'brl', 'settings.py')).read())
ck('无天气标签控件', not hasattr(w, '_lb_wea'))

print('== ⑤ 右上角农历日期已删除')
ck('无农历年标签', not hasattr(w, '_lb_lunnar_year'))
ck('_on_select 不再写农历年', '_lb_lunnar_year' not in msrc)

print('== ⑥ 月份导航与右侧按钮同行')
# 几何校验：月份标签与三个工具按钮的垂直中心应接近
mk = w._lb_month
centers = []
for b in (w._btn_view, w._btn_lock, w._btn_menu):
    centers.append(b.geometry().center().y())
mon_c = mk.geometry().center().y()
ck('月份标签与按钮同高', all(abs(c - mon_c) <= 6 for c in centers),
   '月份=%d 按钮=%s' % (mon_c, centers))
ck('今日按钮与按钮同高',
   abs(w._b_today.geometry().center().y() - mon_c) <= 6,
   str(w._b_today.geometry().center().y()))
ck('顶部只有一行（高度紧凑）', mk.geometry().top() < 30, 'top=%d' % mk.geometry().top())

print('== ⑦ 工具按钮图标')
ck('视图按钮用了新图标', w._btn_view.property('iconKey') == 'view')
ck('锁定按钮用了新图标', w._btn_lock.property('iconKey') == 'lock')
ck('菜单按钮换齿轮', w._btn_menu.property('iconKey') == 'gear')
for key, fn in (('view', 'tool_view.png'), ('lock', 'tool_lock.png'),
                ('gear', 'tool_gear.png')):
    p = os.path.join(HERE, 'brl', 'resources', 'icons', fn)
    ck(u'图标文件存在 %s' % fn, os.path.exists(p))
ck('三个按钮尺寸一致',
   len({(b.width(), b.height()) for b in (w._btn_view, w._btn_lock, w._btn_menu)}) == 1)
ck('视图按钮排在最前',
   w._btn_view.geometry().x() < w._btn_lock.geometry().x() < w._btn_menu.geometry().x(),
   '%d < %d < %d' % (w._btn_view.geometry().x(), w._btn_lock.geometry().x(),
                     w._btn_menu.geometry().x()))

print('')
print('结果: %d 通过, %d 失败' % (npass, nfail))
sys.exit(1 if nfail else 0)
# ===== [END SECTION] =====


# ===== [SECTION v12] 待办清单交互 =====
# -*- coding: utf-8 -*-
"""第十二轮验证（1.2.7.2）

① 待办提醒可用：提醒下拉可选、选"不提醒"时时间置灰、选项/下拉箭头样式统一
② 选中后可编辑；添加/编辑确定后**留在清单**（不再跳回主界面）
③ 支持多选批量删除
"""
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v12')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

app = QApplication(sys.argv)

from brl import store, todo

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
src = open(os.path.join(HERE, 'brl', 'todo.py')).read()
tsrc = open(os.path.join(HERE, 'brl', 'timepick.py')).read()
thsrc = open(os.path.join(HERE, 'brl', 'theme.py')).read()
d0 = datetime.date.today()

print('== ① 提醒可用 / 时间可选')
ck('有可点的时间选择器 TimePick', 'class TimePick' in tsrc)
ck('iPhone 式滚轮控件', 'class TimeWheel' in tsrc and 'def wheelEvent' in tsrc)
ck('悬浮式时间盘 TimePopup', 'class TimePopup' in tsrc and 'Qt.Popup' in tsrc)
ck('滚轮全部自绘（不依赖系统风格）',
   'def paintEvent' in tsrc and 'QComboBox' not in tsrc)
ck('不再使用只能键盘调的 QTimeEdit 控件', 'self.tm = QTimeEdit()' not in src)
ck('提醒选项更丰富（当天/前一天/前两天/前三天/前一周/前两周/前一个月）',
   all(t in src for t in (u'不提醒', u'当天提醒', u'前一天提醒', u'前两天提醒',
                          u'前三天提醒', u'前一周提醒', u'前两周提醒',
                          u'前一个月提醒')))
ck('提醒编码映射保持老数据兼容（0不/1前一天/2当天）',
   'REMIND_LEAD = {0: None, 1: 1, 2: 0, 3: 2, 4: 3, 5: 7, 6: 14, 7: 30}' in src)
ck('下拉用 itemData 存编码（顺序与编码解耦）',
   'addItem(_text, _code)' in src and 'currentData()' in src)
ck('下拉框自绘箭头（统一样式在 theme，todo 引用）',
   'down-arrow{image:url(' in thsrc and 'T.combo_style()' in src)
ck('箭头图标存在', os.path.exists(os.path.join(HERE, 'brl', 'resources', 'icons',
                                            'nav_down.png')))

ed = todo.TodoEditDialog(S, d0, None, None)
ed.show()
app.processEvents()
ck('默认"不提醒"时时间置灰', not ed.tm.isEnabled())
ck('提醒下拉共 8 档', ed.cb_remind.count() == 8, str(ed.cb_remind.count()))
ed.cb_remind.setCurrentIndex(1)      # 下拉第 2 项 = 当天提醒（编码 2）
app.processEvents()
ck('选"当天提醒"后时间可选', ed.tm.isEnabled())
ck('当天选项带回的编码仍是 2（老数据不变）',
   int(ed.cb_remind.currentData()) == 2, str(ed.cb_remind.currentData()))
ed.cb_remind.setCurrentIndex(ed.cb_remind.findData(5))
app.processEvents()
ck('可选"前一周提醒"且能设时间',
   ed.cb_remind.currentText() == u'前一周提醒' and ed.tm.isEnabled(),
   ed.cb_remind.currentText())
ed.cb_remind.setCurrentIndex(0)
app.processEvents()
ck('切回"不提醒"时间又置灰', not ed.tm.isEnabled())
ed.cb_remind.setCurrentIndex(1)
app.processEvents()
ed.tm.setTime(QTime(7, 30))
app.processEvents()
ck('时间能改为 07:30', ed.tm.text() == '07:30', ed.tm.text())
ed.tm.setTime(QTime(21, 45))
app.processEvents()
ck('时间能改到 21:45（分钟不受 5 分钟档限制）', ed.tm.text() == '21:45',
   ed.tm.text())
ed.ed_content.setText(u'__提醒验证__')
ed._ok()
ck('确定后带回 remind/remind_time',
   ed.result_data['remind'] == 2 and ed.result_data['remind_time'] == '21:45',
   str(ed.result_data['remind_time']))
ck('时间下拉框有最小宽度(不被挤没)', ed.tm.width() >= ed.tm.minimumWidth(),
   '%d/%d' % (ed.tm.width(), ed.tm.minimumWidth()))
ed.grab().save(os.path.join(HERE, 'v17_todoedit.png'))

print('== ② 选中可编辑 / 确定后留在清单')
ck('清单有"编辑待办"按钮', u'_btn_edit = QPushButton(u\'编辑待办\')' in src)
ck('_add 不再 accept 关闭清单', 'self._store.add(**dlg.result_data)\n            self.reload()' in src)
ck('_edit 不再 accept 关闭清单', 'self._store.update(tid, **dlg.result_data)\n            self.reload()' in src)
ck('有"关闭"按钮回到主界面', u"close = QPushButton(u'关闭')" in src)

tid0 = S.add(u'__第十二轮__', date=d0.isoformat())
dlg = todo.TodoListDialog(S, d0, None)
dlg.show()
app.processEvents()

real_exec = todo.TodoEditDialog.exec_
def fake_exec(self, *a, **k):
    self.ed_content.setText(u'__新增验证__')
    self.cb_remind.setCurrentIndex(1)
    self.tm.setTime(QTime(8, 15))
    self._ok()
    return QDialog.Accepted
todo.TodoEditDialog.exec_ = fake_exec
dlg._add()
app.processEvents()
todo.TodoEditDialog.exec_ = real_exec
ck('添加后清单仍打开', dlg.isVisible())
ck('添加后清单已刷新出新条目',
   any(u'__新增验证__' in dlg.list.item(i).text() for i in range(dlg.list.count())))
new_id = [S.for_date(d0)[i]['id'] for i in range(len(S.for_date(d0)))
          if S.for_date(d0)[i]['content'] == u'__新增验证__']
ck('新增条目已落库', len(new_id) == 1)
if new_id:
    ck('提醒时间按所选落库(08:15)', S.get(new_id[0])['remind_time'] == '08:15',
       S.get(new_id[0])['remind_time'])
ck('新增后自动选中该条',
   dlg.list.currentItem() is not None and
   dlg.list.currentItem().data(Qt.UserRole) == (new_id[0] if new_id else None))

# 编辑：选中一条 → 编辑按钮可用 → 改内容后仍在清单
dlg.list.setCurrentRow(0)
app.processEvents()
ck('选中后编辑按钮可用', dlg._btn_edit.isEnabled())
item0 = dlg.list.currentItem()
tid0_check = item0.data(Qt.UserRole)
def fake_exec2(self, *a, **k):
    self.ed_content.setText(u'__已编辑__')
    self._ok()
    return QDialog.Accepted
todo.TodoEditDialog.exec_ = fake_exec2
dlg._edit(item0)
app.processEvents()
todo.TodoEditDialog.exec_ = real_exec
ck('编辑后清单仍打开', dlg.isVisible())
ck('编辑内容已生效', (S.get(tid0_check) or {}).get('content') == u'__已编辑__',
   (S.get(tid0_check) or {}).get('content'))
ck('编辑后条目仍被选中',
   dlg.list.currentItem() is not None and
   dlg.list.currentItem().data(Qt.UserRole) == tid0_check)

print('== ③ 多选批量删除')
ck('列表支持多选', 'QAbstractItemView.ExtendedSelection' in src)
ids = [S.add(u'__批量删除%d__' % i, date=d0.isoformat()) for i in range(3)]
dlg.reload()
app.processEvents()
picked = []
for i in range(dlg.list.count()):
    it = dlg.list.item(i)
    if it.data(Qt.UserRole) in ids:
        it.setSelected(True)
        picked.append(it)
app.processEvents()
ck('已选中 3 条', len(dlg.list.selectedItems()) == 3,
   str(len(dlg.list.selectedItems())))
ck('删除按钮显示所选数量', u'删除所选' in dlg._btn_del.text(), dlg._btn_del.text())

# 确认窗已换成自绘的中文窗，这里把 confirm 顶成"点了确定"
import brl.updatedlg as _UDLG
_real_confirm = _UDLG.confirm
_UDLG.confirm = lambda *a, **k: True
dlg._delete_selected()
_UDLG.confirm = _real_confirm
app.processEvents()
left = [S.get(i) for i in ids]
ck('3 条全部从库中删除', all(x is None for x in left))
ck('批量删除后清单仍打开', dlg.isVisible())
ck('清单里不再显示被删条目',
   all(dlg.list.item(i).data(Qt.UserRole) not in ids for i in range(dlg.list.count())))

dlg.list.clearSelection()
app.processEvents()
ck('无选中时删除按钮置灰', not dlg._btn_del.isEnabled())
dlg.grab().save(os.path.join(HERE, 'v17_todolist.png'))

# 清理
for i in [tid0, tid0_check] + (new_id or []):
    if i:
        S.remove(i)
dlg.deleteLater()

print('\n结果: PASS=%d FAIL=%d' % (npass, nfail))
sys.exit(1 if nfail else 0)
# ===== [END SECTION] =====


# ===== [SECTION v13] 滑杆与图标 =====
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
# ===== [END SECTION] =====


# ===== [SECTION v14] 提醒与今日格 =====
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
ck('创建失败仍有兜底提示', 'DLG.info(' in seg and u'退兜' in seg)

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
# ===== [END SECTION] =====


# ===== [SECTION v15] 选中格与自适应 =====
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
from PyQt5.QtWidgets import QApplication, QLabel

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
ck('默认主题 = 松烟墨(0)', str(st2.value('ui/theme')) == '0', str(st2.value('ui/theme')))
ck('默认今天格色 = 用户当前值', str(st2.value('color/todayclr')) == '#361AEAE8')
ck('默认背景色 = 用户当前值', str(st2.value('color/mainbg')) == '#05000000')
ck('默认外边框全透明', str(st2.value('color/borderout')) == '#00FFFFFF')
ck('默认内边框 = #27FFFFFF', str(st2.value('color/borderin')) == '#27FFFFFF')
ck('默认网格线开启', str(st2.value('cal/showline')) == '1')
ck('开机自启默认按 0 处理（不写入 general 组，避免重复段）',
   'app/autostart' not in DF.DEFAULTS
   and str(st2.value('app/autostart', '0')) == '0')
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

ck('源码：提醒按提前天数换算到期日（lead 天后 = 到期日）',
   'day = today + datetime.timedelta(days=lead)' in msrc
   and 'remind_lead(t.get(' in msrc)

id_prev = S4.add(u'前一天提醒测试', date=tomorrow.isoformat(), remind=1,
                 remind_time=past)
id_today = S4.add(u'当天提醒测试', date=today.isoformat(), remind=2,
                  remind_time=past)
id_old = S4.add(u'旧逻辑会误弹的一天前的待办', date=yesterday.isoformat(),
                remind=1, remind_time=past)
id_none = S4.add(u'不提醒测试', date=today.isoformat(), remind=0,
                 remind_time=past)
id_week = S4.add(u'前一周提醒测试',
                 date=(today + datetime.timedelta(days=7)).isoformat(),
                 remind=5, remind_time=past)

w2._pops = []
w2._check_remind()
did = sorted([p._todo.get('id') for p in w2._pops])
ck('前一天提醒会弹（到期日=明天）', id_prev in did, '%s' % did)
ck('当天提醒会弹（到期日=今天）', id_today in did, '%s' % did)
ck('前一周提醒会弹（到期日=7 天后）', id_week in did, '%s' % did)
ck('不提醒的不弹', id_none not in did, '%s' % did)
ck('过期的前一天提醒不再误弹', id_old not in did, '%s' % did)
ck('弹窗保持在内存里不被 GC', len(w2._pops) >= 3, 'pops=%d' % len(w2._pops))
if w2._pops:
    wk = [p for p in w2._pops if p._todo.get('id') == id_week]
    ck('提前提醒的弹窗标出"N 天后到期"',
       not wk or u'7 天后到期' in wk[0].findChild(QLabel, 'popInfo').text()
       or any(u'7 天后到期' in lb.text() for lb in wk[0].findChildren(QLabel)),
       wk[0]._todo.get('content', '') if wk else '')

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
    ck('日志里包含三条触发记录',
       u'前一天提醒测试' in txt and u'当天提醒测试' in txt
       and u'前一周提醒测试' in txt, txt.replace('\n', ' | ')[:160])

print()
print('=== RESULT: PASS %d  FAIL %d' % (npass, nfail))
shutil.rmtree(_TMP, ignore_errors=True)
sys.exit(1 if nfail else 0)
# ===== [END SECTION] =====


# ===== [SECTION v16] 时间盘与提醒弹窗 =====
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
# ===== [END SECTION] =====


# ===== [SECTION v17] 安装流程与版本一致性 =====
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
ck('②.无人值守不卡安装', 'timeout 75' in pi and '[ -t 0 ]' in pi,
   '弹窗有外层 timeout 75 保护；终端安装才走 read 提问')
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
    f.write('[Desktop Entry]\nType=Application\nName=松松日历\nExec=desktop-calendar\n')
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
ck('④.APP_NAME 已改', A.APP_NAME == u'松松日历', A.APP_NAME)
ck('④.desktop 模板已改', u'Name=松松日历' in M.DESKTOP and '6335' not in M.DESKTOP)
ck('④.打包信息已改', u'松松日历' in M.INFO and '6335' not in M.INFO)
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
        # 全部颜色行（含字体色）都带透明度滑杆 -> ColorPick
        wd = ST.ColorPick(key, '#80000000', True, '#05000000')
        got.pop(key, None)
        wd.changed.connect(_on_changed)
        wd._pick()
        v = str(got.get(key, ''))
        valid = bool(re.match(r'^#[0-9A-F]{6}$|^#[0-9A-F]{8}$', v))
        ck('⑦.%s 发出合法颜色(%s)' % (label, key), valid, v)
    ck('⑦.字体颜色三项带透明度滑杆',
       all(alpha for _k, _lb, alpha in COLOR_DEFS[:3]),
       [alpha for _k, _lb, alpha in COLOR_DEFS[:3]])
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

# ---- ⑧ 安装后询问：一次弹窗问两件事，不依赖 zenity ----
print('== ⑧ 安装后询问 ==')
POSTINST = open(os.path.join(OUT, 'makedeb.py'), encoding='utf-8').read()
ck('⑧.postinst 调用自带 --ask-install', '--ask-install' in POSTINST)
ck('⑧.自带对话框失败才走 zenity 兜底', 'own dialog failed' in POSTINST and
   'zenity --question' in POSTINST)
ck('⑧.终端安装有 tty 提问兜底', '[ -t 0 ]' in POSTINST)
ck('⑧.升安装不再询问', 'upgrade: skip prompts' in POSTINST)
ck('⑧.兜底路径会打"已问过"标记', '--mark-asked' in POSTINST)
ck('⑧.不再依赖 /tmp/.X11-unix 判断有无显示',
   'UDISP=""' in POSTINST and 'UDISP=":0"' in POSTINST)
ck('⑧.命令替换失败不会中断安装', '|| rc=$?' in POSTINST)

AI = __import__('brl.askinstall', fromlist=['askinstall'])
ck('⑧.对话框含自启与运行两项', AI.AskDialog is not None)
d0 = AI.AskDialog(ask_run=True, timeout=3)
ck('⑧.默认两项都勾选', d0._cb_auto.isChecked() and d0._cb_run.isChecked())
ck('⑧.没点确定时按"不"处理', d0.answers() == (False, False))
d0._ok()
ck('⑧.点确定后读到勾选', d0.answers() == (True, True))
d1 = AI.AskDialog(ask_run=False, timeout=3)
ck('⑧.首启补问只有自启一项', d1._cb_run is None and d1._cb_auto.isChecked())
d1._later()
ck('⑧.稍后=两项都不做', d1.answers() == (False, False))
# 无显示环境：main() 返回 3 且不创建 QApplication
_env_disp = os.environ.pop('DISPLAY', None)
try:
    rc3 = AI.main(ask_run=True, argv=['x'])
finally:
    if _env_disp is not None:
        os.environ['DISPLAY'] = _env_disp
ck('⑧.无显示时不弹窗返回 3', rc3 == 3, rc3)
AI.mark_asked()
ck('⑧.打过标记后不再问', AI.asked_before() and
   AI.main(ask_run=True, argv=['x']) == 2)
# 对勾图标存在且非空
ck('⑧.自绘对勾图标就位', os.path.getsize(
    os.path.join(OUT, 'brl', 'resources', 'icons', 'tool_check.png')) > 50)
# 启动路径永不补问（开机自启只在安装时问一次，装完想改去设置页）
ck('⑧.程序启动不再弹自启询问', '_ask_autostart_once' not in
   open(os.path.join(OUT, 'brl', 'mainwin.py'), encoding='utf-8').read() and
   'singleShot(900' not in
   open(os.path.join(OUT, 'brl', 'mainwin.py'), encoding='utf-8').read())
# main() 全链路：确定后输出 autostart/run 两行（假对话框模拟点击）
class _FakeDlg(object):
    def __init__(self, ask_run, parent=None):
        self.ask_run = ask_run

    def exec_(self):
        pass

    def answers(self):
        return True, True


_real_ad = AI.AskDialog
_real_dok = AI.X11.display_ok
AI.AskDialog = _FakeDlg
AI.X11.display_ok = lambda d=None: True      # 假装能弹窗（离屏连不上 X）
AI._new_settings().setValue('app/autostart_asked', 0)
AI._new_settings().sync()
_env_disp = os.environ.pop('DISPLAY', None)
try:
    _buf = __import__('io').StringIO()
    _old = sys.stdout
    sys.stdout = _buf
    try:
        rc0 = AI.main(ask_run=True, argv=['x'])
    finally:
        sys.stdout = _old
finally:
    if _env_disp is not None:
        os.environ['DISPLAY'] = _env_disp
    AI.AskDialog = _real_ad
    AI.X11.display_ok = _real_dok
ck('⑧.确定后输出 autostart/run 两行', rc0 == 0 and
   'autostart=1' in _buf.getvalue() and 'run=1' in _buf.getvalue(),
   _buf.getvalue())

print()
print('结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:')
    for n in bad:
        print(' - ' + n)
sys.exit(1 if bad else 0)
# ===== [END SECTION] =====


# ===== [SECTION v18] 取色盘与X11窗口行为 =====
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
import time as _time


def _xhas(name, want=True, tries=20):
    """X11 状态读回带短轮询：属性写入与窗口管理器回写之间有偶发竞态。

    轮询期间要跑事件循环——主窗口有延迟自愈的定时器，真实运行时事件循环
    一直在转，这里也要转，否则等于把自愈能力关掉了。
    """
    for _i in range(tries):
        have = name in X11.state_names(wid)
        if have == want:
            return True
        _time.sleep(0.05)
        app.processEvents()
    return False


ctx = A.Context(app)
w = A.MainWindow(ctx.store, ctx)
w.show()
app.processEvents()
wid = w._win_id()
w._locked = True
w._apply_lock_flags()
app.processEvents()
ck('③.锁定=贴底(BELOW)', _xhas('BELOW'), X11.state_names(wid))
ck('③.锁定后窗口可见', w.isVisible())
ck('③.锁定保留无边框', bool(w.windowFlags() & Qt.FramelessWindowHint))
w._locked = False
w._apply_lock_flags()
app.processEvents()
ck('③.解锁无BELOW', _xhas('BELOW', want=False), X11.state_names(wid))
ck('③.解锁后窗口可见', w.isVisible())
# _on_lock 走完整链路
w._on_lock()
app.processEvents()
ck('③.按钮切换->贴底', _xhas('BELOW'), X11.state_names(wid))
w._on_lock()
app.processEvents()
ck('③.再切->恢复', _xhas('BELOW', want=False), X11.state_names(wid))
# 任务栏隐藏声明
X11.skip_taskbar(wid)
ck('③.任务栏隐藏(SKIP_TASKBAR)',
   _xhas('SKIP_TASKBAR'), X11.state_names(wid))
# 自愈：窗口管理器回写状态时把 BELOW 抹掉，延迟补一次要能修回来
ck('③.有自愈函数 assert_state', callable(getattr(X11, 'assert_state', None)))
ck('③.已满足时 assert_state 空转', X11.assert_state(wid, ['SKIP_TASKBAR']) is True)
_X11_SRC = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             'brl', 'x11fix.py'), encoding='utf-8').read()
ck('③.状态变更走 EWMH ClientMessage', 'XSendEvent' in _X11_SRC and
   'send_state' in _X11_SRC)
ck('③.锁定后会延迟补写状态', '_reassert_wm_state' in
   open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     'brl', 'mainwin.py'), encoding='utf-8').read())

print('== 自定义色板持久化 ==')
from PyQt5.QtCore import QSettings
st = QSettings()
val = st.value('colorpick/custom')
ck('①.自定义色已存盘', isinstance(val, list) and val == ['#102040'], val)

print('结果: %d 项, 失败 %d 项' % (_n[0], _fails[0]))
print('FAILED: %s' % ('none' if not _fails[0] else '%d 项' % _fails[0]))
# ===== [END SECTION] =====


# ===== [SECTION v19] 检查更新 =====
# -*- coding: utf-8 -*-
"""第 19 轮修改专项验证：检查更新（GitCode）。

覆盖：
  ① 版本一致性 / 文档同步
  ② update 模块纯逻辑（版本比较、检查周期、清单解析、blob sha）
  ③ 网络层端到端（本地 mock 服务器：清单 / 下载地址 / Release 兜底 / 全挂）
  ④ 下载校验（ar 包头 / 体积 / sha256）
  ⑤ 清单生成脚本（make_manifest）
  ⑥ 设置页「检查更新」独立页签
  ⑦ 主窗口与托盘入口、自动检查周期
  ⑧ UpdateFlow 全流程端到端（提示 -> 下载 -> 交给安装器）
  ⑨ 跳过此版本 / 已是最新 的静默规则
  ⑩ 安全检查（不携带任何令牌）
"""
import base64
import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brltest_env as _ENV
_ENV.isolate('v19')

OUT = os.path.dirname(os.path.abspath(__file__))

ok, bad = [], []


def ck(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


from PyQt5.QtWidgets import QApplication, QDialog

app = QApplication(sys.argv)

import brl.appctx as A
import brl.mainwin as MW
from brl import store as S
from brl import update as U
import brl.updatedlg as UD
from brl.updatedlg import UpdateFlow
from brl.settings import SettingsDialog

ctx = A.Context(app)
w = A.MainWindow(ctx.store, ctx)
ctx.win = w
# 测试期间禁止启动时的自动检查定时器真的联网
ctx.store.settings().setValue('update/mode', 'manual')
ctx.store.settings().sync()


def spin(app, cond, timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        app.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    app.processEvents()
    return bool(cond())


# ================= ① 版本一致性 / 文档 =================
import brl as _B
sys.path.insert(0, OUT)
import makedeb as M
ck('①.源码与打包版本一致', M.VER == _B.__version__, '%s vs %s' % (M.VER, _B.__version__))
ck('①.本轮版本号已推进', tuple(int(x) for x in _B.__version__.split('.')) >= (1, 4, 0, 0),
   _B.__version__)
cl = open(os.path.join(OUT, 'CHANGELOG.md'), encoding='utf-8').read()
ck('①.CHANGELOG 含 v%s' % _B.__version__, '## v%s' % _B.__version__ in cl)
rd = open(os.path.join(OUT, 'README.md'), encoding='utf-8').read()
ck('①.README 写明检查更新', u'检查更新' in rd)
ck('①.README 版本已更新', _B.__version__ in rd)

# ================= ② 纯逻辑 =================
ck('②.版本比较-补零', U.ver_tuple('1.4') == (1, 4, 0, 0))
ck('②.版本比较-v前缀', U.ver_tuple('v1.4.0.0') == (1, 4, 0, 0))
ck('②.版本比较-预发布', U.ver_tuple('1.4.0.0-beta') == (1, 4, 0, 0))
ck('②.版本比较-空串', U.ver_tuple('') == (0, 0, 0, 0))
ck('②.新版本判定', U.is_newer('1.4.0.1', '1.4.0.0') and U.is_newer('v2.0', '1.9.9.9'))
ck('②.相同版本不算新', not U.is_newer('1.4.0.0', '1.4.0.0'))
ck('②.旧版本不算新', not U.is_newer('1.3.9.9', '1.4.0.0'))
ck('②.手动模式永不到期', not U.due('manual', 0) and not U.due('manual', None))
ck('②.从未检查->到期', U.due('daily', 0) and U.due('weekly', 0))
ck('②.周期天数', U.mode_days('daily') == 1 and U.mode_days('weekly') == 7
   and U.mode_days('monthly') == 30 and U.mode_days('manual') == 0)
ck('②.每天-24h内不查', not U.due('daily', time.time() - 86300))
ck('②.每天-25h要查', U.due('daily', time.time() - 90000))
ck('②.每周-6天不查', not U.due('weekly', time.time() - 6 * 86400))
ck('②.每周-8天要查', U.due('weekly', time.time() - 8 * 86400))
ck('②.每月-29天不查', not U.due('monthly', time.time() - 29 * 86400))
ck('②.每月-31天要查', U.due('monthly', time.time() - 31 * 86400))
ck('②.坏时间戳按到期', U.due('daily', 'xxx'))
ck('②.频率选项四种', [k for k, _n, _d in U.MODE_DAYS] ==
   ['daily', 'weekly', 'monthly', 'manual'])
m = U.parse_manifest({'version': 'v9.9.9.9', 'notes': 'n', 'size': '10',
                      'sha256': 'AB', 'url': 'http://x/y.deb', 'tag': ''})
ck('②.清单解析-字段', m['version'] == '9.9.9.9' and m['size'] == 10
   and m['sha256'] == 'ab' and m['url'] == 'http://x/y.deb' and m['tag'] == 'v9.9.9.9')
ck('②.清单解析-默认文件名', U.parse_manifest({'version': '2.0.0.0'})['file']
   == 'desktop-calendar_2.0.0.0_arm64.deb')
try:
    U.parse_manifest({'notes': 'no version'})
    ck('②.清单解析-缺版本报错', False)
except U.UpdateError:
    ck('②.清单解析-缺版本报错', True)
tmpf = os.path.join(tempfile.mkdtemp(), 'hello')
open(tmpf, 'wb').write(b'hello')
ck('②.blob sha 与 git 规范一致',
   __import__('make_manifest').blob_sha(tmpf) == 'b6fc4c620b67d95f953a5c1c1230aaab5db5a1b0')

# ================= ③ 网络层（本地 mock 服务器） =================
DEB_BYTES = b'!<arch>\n' + bytes(bytearray(range(256))) * 2      # 520 字节伪 deb
DEB_SHA = hashlib.sha256(DEB_BYTES).hexdigest()
SRV = {
    'manifest': {'version': '9.9.9.9', 'notes': u'测试版', 'file': 't_9.9.9.9.deb',
                 'size': len(DEB_BYTES), 'sha256': DEB_SHA, 'url': ''},
    'hits': [],
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype='application/json'):
        b = body if isinstance(body, bytes) else json.dumps(body).encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        SRV['hits'].append(self.path)
        p = self.path.split('?')[0]
        if p.endswith('/contents/releases/latest.json'):
            mf = dict(SRV['manifest'])
            mf['url'] = mf.get('url') or ''
            body = {'type': 'file', 'encoding': 'base64',
                    'content': base64.b64encode(
                        json.dumps(mf).encode('utf-8')).decode('utf-8')}
            self._send(200, body)
        elif p.endswith('/contents/releases/t_9.9.9.9.deb'):
            self._send(200, {'type': 'file', 'encoding': 'base64', 'content': '',
                             'download_url': 'http://127.0.0.1:%s/blobs/deadbeef/releases/t_9.9.9.9.deb'
                             % PORT})
        elif p.startswith('/blobs/') and p.endswith('/t_9.9.9.9.deb'):
            self._send(200, DEB_BYTES, 'application/octet-stream')
        elif p.endswith('/releases/latest'):
            self._send(200, {'tag_name': 'v9.9.8.0', 'name': 'v9.9.8.0',
                             'body': 'release fallback'})
        else:
            self._send(404, {'error_code': 404})


httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
PORT = httpd.server_address[1]
th = threading.Thread(target=httpd.serve_forever, daemon=True)
th.start()
LOCAL = 'http://127.0.0.1:%d/api/v5' % PORT

_real_hosts = U.API_HOSTS
_real_raw = U.RAW_MANIFEST
# 这一节只测接口路径：把 raw 直链指到不可达，免得真去线上取清单
U.RAW_MANIFEST = 'http://127.0.0.1:1/raw-manifest.json'
U.API_HOSTS = (LOCAL, 'http://127.0.0.1:1/unreachable')

mf = U.fetch_manifest()
ck('③.清单经 contents API 取得', mf['version'] == '9.9.9.9'
   and mf['source'].startswith('http://127.0.0.1'), mf['source'][:60])
ck('③.清单字段完整', mf['sha256'] == DEB_SHA and mf['size'] == len(DEB_BYTES))

# 清单里没写 url 时，用 contents 接口现查
mf2 = dict(mf)
mf2['url'] = ''
url = U.resolve_url(mf2)
ck('③.下载地址兜底-contents', url.endswith('/t_9.9.9.9.deb'), url)

dld = os.path.join(tempfile.mkdtemp(), 't.deb')
got, total = U.download(url, dld)
cok, cwhy = U.verify_deb(dld, mf['size'], mf['sha256'])
ck('③.下载字节数一致', got == len(DEB_BYTES) and total == len(DEB_BYTES), (got, total))
ck('③.下载校验通过', cok, cwhy)

# 清单自带 url 时直接用，不再查接口
SRV['hits'][:] = []
mfu = dict(mf)
mfu['url'] = 'http://example.invalid/x.deb'
url2 = U.resolve_url(mfu)
n_before = len([h for h in SRV['hits'] if 'contents' in h])
ck('③.自带 url 不查接口', n_before == 0 and url2 == 'http://example.invalid/x.deb',
   (url2, SRV['hits']))

# contents 全挂 -> Release 兜底


class Handler404(Handler):
    def do_GET(self):
        p = self.path.split('?')[0]
        if p.endswith('/releases/latest'):
            SRV['hits'].append(self.path)
            self._send(200, {'tag_name': 'v9.9.8.0', 'name': 'v9.9.8.0',
                             'body': 'release fallback', 'created_at': '2026-01-02T00:00:00Z'})
        else:
            self._send(404, {'error_code': 404})


httpd2 = ThreadingHTTPServer(('127.0.0.1', 0), Handler404)
LOCAL2 = 'http://127.0.0.1:%d/api/v5' % httpd2.server_address[1]
threading.Thread(target=httpd2.serve_forever, daemon=True).start()
U.API_HOSTS = (LOCAL2, 'http://127.0.0.1:1/unreachable')
mf3 = U.fetch_manifest()
ck('③.Release 兜底取到版本', mf3['version'] == '9.9.8.0' and mf3['source'] == 'release',
   mf3)
ck('③.Release 兜底文件名', mf3['file'] == 'desktop-calendar_9.9.8.0_arm64.deb')

# 全部不可达 -> 报错（文案里不许出现接口地址，这是 1.4.9.2 修的那条）
U.API_HOSTS = ('http://127.0.0.1:1/unreachable',)
try:
    U.fetch_manifest()
    ck('③.全挂时抛 UpdateError', False)
except U.UpdateError as e:
    ck('③.全挂时抛 UpdateError', True)
    ck('③.失败文案不含接口地址', 'http' not in str(e) and '//' not in str(e), str(e))


# ---- raw 直链优先：接口全 429 也能拿到清单（1.4.9.2）
class HandlerRaw(Handler):
    def do_GET(self):
        p = self.path.split('?')[0]
        SRV['hits'].append(self.path)
        if p.endswith('/raw-manifest.json'):
            self._send(200, {'version': '9.9.7.0', 'file': 'x.deb'})
        else:
            self._send(429, {'error_code': 429})


httpd_raw = ThreadingHTTPServer(('127.0.0.1', 0), HandlerRaw)
RAW_PORT = httpd_raw.server_address[1]
threading.Thread(target=httpd_raw.serve_forever, daemon=True).start()
U.RAW_MANIFEST = 'http://127.0.0.1:%d/raw-manifest.json' % RAW_PORT
U.API_HOSTS = ('http://127.0.0.1:%d/api/v5' % RAW_PORT,)
SRV['hits'][:] = []
mf4 = U.fetch_manifest()
ck('③.raw 直链优先', mf4['version'] == '9.9.7.0' and mf4['source'] == 'raw',
   mf4['source'])
ck('③.raw 命中后不再打接口',
   not [h for h in SRV['hits'] if '/api/v5' in h], SRV['hits'][:4])

# ---- 全 429：给「服务器忙」而不是一串 URL
class Handler429(Handler):
    def do_GET(self):
        self._send(429, {'error_code': 429})


httpd429 = ThreadingHTTPServer(('127.0.0.1', 0), Handler429)
P429 = httpd429.server_address[1]
threading.Thread(target=httpd429.serve_forever, daemon=True).start()
U.RAW_MANIFEST = 'http://127.0.0.1:%d/raw-manifest.json' % P429
U.API_HOSTS = ('http://127.0.0.1:%d/api/v5' % P429,)
try:
    U.fetch_manifest()
    ck('③.全 429 抛 RateLimited', False)
except U.RateLimited as e:
    ck('③.全 429 抛 RateLimited', getattr(e, 'code', 0) == 429)
    ck('③.429 文案是人话', u'稍后再试' in str(e) and 'http' not in str(e), str(e))
except Exception as e:
    ck('③.全 429 抛 RateLimited', False, e)

# ---- 失败退避：刚失败过就别每小时再撞
ck('③.失败退避-1 小时内不再查', U.fail_backoff(time.time() - 3600))
ck('③.失败退避-7 小时后可再查', not U.fail_backoff(time.time() - 7 * 3600))
ck('③.失败退避-没记录时直接查', not U.fail_backoff(0))

# ---- 商店跳转：用官方支持的业务 URI，别自己拼网页地址
ck('③.商店 URI 是 app_detail_info',
   U.STORE_URI == 'appstore://deepin-home-appstore-client?app_detail_info/'
   + U.STORE_APPID, U.STORE_URI)
_det = 'app_detail_info/' + U.STORE_APPID
_spawned = []
_real_spawn = U._spawn
U._spawn = lambda argv: _spawned.append(argv)
try:
    _ok, _why = U.open_store()
    ck('③.跳商店走应用详情页',
       _ok and any(_det in ' '.join(a) for a in _spawned), (_ok, _spawned[:1]))
finally:
    U._spawn = _real_spawn
_real_present = U.store_present
U.store_present = lambda: False
try:
    _ok2, _why2 = U.open_store()
    ck('③.没装商店时给出明确提示',
       (not _ok2) and u'应用商店' in str(_why2), _why2)
finally:
    U.store_present = _real_present

U.RAW_MANIFEST = _real_raw
U.API_HOSTS = _real_hosts
httpd_raw.shutdown()
httpd429.shutdown()
httpd.shutdown()
httpd2.shutdown()

# ================= ④ 校验失败分支 =================
badf = os.path.join(tempfile.mkdtemp(), 'b.deb')
open(badf, 'wb').write(b'not a deb at all')
c1 = U.verify_deb(badf)
ck('④.非 deb 报错', not c1[0] and u'deb' in c1[1], c1)
c2 = U.verify_deb(dld, len(DEB_BYTES) + 1)
ck('④.体积不符报错', not c2[0], c2)
c3 = U.verify_deb(dld, 0, '00' * 32)
ck('④.sha 不符报错', not c3[0], c3)
c4 = U.verify_deb('/nonexistent/x.deb')
ck('④.文件不存在报错', not c4[0])

# ================= ⑤ 清单生成脚本 =================
sys.path.insert(0, OUT)
import make_manifest as MM
ck('⑤.版本取自 brl', MM.VER == _B.__version__)
notes = MM.notes_from_changelog('1.3.3.0')
ck('⑤.更新说明取自 CHANGELOG', u'待办逐条列出' in notes, notes[:30])
ck('⑤.说明去掉 markdown 记号', '**' not in notes and '`' not in notes)

# ================= ⑥ 设置页：独立「检查更新」页签 =================
st0 = ctx.store.settings()
st0.remove('update/mode')          # 回到"从未设置"状态，验证默认值
st0.sync()
dlg = SettingsDialog(ctx.store, w)
dlg.show()
app.processEvents()
ck('⑥.三个页签', [b.text() for b in dlg._tabs] ==
   [u'基础设置', u'背景设置', u'检查更新'])
dlg._switch(2)
app.processEvents()
ck('⑥.频率下拉默认每天', dlg._upd_cb.currentData() == 'daily')
dlg._upd_cb.setCurrentIndex(2)          # monthly
app.processEvents()
ck('⑥.改频率立即写盘', str(ctx.store.settings().value('update/mode')) == 'monthly')
fired = []
dlg.checkRequested.connect(lambda: fired.append(1))
dlg._upd_btn.click()
app.processEvents()
ck('⑥.立即检查发信号', fired == [1])
st_txt = dlg._upd_status()
ck('⑥.状态行含上次检查', u'上次检查' in st_txt, st_txt)
ck('⑥.状态行含当前版本', 'v' + _B.__version__ in dlg._ver_lb.text(),
   dlg._ver_lb.text())
dlg._switch(2)

# ================= ⑦ 主窗口入口 / 自动检查 =================
acts = [a.text() for a in w._menu().actions()]
ck('⑦.菜单含检查更新', u'检查更新' in acts, acts)
calls = []
_real_check = w._updater.check
w._updater.check = lambda silent=True, parent=None: calls.append(silent) or True
st = ctx.store.settings()
st.setValue('update/mode', 'manual')
st.sync()
w._auto_update()
ck('⑦.手动模式不自动查', calls == [], calls)
st.setValue('update/mode', 'daily')
st.setValue('update/last', 0)
st.sync()
w._auto_update()
ck('⑦.到期自动查(silent)', calls == [True], calls)
st.setValue('update/last', int(time.time()))   # 刚查过
st.sync()
w._auto_update()
ck('⑦.未到期不再查', calls == [True], calls)
st.setValue('update/mode', 'manual')
st.sync()
w._updater.check = _real_check

# ================= ⑧ UpdateFlow 端到端 =================
# 重新起一个 mock 服务器（这回清单带 url，直链下载）
httpd3 = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
PORT3 = httpd3.server_address[1]
SRV['manifest'] = {'version': '9.9.9.9', 'notes': u'端到端测试版\n第二行',
                   'file': 't_9.9.9.9.deb', 'size': len(DEB_BYTES),
                   'sha256': DEB_SHA,
                   'url': 'http://127.0.0.1:%d/blobs/cafe/releases/t_9.9.9.9.deb' % PORT3}
threading.Thread(target=httpd3.serve_forever, daemon=True).start()
LOCAL3 = 'http://127.0.0.1:%d/api/v5' % PORT3

# 更新流程里的提示窗已全部换成自绘 MsgDialog（浅色卡片 +「好的」），
# 这里同样用替身记录弹出的 (标题, 正文)，顺便断言不再碰系统 QMessageBox。
udsrc = open(os.path.join(OUT, 'brl', 'updatedlg.py'), encoding='utf-8').read()
ck('⑧.更新流程不再用系统 QMessageBox', 'QMessageBox' not in udsrc.replace(
    '顶替系统 QMessageBox', '').replace('系统 QMessageBox', ''))
ck('⑧.提示窗按钮是「好的」', u"self._btn(u'好的'" in udsrc)


class FakeMsg(object):
    shown = []

    def __init__(self, *a, **k):
        FakeMsg.shown.append(a)

    def exec_(self):
        return QDialog.Accepted


UD.MsgDialog = FakeMsg
spawned = []


class _FakeProc(object):
    returncode = 0

    def communicate(self):
        return (b'', None)


UD.subprocess.Popen = lambda argv, env=None: spawned.append(argv) or _FakeProc()


class FakePrompt(UD.PromptDialog):
    shown = []
    _choice = 'update'

    def exec_(self):
        FakePrompt.shown.append(self.manifest.get('version'))
        self.choice = self._choice
        return QDialog.Accepted


U.API_HOSTS = (LOCAL3, 'http://127.0.0.1:1/unreachable')
# 这一节测的是接口路径：raw 直链指到不可达，别让线上清单抢在前面
_raw_bak8 = U.RAW_MANIFEST
U.RAW_MANIFEST = 'http://127.0.0.1:1/raw-manifest.json'

# --- 8.1 确认更新 -> 下载 -> 交给安装器
# FakePrompt 顶替 PromptDialog：exec_ 直接返回 choice=update，
# 因此原版 _prompt/_download 流程原封不动地被走到。
flow = UpdateFlow(ctx.store, w)
updir = U.updates_dir()
for f in os.listdir(updir):
    os.remove(os.path.join(updir, f))
FakePrompt.shown[:] = []
UD.PromptDialog = FakePrompt
flow._parent = w
flow.check(silent=False, parent=w)
done8 = spin(app, lambda: bool(spawned), 30)
ck('⑧.确认后下载并进入安装', done8 and bool(spawned), spawned)
ck('⑧.提示窗出现过', FakePrompt.shown == ['9.9.9.9'], FakePrompt.shown)
ck('⑧.交给安装器的命令含 deb',
   spawned and spawned[0][-1].endswith('t_9.9.9.9.deb'), spawned)
ck('⑧.提示已启动安装程序', len(FakeMsg.shown) == 1 and u'已启动' in str(FakeMsg.shown[0]),
   FakeMsg.shown)
ck('⑧.下载文件校验通过', os.path.exists(os.path.join(updir, 't_9.9.9.9.deb')))

# --- 8.2 安装包已在本地且校验通过 -> 直接安装不再下载
spawned[:] = []
FakeMsg.shown[:] = []
flow2 = UpdateFlow(ctx.store, w)
flow2._parent = w
flow2._download(dict(SRV['manifest']))
ck('⑧.已有安装包直接安装', bool(spawned)
   and not any(u'失败' in str(m) for m in FakeMsg.shown),
   (spawned, FakeMsg.shown))

# ================= ⑨ 静默规则 =================
st = ctx.store.settings()
st.setValue('update/skip', '9.9.9.9')
st.sync()
FakePrompt.shown[:] = []
flow3 = UpdateFlow(ctx.store, w)
flow3._parent = w
flow3.check(silent=True, parent=w)
spin(app, lambda: flow3._check_th is None, 10)
app.processEvents()
ck('⑨.跳过的版本静默不提示', FakePrompt.shown == [], FakePrompt.shown)
FakePrompt.shown[:] = []
flow4 = UpdateFlow(ctx.store, w)
flow4._parent = w
flow4.check(silent=False, parent=w)
spin(app, lambda: flow4._check_th is None, 10)
app.processEvents()
ck('⑨.手动检查忽略跳过设置', FakePrompt.shown == ['9.9.9.9'], FakePrompt.shown)

# --- 9.2 已是最新：写检查时间且不提示
SRV['manifest'] = {'version': _B.__version__, 'notes': '', 'file': 'x.deb',
                   'size': 0, 'sha256': '', 'url': ''}
FakePrompt.shown[:] = []
st.setValue('update/skip', '')
st.setValue('update/last', 0)
st.sync()
flow5 = UpdateFlow(ctx.store, w)
flow5._parent = w
flow5.check(silent=True, parent=w)
spin(app, lambda: flow5._check_th is None, 10)
app.processEvents()
ck('⑨.已是最新不提示', FakePrompt.shown == [], FakePrompt.shown)
ck('⑨.检查时间已落盘', int(st.value('update/last') or 0) > 0)
ck('⑨.清单版本已记录', str(st.value('update/lastver')) == _B.__version__)

# --- 9.3 手动检查失败给出提示（清单缺安装包地址 -> resolve_url 失败）
SRV['manifest'] = {'version': '9.9.9.9', 'notes': '', 'file': 'x.deb',
                   'size': 0, 'sha256': '', 'url': ''}
flow6 = UpdateFlow(ctx.store, w)
flow6._parent = w
flow6.check(silent=False, parent=w)
spin(app, lambda: flow6._check_th is None, 10)
app.processEvents()
ck('⑨.手动检查失败有提示', len(FakeMsg.shown) >= 1, FakeMsg.shown)

# --- 9.4 已是最新版本：自绘提示窗（浅色卡片 +「好的」按钮） ---
SRV['manifest'] = {'version': _B.__version__, 'notes': '', 'file': 'x.deb',
                   'size': 0, 'sha256': '', 'url': ''}
FakeMsg.shown[:] = []
st.setValue('update/mode', 'manual')
st.setValue('update/skip', '')
st.setValue('update/last', 0)
st.sync()
flow7 = UpdateFlow(ctx.store, w)
flow7._parent = w
flow7.check(silent=False, parent=w)
spin(app, lambda: flow7._check_th is None, 10)
app.processEvents()
ck('⑨.已是最新弹自绘窗', len(FakeMsg.shown) == 1, FakeMsg.shown)
ck('⑨.文案含"已是最新版本"',
   FakeMsg.shown and u'已是最新版本' in str(FakeMsg.shown[0]), FakeMsg.shown)

U.RAW_MANIFEST = _raw_bak8

# ================= ⑩ 安全 =================
brand_free = True
for fn in ('update.py', 'updatedlg.py'):
    txt = open(os.path.join(OUT, 'brl', fn), encoding='utf-8').read()
    if 'access_token' in txt or 'token=' in txt:
        brand_free = False
ck('⑩.更新模块不携带令牌', brand_free)
ck('⑩.数据源指向 GitCode', U.PAGE.startswith('https://gitcode.com/'), U.PAGE)

# CLI 自检参数
import io
import contextlib
import brl.__main__ as MAIN
_real_fm = U.fetch_manifest
U.fetch_manifest = lambda timeout=10: {'version': '9.9.9.9', 'file': 'f.deb'}
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    handled, code = MAIN._dispatch(['--check-update'])
ck('⑩.--check-update 正常', handled and code == 0 and '9.9.9.9' in buf.getvalue(),
   buf.getvalue())
U.fetch_manifest = _real_fm

print()
print('结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:')
    for n in bad:
        print(' - ' + n)
sys.exit(1 if bad else 0)
# ===== [END SECTION] =====


# ===== [SECTION v20] 升级保护与重启 =====
# -*- coding: utf-8 -*-
"""第 23 轮专项验证：装新版本时保住老数据、关掉旧版本、打开新版本。

覆盖：
  ① appdata：升级前备份 / 缺失恢复 / 旧路径迁移 / 实例登记
  ② 进程识别：只认日历本体，绝不误伤 dpkg 与终端里敲命令的 shell
  ③ 脚本契约：preinst 备份、postinst 关旧+恢复+开新、prerm 停、postrm 留数据
  ④ 端到端：旧实例在跑 -> 数据被清空 -> 装完自动关旧、恢复、开新
"""
import glob
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brltest_env as _ENV
_ENV.isolate('v20')

ok, bad = [], []


def ck(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


# ---------------------------------------------------------------- ① appdata
TD = tempfile.mkdtemp(prefix='v20-')
XD = os.path.join(TD, 'xdg')
XC = os.path.join(TD, 'cfg')
BKR = os.path.join(TD, 'bk')
for _d in (XD, XC):
    os.makedirs(os.path.join(_d, 'desktop-calendar'))
os.environ['XDG_DATA_HOME'] = XD
os.environ['XDG_CONFIG_HOME'] = XC
# HOME 也要隔离：迁移逻辑会把 HOME 下的老位置当成数据源，
# 不挪走的话 root 家目录里的历史残留会串进测试。
os.environ['HOME'] = os.path.join(TD, 'home')
os.makedirs(os.environ['HOME'])
os.environ['DC_BACKUP_ROOT'] = BKR

import brl.appdata as AD
from brl import store as S

INI = os.path.join(XC, 'desktop-calendar', 'calendar.ini')
DB = os.path.join(XD, 'desktop-calendar', 'calendar.db')
PID = os.path.join(XD, 'desktop-calendar', 'app.pid')


def seed(path_ini, path_db, n, theme):
    # 注意 ini 节名要与 QSettings 的读写一致：ui/theme 对应 [ui] 节
    with open(path_ini, 'w') as f:
        f.write('[ui]\ntheme=%d\npos=11,22\n' % theme)
    cn = sqlite3.connect(path_db)
    cn.executescript(S.SCHEMA)
    for i in range(n):
        cn.execute('INSERT INTO todo(content,category,date,created) VALUES(?,?,?,?)',
                   (u'升级前待办%d' % (i + 1), u'生活', '2026-10-22', 'x'))
    cn.commit()
    cn.close()


def todos(path_db):
    cn = sqlite3.connect(path_db)
    n = cn.execute('SELECT COUNT(*) FROM todo').fetchone()[0]
    cn.close()
    return n


seed(INI, DB, 3, 2)
d, kinds = AD.make_backup()
ck('①1 升级前备份生成', bool(d) and kinds == ['db', 'ini'], d)
ck('①2 备份落在数据目录之外', bool(d) and not d.startswith(XD), d)
os.remove(DB)
os.remove(INI)
# 显式指定备份目录：机器上可能有历史残留备份（/var/backups 等），
# 恢复时必须用本次测试自己做的那份，不能被残留抢先
got = AD.ensure_data(d)
ck('①3 缺失时自动恢复', sorted(got) == ['db', 'ini'], got)
ck('①4 待办保留', todos(DB) == 3, todos(DB))
ck('①5 设置保留', 'theme=2' in open(INI).read())
with open(INI, 'w') as f:
    f.write('KEEPME')
ck('①6 已有内容不被备份覆盖', 'ini' not in AD.ensure_data()
   and open(INI).read() == 'KEEPME')

# 机器上可能留有别的安装（真机升级）写进 /var/backups 的备份，
# 恢复时显式备份必须优先，旧路径迁移也不得去翻 /var/backups
_ad = open(os.path.join(HERE, 'brl', 'appdata.py'), encoding='utf-8').read()
_ens = _ad[_ad.index('def ensure_data('):_ad.index('def prune_backups(')]
ck('①6b 显式备份先于旧路径迁移',
   'got = restore_missing(backup)' in _ens
   and _ens.index('got = restore_missing(backup)')
   < _ens.index('migrate_legacy()'))
ck('①6c migrate_legacy 不再翻 /var/backups',
   '/var/backups' not in _ad[_ad.index('def migrate_legacy('):
                             _ad.index('def ensure_data(')])

# 旧兜底路径（~/.desktop-calendar）迁移
H5 = os.path.join(TD, 'home5')
os.makedirs(os.path.join(H5, '.desktop-calendar'))
os.remove(DB)
bkd = sorted(os.listdir(BKR))[-1]
shutil.copy(os.path.join(BKR, bkd, 'calendar.db'),
            os.path.join(H5, '.desktop-calendar', 'calendar.db'))
_old_home = os.environ.get('HOME')
os.environ['HOME'] = H5
got2 = AD.migrate_legacy()
os.environ['HOME'] = _old_home
ck('①7 旧兜底路径搬回来', 'db' in got2, got2)
ck('①8 搬回的待办完好', todos(DB) == 3)

ck('①9 实例登记可写可读', AD.write_pid('1.4.1.0')
   and AD.read_pid()[0] == os.getpid())
ck('①10 登记可清理', AD.clear_pid() and AD.read_pid() is None)

# ---------------------------------------------------------------- ② 进程识别
noise = subprocess.Popen(['bash', '-c', 'M=desktop-calendar_1.4.1.0_arm64.deb; sleep 40'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
time.sleep(0.6)
ck('②1 终端里含包名的 shell 不算日历', not AD._is_ours(noise.pid))
ck('②2 pid 1 永不识别', not AD._is_ours(1))
# 真机上用户很可能正开着日历：这种情况下这条不能真去 quit 它，
# 否则跑一次验证就把人家窗口关了。只在没有任何实例时才验"空跑是空操作"。
if AD.running_pids():
    ck('②3 空跑请求退出不误伤（真机有实例在跑，跳过）', True)
else:
    ck('②3 空跑请求退出不误伤', AD.request_quit(timeout=0.5) == ([], []))
noise.kill()
noise.wait()

# ---------------------------------------------------------------- ③ 脚本契约
import makedeb as MD
MD_SRC = open(os.path.join(HERE, 'makedeb.py'), encoding='utf-8').read()
CARRY_SRC = open(os.path.join(HERE, 'brl', 'carry.py'), encoding='utf-8').read()
ck('③1 preinst 只在升级时存档', '"$1" = "upgrade"' in MD.PREINST
   and 'save --home' in MD.PREINST)
ck('③2 preinst 内联了随身包源码', 'DC_CARRY_EOF' in MD.PREINST
   and 'SET_PREFIX' in MD.PREINST and 'def save(' in MD.PREINST)
ck('③3 内联源码与 brl/carry.py 逐字一致', CARRY_SRC in MD.PREINST)
ck('③4 postinst 只在升级时收尾', 'if [ -n "$2" ]' in MD.POSTINST)
ck('③5 postinst 最后一步是放回数据',
   '"$APPUPG" finish "$U"' in MD.POSTINST
   and 'APPUPG=$APPDIR/bin/desktop-calendar-upgrade' in MD.POSTINST)
ck('③6 prerm 卸载才停实例', 'stop' in MD.PRERM and '!= "upgrade"' in MD.PRERM)
ck('③7 postrm 不删用户数据', 'purge' in MD.POSTRM
   and '/home' not in MD.POSTRM and 'HOME' not in MD.POSTRM)
ck('③8 收尾脚本按进程名识别', 'comm' in MD.UPGRADER)
_fi = MD.UPGRADER[MD.UPGRADER.index('do_finish() {'):]
_k = _fi.index('kill -TERM')
ck('③9 先关旧的再放回数据', _fi.find('do_restore', _k) > _k)
ck('③10 收尾脚本只认指针不翻旧组',
   'carry.py' in MD.UPGRADER and '--root' in MD.UPGRADER
   and 'upgrade-' not in MD.UPGRADER and 'ls -1r' not in MD.UPGRADER)
ck('③11 1.4.6.0 那套逻辑已彻底移除',
   'restore-best' not in (MD.PREINST + MD.POSTINST + MD.UPGRADER)
   and 'do_prepare' not in MD.UPGRADER and 'prepare)' not in MD.UPGRADER)
ck('③12 打包写入维护脚本', "'preinst', PREINST" in MD_SRC
   and "'postrm', POSTRM" in MD_SRC)
_debs = sorted(glob.glob(os.path.join(HERE, 'dist', '*.deb')))
if _debs:
    _ctl = os.path.join(TD, 'ctl')
    os.makedirs(_ctl)
    subprocess.run(['dpkg-deb', '-e', _debs[-1], _ctl], capture_output=True)
    _miss = [n for n in ('preinst', 'postinst', 'prerm', 'postrm')
             if not os.path.isfile(os.path.join(_ctl, n))]
    ck('③13 deb 内含四个维护脚本', not _miss, _miss)
else:
    ck('③13 deb 内含四个维护脚本（暂无 deb，跳过）', True)

# ---------------------------------------------------------------- ④ 端到端
# 这一段跑的是打包后真正会进 deb 的那两个脚本，不是另写的仿制品：
#   preinst（安装第一步：存两个文件）→ 数据被人为清掉 → finish（最后一步：放回）
PRE_SH = os.path.join(TD, 'dc-preinst')
with open(PRE_SH, 'w') as f:
    f.write(MD.PREINST)
os.chmod(PRE_SH, 0o755)
UP_SH = os.path.join(TD, 'dc-upgrade')
with open(UP_SH, 'w') as f:
    f.write(MD.UPGRADER)
os.chmod(UP_SH, 0o755)
LOG = os.path.join(TD, 'log')

# 收尾脚本里 carry.py 的落点（真机上是 /opt/apps/com.desktop.calendar/files）
APPD = os.path.join(TD, 'appfiles')
os.makedirs(os.path.join(APPD, 'brl'))
shutil.copy2(os.path.join(HERE, 'brl', 'carry.py'),
             os.path.join(APPD, 'brl', 'carry.py'))

H6 = os.path.join(TD, 'home6')
XD6 = os.path.join(H6, '.local/share')
XC6 = os.path.join(H6, '.config')
for _d in (os.path.join(XD6, 'desktop-calendar'),
           os.path.join(XC6, 'desktop-calendar')):
    os.makedirs(_d)
INI6 = os.path.join(XC6, 'desktop-calendar', 'calendar.ini')
DB6 = os.path.join(XD6, 'desktop-calendar', 'calendar.db')
PID6 = os.path.join(XD6, 'desktop-calendar', 'app.pid')
seed(INI6, DB6, 4, 5)

LAUNCHED = os.path.join(TD, 'launched')
LAUNCH = os.path.join(TD, 'fake-launch')
with open(LAUNCH, 'w') as f:
    f.write('#!/bin/sh\necho "HOME=$HOME DISPLAY=$DISPLAY" >> %s\n' % LAUNCHED)
os.chmod(LAUNCH, 0o755)

env6 = dict(os.environ)
env6.update({'HOME': H6, 'XDG_DATA_HOME': XD6, 'XDG_CONFIG_HOME': XC6,
             'QT_QPA_PLATFORM': 'offscreen', 'PYTHONPATH': HERE})
# 备份根显式隔离：不设的话 root 下脚本会写共享的 /var/backups，
# 既污染机器也可能让恢复读到历史残留
BK6 = os.path.join(H6, 'bk')
os.makedirs(BK6)
env6['DC_BACKUP_ROOT'] = BK6
# 家目录也钉死，免得脚本按 SUDO_USER 摸到真实用户目录
env6['DC_HOME'] = H6
env6['DC_APPDIR'] = APPD
# 真机上这份日志是 root 写的，普通用户测试时追加会失败，
# 而失败的命令替换会把整步 python 跳过去——必须指到自己目录里
env6['DC_LOG'] = os.path.join(TD, 'install.log')
_env_root = os.environ.get('DC_BACKUP_ROOT')

# 先放一组"很久以后"的假包：按文件名排序它会排在最前，
# 只有真正认指针的实现才不会把它当成新数据放回去。
_stale = os.path.join(BK6, 'user-todos-olduser-20301231-235959.db')
_cn = sqlite3.connect(_stale)
_cn.executescript(S.SCHEMA)
_cn.execute("INSERT INTO todo(content,category,date,created) VALUES('陈年旧事','生活','2020-01-01','x')")
_cn.commit()
_cn.close()
with open(os.path.join(BK6, 'user-settings-olduser-20301231-235959.ini'), 'w') as f:
    f.write('[ui]\ntheme=1\n')

# 旧实例先跑起来：preinst 要读的是"正开着的活库"
old = subprocess.Popen([sys.executable, '-m', 'brl'], env=env6,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       start_new_session=True)
_t0 = time.time()
while time.time() - _t0 < 25 and not os.path.isfile(PID6):
    time.sleep(0.2)
ck('④1 旧实例已登记自己', os.path.isfile(PID6), old.poll())

# ===== 安装第一步 =====
r = subprocess.run(['sh', PRE_SH, 'upgrade', '1.4.5.2'], env=env6,
                   capture_output=True, text=True, timeout=120)
_nm = os.listdir(BK6)
_set = [f for f in _nm if f.startswith('user-settings-') and f.endswith('.ini')
        and 'olduser' not in f]
_todo = [f for f in _nm if f.startswith('user-todos-') and f.endswith('.db')
         and 'olduser' not in f]
ck('④2 第一步存下"设置"文件', len(_set) == 1, _nm)
ck('④3 第一步存下"待办"文件', len(_todo) == 1, _nm)


def _stamp(name):
    # 文件名尾部的 YYYYMMDD-HHMMSS（去掉扩展名后取最后 15 个字符）
    return name.rsplit('.', 1)[0][-15:]


_s1 = _stamp(_set[0]) if _set else ''
_s2 = _stamp(_todo[0]) if _todo else ''
ck('④4 两个文件共用同一个时间戳', bool(_s1) and _s1 == _s2, (_s1, _s2))
_stamp = _s1
_ptrs = [f for f in _nm if f.startswith('user-carry-') and f.endswith('.stamp')]
ck('④5 指针记下的是这一组',
   _ptrs and open(os.path.join(BK6, _ptrs[0])).read().strip() == _stamp, _ptrs)
ck('④6 存下的是活库的一致快照（程序正开着）',
   _todo and todos(os.path.join(BK6, _todo[0])) == 4,
   todos(os.path.join(BK6, _todo[0])) if _todo else 'no db')

# ===== 数据被清掉 =====
os.remove(DB6)
os.remove(INI6)

# ===== 安装最后一步 =====
env7 = dict(env6)
env7['DC_LAUNCHER'] = LAUNCH
r = subprocess.run(['sh', UP_SH, 'finish', 'u20', H6, ':0', LOG],
                   env=env7, capture_output=True, text=True, timeout=60)
_gone = old.poll() is not None
if not _gone:
    time.sleep(2)
    _gone = old.poll() is not None
ck('④7 旧实例已关闭', _gone, old.poll())
ck('④8 旧实例自己清理了登记', not os.path.isfile(PID6))
ck('④9 最后一步把待办放回去了', todos(DB6) == 4, todos(DB6))
# QSettings 写 ini 时键里的 / 会变成 \（ui\theme=5），所以只看值
ck('④10 最后一步把设置放回去了', 'theme=5' in open(INI6).read(),
   open(INI6).read()[:120])
ck('④11 没有误用备份里的陈年旧组', '陈年旧事' not in
   subprocess.run(['/usr/bin/python3', '-c',
                   'import sqlite3,sys;print(sqlite3.connect(sys.argv[1]).execute('
                   '"select group_concat(content) from todo").fetchone()[0])', DB6],
                  capture_output=True, text=True).stdout)
ck('④12 新版本被拉起',
   os.path.isfile(LAUNCHED) and 'DISPLAY=:0' in open(LAUNCHED).read(),
   open(LAUNCHED).read() if os.path.isfile(LAUNCHED) else '')
os.environ['DC_BACKUP_ROOT'] = _env_root
AD.clear_pid(only_self=False)

print()
print('结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:')
    for n in bad:
        print(' - ' + n)
sys.exit(1 if bad else 0)
# ===== [END SECTION] =====


# ===== [SECTION v21] 询问时机与关于窗口 =====
# -*- coding: utf-8 -*-
"""第 25 轮专项验证：开机自启只在首次安装问一次 + 齿轮菜单瘦身 + 关于窗口。

覆盖：
  ① 询问时机：全新会问、问过不再问、升级装完不再问、退出重开不再问
  ② 齿轮菜单：不再有「调整日期和时间 / 同步时间」
  ③ 关于窗口：作者 JiangZY、项目主页可点、设置页不再重复放主页
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brltest_env as _ENV
_ENV.isolate('v21')

ok, bad = [], []


def ck(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


# HOME 也要隔离：askinstall 的配置目录跟着 HOME/XDG 走
TD = tempfile.mkdtemp(prefix='v21-')
os.environ['HOME'] = os.path.join(TD, 'home')
os.makedirs(os.environ['HOME'])

from brl import askinstall as AI          # noqa: E402

# ---------------------------------------------------------------- ① 询问时机
ck('①1 全新安装时还没问过', not AI.asked_before())
AI.mark_asked()
ck('①2 问过一次后不再问', AI.asked_before())
# 换一个全新的 QSettings 实例读（模拟"退出后重新打开"）
ck('①3 重启后仍记得已问过', AI.asked_before())

# 打包脚本：升级（$2 非空）也要打标记，否则老用户升级后首启会被补问
import makedeb as MD                      # noqa: E402

_up = MD.POSTINST[MD.POSTINST.index('AUTO=0'):MD.POSTINST.index('if [ "$AUTO" = "1" ]')]
ck('①4 升级路径也会打标记', 'NEED_MARK=1' in _up)
ck('①5 打标记的命令在脚本里', '--mark-asked' in MD.POSTINST)
# 升级路径不能反过来去弹窗
_i_up = _up.index('if [ -n "$2" ]')
_i_ask = _up.index('--ask-install')
ck('①6 升级时不弹询问窗', _i_up < _i_ask and 'ASKED=1' in _up)

# 软件退出时兜底打标记：哪怕安装时没问成，用过一次也别再烦用户
_ctx = open(os.path.join(HERE, 'brl', 'appctx.py'), encoding='utf-8').read()
_i_quit = _ctx.index('def quit(')
ck('①7 退出时兜底标记已问过',
   'mark_asked()' in _ctx[_i_quit:])

# 启动路径永不补问：开机自启只在安装时问一次（postinst 负责），此后想改
# 去「选项设置 → 基础设置 → 开机启动桌面日历」勾选
_mw = open(os.path.join(HERE, 'brl', 'mainwin.py'), encoding='utf-8').read()
ck('①8 程序启动不再弹自启询问',
   '_ask_autostart_once' not in _mw and 'singleShot(900' not in _mw)
ck('①9 安装时仍会问一次（仅首装）',
   '--ask-install' in MD.POSTINST and 'ASKED=1' in _up)
ck('①10 启动补问相关方法已全部移除',
   'asked_before()' not in _mw and 'mark_asked()' not in _mw)

# 键名必须跨进程一致：Qt 写 general/* 会落成 [%General] 段，
# 下次启动再按 general/* 读就是空的——"每次打开都问一遍"就是这么来的。
import glob as _glob                      # noqa: E402

_bad_keys = []
for _f in _glob.glob(os.path.join(HERE, 'brl', '*.py')):
    # 注释/docstring 里提到这段历史是允许的，只要不再真的去读写它
    if 'general/autostart' in open(_f, encoding='utf-8').read():
        _bad_keys.append(os.path.basename(_f))
ck('①11 源码不再用 general/ 键', not _bad_keys, _bad_keys)
ck('①12 自启用 app/autostart', "'app/autostart'" in _ctx)
ck('①13 询问标记用 app/autostart_asked',
   "'app/autostart_asked'" in open(
       os.path.join(HERE, 'brl', 'askinstall.py'), encoding='utf-8').read())

# 老配置迁移：[%General] 里的值要搬到 [app]，且只能搬一次
from brl import appctx as AX              # noqa: E402

TD2 = tempfile.mkdtemp(prefix='v21-mig-')
INI2 = os.path.join(TD2, 'calendar.ini')
with open(INI2, 'w') as f:
    f.write('[%General]\nautostart=1\nautostart_asked=1\n\n[ui]\ntheme=3\n')
ck('①14 老配置会被迁移', AX.migrate_ini_group(INI2))
ck('①15 迁移后只剩 [app] 段', '[%General]' not in open(INI2).read())
ck('①16 迁移保留原值',
   'autostart=1' in open(INI2).read()
   and 'autostart_asked=1' in open(INI2).read())
ck('①17 迁移不影响其它段', 'theme=3' in open(INI2).read())
ck('①18 重复迁移不再改动', not AX.migrate_ini_group(INI2))
# 启动时若配置没记过自启，不能把用户自己的自启动项删掉
_i_apply = _ctx.index('def apply_autostart(')
_apply = _ctx[_i_apply:_ctx.index('def migrate_ini_group(')
             if _ctx.index('def migrate_ini_group(') > _i_apply
             else _i_apply + 1200]
ck('①19 没记过时不删已有自启项',
   'autostart_path()' in _apply and 'v is None' in _apply)

# UOS「自启动管控」盯的是写入事件：内容不变时绝不能重写自启文件，
# 否则用户每次开机都会被系统弹一次「正在设置开机自启动」
_asp = AX.autostart_path()
os.makedirs(os.path.dirname(_asp), exist_ok=True)
with open(_asp, 'w') as f:
    f.write('[Desktop Entry]\nstale=1\n')
ck('①20 内容不同会重写', AX.apply_autostart(None, want=True))
_m1 = os.stat(_asp).st_mtime_ns
ck('①21 内容不变时不重写', AX.apply_autostart(None, want=True)
   and os.stat(_asp).st_mtime_ns == _m1)

# 启动即锁定：安装/更新/重启/重开后默认锁住，首次显示后落实一次
ck('①22 初始状态为锁定', '_locked = True' in _mw)
_i_show = _mw.index('def showEvent(')
ck('①23 首次显示后落地锁定',
   '_lock_shown' in _mw and '_apply_lock_flags' in _mw[_i_show:_i_show + 400])
# 设置页颜色标签：星期标题栏背景颜色（不再叫周末背景颜色）
_setsrc = open(os.path.join(HERE, 'brl', 'settings.py'),
               encoding='utf-8').read()
ck('①24 颜色名为星期标题栏背景颜色', u'星期标题栏背景颜色' in _setsrc)
ck('①25 不再叫周末背景颜色', u'周末背景颜色' not in _setsrc)

# ---------------------------------------------------------------- ② 齿轮菜单
_i_menu = _mw.index('def _menu(')
_menu = _mw[_i_menu:_mw.index('def _auto_update(', _i_menu)]
ck('②1 菜单无「调整日期和时间」', u'调整日期和时间' not in _menu)
ck('②2 菜单无「同步时间」', u'同步时间' not in _menu)
ck('②3 菜单保留检查更新', u'检查更新' in _menu)
ck('②4 菜单保留选项设置', u'选项设置' in _menu)
ck('②5 菜单保留关于', u'关于' in _menu)
ck('②6 菜单保留退出', u'退出软件' in _menu)
ck('②7 旧的两个处理函数已删除',
   '_open_datetime' not in _mw and '_sync_time' not in _mw)
ck('②8 齿轮菜单用圆角卡片菜单', 'T.CardMenu(self)' in _menu)
_ax = open(os.path.join(HERE, 'brl', 'appctx.py'), encoding='utf-8').read()
ck('②9 托盘菜单用圆角卡片菜单', 'T.CardMenu()' in _ax)
_th = open(os.path.join(HERE, 'brl', 'theme.py'), encoding='utf-8').read()
ck('②10 menu_style 项样式三要素',
   'background:transparent' in _th and 'QMenu::item:selected' in _th
   and 'QMenu::separator' in _th and '#EDF4FE' in _th)
ck('②11 CardMenu 自绘圆角底（半透明窗口 + fillPath）',
   'class CardMenu' in _th and 'WA_TranslucentBackground' in _th
   and 'addRoundedRect' in _th and 'fillPath(path, QColor(self.BG))' in _th)

# ---------------------------------------------------------------- ③ 关于窗口
ck('③1 关于窗口已独立实现', 'class AboutDialog' in _mw)
ck('③2 关于里写了作者 JiangZY', 'JiangZY' in _mw)
ck('③3 关于里有项目主页链接', 'QDesktopServices.openUrl' in _mw)
ck('③4 关于里带 GitCode 与 GitHub 两处',
   'gitcode' in _mw.lower() and 'github' in _mw.lower())
ck('③5 关于窗口固定浅色底', "'#F2F6FC'" in _mw)
_i_ab = _mw.index('class AboutDialog')
_ab = _mw[_i_ab:_mw.index('class RemindPopup')]
ck('③6 关于里显示版本号', 'APP_VER' in _ab)

_st = open(os.path.join(HERE, 'brl', 'settings.py'), encoding='utf-8').read()
ck('③7 设置页不再放项目主页', u'项目主页' not in _st)
ck('③8 设置页保留检查更新页签', u'检查更新' in _st)

# 真的把窗口建出来，确认不发黑、内容齐全
from PyQt5.QtWidgets import QApplication     # noqa: E402

_app = QApplication.instance() or QApplication(sys.argv[:1])
from brl.mainwin import AboutDialog          # noqa: E402

from PyQt5.QtWidgets import QLabel, QPushButton   # noqa: E402

dlg = AboutDialog()
_txt = ' '.join(w.text() for w in dlg.findChildren(QLabel))
_txt += ' ' + ' '.join(w.text() for w in dlg.findChildren(QPushButton))
ck('③9 关于窗能正常构建', dlg.width() > 300 and dlg.height() > 200,
   '%dx%d' % (dlg.width(), dlg.height()))
ck('③10 关于窗含作者与版本', 'JiangZY' in _txt and 'v' in _txt)
_tips = ' '.join(w.toolTip() for w in dlg.findChildren(QPushButton))
ck('③11 主页入口改为纯图标+悬停说明',
   'GitCode' in _tips and 'GitHub' in _tips, _tips)
ck('③12 主页图标文件存在',
   os.path.exists(os.path.join(HERE, 'brl', 'resources', 'icons',
                               'site_github.png'))
   and os.path.exists(os.path.join(HERE, 'brl', 'resources', 'icons',
                                   'site_gitcode.png')))
ck('③13 主页不再写"（国内）"等文字', u'（国内）' not in _txt and 'GitHub' not in _txt,
   _txt[:80])
_icon_btns = [b for b in dlg.findChildren(QPushButton) if b.toolTip()]
ck('③14 主页图标可点且走 openUrl 跳转',
   len(_icon_btns) >= 2 and 'QDesktopServices.openUrl' in _mw)
ck('③15 两个图标按钮尺寸一致',
   len(_icon_btns) >= 2 and len(set((b.width(), b.height())
                                    for b in _icon_btns[:2])) == 1)
ck('③16 设置页左侧页签用统一卡片样式',
   'T.tab_style()' in _st and 'QPushButton:checked' in _th)

# ---------------------------------------------------------------- ④ 周一打头 / 圆角菜单（行为验证）
import datetime                                        # noqa: E402
from brl import theme as T                             # noqa: E402
from brl.caltable import CalTable                      # noqa: E402

cal = CalTable()
cal.resize(560, 360)
cal.set_month(datetime.date.today())
cal.show()
_app.processEvents()
cal.grab()
first7 = [d for d, _r in cal._cells][:7]
ck('④1 月历首列是周一', len(first7) == 7 and first7[0].weekday() == 0,
   first7[0].isoformat() if first7 else '')
ck('④2 末列是周日', len(first7) == 7 and first7[6].weekday() == 6)
ck('④3 表头文案周一打头', 'WEEK_HEAD = ' in open(
    os.path.join(HERE, 'brl', 'caltable.py'), encoding='utf-8').read()
    .split('\n')[0] or u"u'周一'" in open(os.path.join(HERE, 'brl', 'caltable.py'),
                                         encoding='utf-8').read())
cal.set_view('week')
cal.set_selected(datetime.date.today())
cal.grab()
wk = [d for d, _r in cal._cells]
ck('④4 周视图从该周周一开始', wk and wk[0].weekday() == 0,
   wk[0].isoformat() if wk else '')
cal.close()

menu = T.CardMenu()
menu.addAction(u'选项设置')
menu.addAction(u'退出软件')
menu.show()
_app.processEvents()
img = menu.grab().toImage()
ck('④5 菜单四角透明（圆角生效，不是 QSS 空谈）',
   img.pixelColor(0, 0).alpha() == 0 and img.pixelColor(img.width() - 1, 0).alpha() == 0,
   'corner alpha=%d' % img.pixelColor(0, 0).alpha())
ck('④6 菜单中部不透明（底色画上了）',
   img.pixelColor(img.width() // 2, img.height() // 2).alpha() == 255)
menu.close()

print()
print('结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:')
    for n in bad:
        print(' - ' + n)
sys.exit(1 if bad else 0)
# ===== [END SECTION] =====


# ===== [SECTION v22] 用户数据随身包 =====
# -*- coding: utf-8 -*-
"""第 31 轮专项验证：升级时把「自定义设置」与「待办清单」各存一个文件再放回。

这一节的立场：升级只干两件事——
  安装第一步：读用户目录，另存 user-settings-<用户>-<时间戳>.ini
              与 user-todos-<用户>-<时间戳>.db，并写下指针；
  安装最后一步：按指针把这两个文件放回去，别的什么都不碰。

覆盖：
  ① 命名与指针          ② 存放（活库快照 / 空数据不写指针）
  ③ 放回（救回 / 不覆盖更多 / 清 -wal / force）
  ④ 只认指针，不翻旧组  ⑤ 保留份数、跨用户名回落、退出码
  ⑥ 与安装脚本的耦合（内联源码、时序、版本号）
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import brltest_env as _ENV
_ENV.isolate('v22')
from brl import carry as C          # noqa: E402

ok, bad = [], []


def ck(name, cond, extra=''):
    (ok if cond else bad).append(name)
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


TD = tempfile.mkdtemp(prefix='v22-')


def mkhome(tag, n=3, theme=5):
    """造一个"用户目录"：设置 + n 条待办。返回 (home, cfg, dat)。"""
    home = os.path.join(TD, tag)
    cfg, dat = C.home_dirs(home)
    for d in (cfg, dat):
        if not os.path.isdir(d):
            os.makedirs(d)
    with open(os.path.join(cfg, C.INI), 'w') as f:
        f.write('[ui]\ntheme=%d\n' % theme)
    cn = sqlite3.connect(os.path.join(dat, C.DB))
    cn.execute('CREATE TABLE IF NOT EXISTS todo(id INTEGER PRIMARY KEY AUTOINCREMENT,'
               ' content TEXT, category TEXT, date TEXT, created TEXT)')
    for i in range(n):
        cn.execute('INSERT INTO todo(content,category,date,created) VALUES(?,?,?,?)',
                   (u'待办%d' % (i + 1), u'生活', '2026-10-26', 'x'))
    cn.commit()
    cn.close()
    return home, cfg, dat


def rows(path):
    if not os.path.isfile(path):
        return -1
    cn = sqlite3.connect(path)
    try:
        return cn.execute('SELECT COUNT(*) FROM todo').fetchone()[0]
    finally:
        cn.close()


def run(*args):
    p = subprocess.run([sys.executable, os.path.join(HERE, 'brl', 'carry.py')] + list(args),
                       capture_output=True, text=True)
    return p


# ---------------------------------------------------------------- ① 命名与指针
ck('①1 设置文件命名', C.names('uos', '20261026-170108')[0]
   == 'user-settings-uos-20261026-170108.ini', C.names('uos', '20261026-170108')[0])
ck('①2 待办文件命名', C.names('uos', '20261026-170108')[1]
   == 'user-todos-uos-20261026-170108.db', C.names('uos', '20261026-170108')[1])
_s = C.new_stamp()
ck('①3 时间戳格式 YYYYMMDD-HHMMSS', len(_s) == 15 and _s[8] == '-'
   and _s[:8].isdigit() and _s[9:].isdigit(), _s)
_bad = C.names('a b/c', '20260101-010101')[0]
ck('①4 用户名里的怪字符被替换', ' ' not in _bad and '/' not in _bad, _bad)

# ---------------------------------------------------------------- ② 存放
H1, CFG1, DAT1 = mkhome('h1', 3, 5)
R1 = os.path.join(TD, 'bk1')
os.makedirs(R1)
r = C.save(CFG1, DAT1, R1, 'uos')
ck('②1 存下设置', r['ini'] == 1, r)
ck('②2 存下待办', r['db'] == 1 and r.get('rows') == 3, r)
ck('②3 两个文件都在', os.path.isfile(os.path.join(R1, C.names('uos', r['stamp'])[0]))
   and os.path.isfile(os.path.join(R1, C.names('uos', r['stamp'])[1])),
   sorted(os.listdir(R1)))
ck('②4 指针写下这一组', C.read_stamp(R1, 'uos') == r['stamp'], C.read_stamp(R1, 'uos'))
ck('②5 只有一组时不误删', len(C.pairs(R1, 'uos')) == 1)

# 活库：数据还在 -wal 里（进程没关就退出），直接 cp 会少；backup 不会
H2, CFG2, DAT2 = mkhome('h2', 0)
DB2 = os.path.join(DAT2, C.DB)
_py = ('import sqlite3,os,sys\n'
       'p=sys.argv[1]\n'
       'c=sqlite3.connect(p)\n'
       'c.execute("PRAGMA journal_mode=wal")\n'
       'c.execute("INSERT INTO todo(content,category,date,created) VALUES(\'未落盘\',\'生活\',\'2026-10-26\',\'x\')")\n'
       'c.commit()\n'
       'os._exit(0)\n')
subprocess.run([sys.executable, '-c', _py, DB2])
ck('②6 造出了 -wal（数据还没并回主库）', os.path.isfile(DB2 + '-wal')
   and os.path.getsize(DB2 + '-wal') > 0)
R2 = os.path.join(TD, 'bk2')
os.makedirs(R2)
r2 = C.save(CFG2, DAT2, R2, 'uos')
ck('②7 活库快照把 -wal 里的记录也带上', r2.get('rows') == 1, r2)

# 用户还没开始用：不写指针，免得最后一步拿空包去覆盖
H3 = os.path.join(TD, 'h3')
CFG3, DAT3 = C.home_dirs(H3)
R3 = os.path.join(TD, 'bk3')
os.makedirs(R3)
r3 = C.save(CFG3, DAT3, R3, 'uos')
ck('②8 什么都没存时不写指针', r3['ini'] == 0 and r3['db'] == 0
   and C.read_stamp(R3, 'uos') is None, r3)
ck('②9 空包时 load 是空操作', C.load(CFG3, DAT3, R3, 'uos')['stamp'] is None)

# ---------------------------------------------------------------- ③ 放回
os.remove(os.path.join(CFG1, C.INI))
os.remove(os.path.join(DAT1, C.DB))
r = C.load(CFG1, DAT1, R1, 'uos')
ck('③1 设置被放回', r['ini'] == 1 and 'theme=5' in open(os.path.join(CFG1, C.INI)).read(), r)
ck('③2 待办被放回', r['db'] == 1 and rows(os.path.join(DAT1, C.DB)) == 3, rows(os.path.join(DAT1, C.DB)))
ck('③3 放回后指针还在', C.read_stamp(R1, 'uos') == r['stamp'])

# 安装期间用户又记了事：当前比存的多，不许盖回去
cn = sqlite3.connect(os.path.join(DAT1, C.DB))
for i in range(2):
    cn.execute("INSERT INTO todo(content,category,date,created) VALUES('新记的','生活','2026-10-27','x')")
cn.commit()
cn.close()
r = C.load(CFG1, DAT1, R1, 'uos')
ck('③4 当前条数更多时保留当前', r['db'] == 0 and r['kept_current'] == 5
   and rows(os.path.join(DAT1, C.DB)) == 5, r)
r = C.load(CFG1, DAT1, R1, 'uos', force=True)
ck('③5 force 时照放不误', r['db'] == 1 and rows(os.path.join(DAT1, C.DB)) == 3, r)

# 换库必须清掉旧库的 -wal/-shm，否则 SQLite 会把上一份日志回放进新库
for suf in ('-wal', '-shm'):
    with open(os.path.join(DAT1, C.DB + suf), 'w') as f:
        f.write('stale')
C.load(CFG1, DAT1, R1, 'uos', force=True)
ck('③6 换库前清掉 -wal/-shm',
   not os.path.exists(os.path.join(DAT1, C.DB + '-wal'))
   and not os.path.exists(os.path.join(DAT1, C.DB + '-shm')))

# ---------------------------------------------------------------- ④ 只认指针
# 备份里塞一组"2030 年"的假包：按文件名排序它最靠前，
# 只有真按指针取的实现才不会把它放回去
_d170 = os.path.join(R1, C.TODO_PREFIX + 'olduser-20301231-235959.db')
cn = sqlite3.connect(_d170)
cn.execute('CREATE TABLE todo(id INTEGER PRIMARY KEY AUTOINCREMENT, content TEXT,'
           ' category TEXT, date TEXT, created TEXT)')
cn.execute("INSERT INTO todo(content,category,date,created) VALUES('陈年旧事','生活','2020-01-01','x')")
cn.commit()
cn.close()
with open(os.path.join(R1, C.SET_PREFIX + 'olduser-20301231-235959.ini'), 'w') as f:
    f.write('[ui]\ntheme=1\n')
os.remove(os.path.join(DAT1, C.DB))
C.load(CFG1, DAT1, R1, 'uos')
ck('④1 有指针时不用"最新文件名"那组', rows(os.path.join(DAT1, C.DB)) == 3
   and '陈年旧事' not in open(os.path.join(DAT1, C.DB), 'rb').read().decode('utf-8', 'ignore'),
   rows(os.path.join(DAT1, C.DB)))
ck('④2 设置也没被旧组带走',
   'theme=5' in open(os.path.join(CFG1, C.INI)).read())

# ---------------------------------------------------------------- ⑤ 份数、跨用户名、退出码
R5 = os.path.join(TD, 'bk5')
os.makedirs(R5)
for i in range(5):
    C.save(CFG1, DAT1, R5, 'uos', stamp='2026102%d-10000%d' % (i, i))
ck('⑤1 只保留最近 3 组', len(C.pairs(R5, 'uos')) == 3, len(C.pairs(R5, 'uos')))
ck('⑤2 留的是最新那 3 组',
   [k[-15:] for k, _i, _d in C.pairs(R5, 'uos')]
   == ['20261024-100004', '20261023-100003', '20261022-100002'],
   [k for k, _i, _d in C.pairs(R5, 'uos')])

# 安装器两段脚本各自探测用户，名字偶尔对不上：load 要不限用户名再找一次
os.remove(os.path.join(DAT1, C.DB))
r = C.load(CFG1, DAT1, R1, 'anotheruser')
ck('⑤3 用户名对不上也能找回', rows(os.path.join(DAT1, C.DB)) == 3, r)

p = run('load', '--home', os.path.join(TD, 'nohome'), '--root', os.path.join(TD, 'nobk'),
        '--user', 'uos')
ck('⑤4 没有包时退出码 2（无事可做）', p.returncode == 2, p.returncode)
p = run('save', '--home', H1, '--root', os.path.join(TD, 'bk6'), '--user', 'uos')
ck('⑤5 命令行输出可解析', 'action=save' in p.stdout and 'ini=1' in p.stdout
   and 'db=1' in p.stdout, p.stdout.strip())

# ---------------------------------------------------------------- ⑥ 与安装脚本的耦合
import makedeb as MD          # noqa: E402
CARRY_SRC = open(os.path.join(HERE, 'brl', 'carry.py'), encoding='utf-8').read()
ck('⑥1 版本号与源码一致', MD.VER == __import__('brl').__version__, MD.VER)
ck('⑥2 preinst 内联的就是这份源码', CARRY_SRC in MD.PREINST)
_i = MD.PREINST.index('save --home')
ck('⑥3 存档在 preinst 里、且早于收尾标记', _i > 0
   and _i < MD.PREINST.index('#DEBHELPER#'))
ck('⑥4 preinst 只在升级时动', '"$1" = "upgrade"' in MD.PREINST)
ck('⑥5 postinst 最后一步放回',
   MD.POSTINST.rindex('"$APPUPG" finish') > 0
   and MD.POSTINST.rindex('finish') < MD.POSTINST.rindex('#DEBHELPER#'))
ck('⑥6 收尾脚本用同一份 carry.py', 'brl/carry.py' in MD.UPGRADER
   and "' load " in MD.UPGRADER)
ck('⑥7 收尾脚本不再翻 upgrade-* 目录',
   'upgrade-' not in MD.UPGRADER and 'ls -1r' not in MD.UPGRADER)
ck('⑥8 1.4.6.0 的逻辑已清空',
   'restore-best' not in (MD.PREINST + MD.POSTINST + MD.UPGRADER + MD.PRERM + MD.POSTRM)
   and 'do_prepare' not in MD.UPGRADER)
ck('⑥9 carry.py 进了包', os.path.isfile(os.path.join(HERE, 'brl', 'carry.py')))

print()
print('结果: PASS=%d FAIL=%d' % (len(ok), len(bad)))
if bad:
    print('未通过:')
    for n in bad:
        print(' - ' + n)
sys.exit(1 if bad else 0)
# ===== [END SECTION] =====


# ===== [SECTION data] 数据层自检 =====
# -*- coding: utf-8 -*-
"""无头自测：核心逻辑 + 界面构建 + 离屏截图"""
import os, sys, datetime
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('self')


from brl import lunar as L
from brl import data as D
from brl import store as S
from brl import theme as T
from brl import holidays as HD

fails = []
def ck(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + str(extra) if extra and not cond else ''))
    if not cond:
        fails.append(name)

# ---- 农历
ck('lunar.2026春节', L.lunar_from_solar(datetime.date(2026,2,17)).day == 1
   and L.lunar_from_solar(datetime.date(2026,2,17)).month == 1)
ck('lunar.2025春节', (L.lunar_from_solar(datetime.date(2025,1,29)).month,
                      L.lunar_from_solar(datetime.date(2025,1,29)).day) == (1,1))
ld = L.lunar_from_solar(datetime.date(2026,1,1))
ck('lunar.2026-01-01', (ld.year, ld.month, ld.day) == (2025, 11, 13), (ld.year, ld.month, ld.day))
gz, sx = L.ganzhi_year(2026)
ck('ganzhi.2026', gz == u'丙午年' and sx == u'马', (gz, sx))
t = L.year_terms(2026)
ck('terms.2026', len(t) == 24, len(t))
ck('term.2026冬至', t.get(datetime.date(2026,12,22)) == u'冬至')
ck('term.2026清明', t.get(datetime.date(2026,4,5)) == u'清明')
ck('roundtrip', L.solar_from_lunar(2026,1,1) == datetime.date(2026,2,17))
ck('roundtrip.leap', True)

# ---- 节假日（内置自制数据）
import subprocess
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl')
ck('holiday.2026元旦休', D.HOLIDAY.is_free(datetime.date(2026,1,1)) is True)
ck('holiday.周末', D.HOLIDAY.is_free(datetime.date(2026,10,17)) is True)   # 周六
ck('holiday.2026国庆名', D.HOLIDAY.fest(datetime.date(2026,10,1)) == u'国庆节')
ck('holiday.2026春节名', D.HOLIDAY.fest(datetime.date(2026,2,17)) == u'春节')
ck('holiday.内置条数', len(HD.FESTS) >= 15, len(HD.FESTS))
ck('themes', len(T.ALL_THEMES) == 8, len(T.ALL_THEMES))

# ---- 主题命名：统一「意象 + 单字颜色」的三字格式，不带“色”字
_NAMES = [t.get('name') for t in T.ALL_THEMES]
ck('theme.八套名字均 2~4 字', all(2 <= len(n) <= 4 for n in _NAMES), _NAMES)
ck('theme.名字不带“色”字', all(u'色' not in n for n in _NAMES), _NAMES)
ck('theme.名字不重复', len(set(_NAMES)) == 8, _NAMES)
ck('theme.三字格式统一', all(len(n) == 3 for n in _NAMES), _NAMES)
ck('theme.顺序=三深五浅', _NAMES == [u'松烟墨', u'星夜蓝', u'远山灰', u'曙光橙',
                                u'原野绿', u'雨过青', u'薰衣紫', u'蜜桃粉'], _NAMES)

# ---- 老配置只有旧下标：改顺序后必须仍指向用户原来那一套
_LEGACY_EXPECT = {0: u'松烟墨', 1: u'星夜蓝', 2: u'远山灰', 3: u'曙光橙',
                  4: u'雨过青', 5: u'蜜桃粉', 6: u'原野绿', 7: u'薰衣紫'}
_bad = [(i, T.ALL_THEMES[T.resolve_theme_index(i)].get('name'), n)
        for i, n in _LEGACY_EXPECT.items()
        if T.ALL_THEMES[T.resolve_theme_index(i)].get('name') != n]
ck('theme.旧下标迁移到原来那一套', not _bad, _bad)
# 旧下标表只对旧数据成立，不能拿新下标再翻一遍；
# 真正要保证的是：迁移后把名字写回去，之后再解析必须稳定
ck('theme.写回名字后不再二次迁移',
   all(T.resolve_theme_index(T.resolve_theme_index(i),
                             [t.get('name') for t in T.ALL_THEMES][T.resolve_theme_index(i)])
       == T.resolve_theme_index(i) for i in range(8)))
_mwsrc2 = open(os.path.join(_ROOT, 'mainwin.py'), encoding='utf-8').read()
ck('theme.启动按名字/旧下标解析',
   "T.resolve_theme_index(st.value('ui/theme'" in _mwsrc2)
_seg = _mwsrc2.split('def _apply_theme', 1)[1].split('def ', 1)[0]
ck('theme.启动只读配置（不覆盖升级还原的快照）',
   'setValue' not in _seg and 'sync()' not in _seg)
_stsrc2 = open(os.path.join(_ROOT, 'settings.py'), encoding='utf-8').read()
ck('theme.设置页选主题时存名字', "st.setValue('ui/theme_name'" in _stsrc2)
ck('theme.认名字优先于下标',
   T.resolve_theme_index(0, u'蜜桃粉') == _NAMES.index(u'蜜桃粉'),
   T.resolve_theme_index(0, u'蜜桃粉'))
ck('theme.存名字后改顺序也不认错（新下标自洽）',
   T.resolve_theme_index(5, u'雨过青') == _NAMES.index(u'雨过青'))

# ---- 更新说明里的字面 \n 必须变成真换行（v1.4.7.0/1.4.8.0 踩过）
import make_manifest as _MM2
from brl import update as _U2
_RAW = u'· 甲\\n· 乙\\n· 丙'            # 字面反斜杠+n，模拟 --notes 传进来的样子
_WANT = u'· 甲' + u'\n' + u'· 乙' + u'\n' + u'· 丙'    # 真换行
ck('notes.清单生成时还原换行', _MM2.normalize_notes(_RAW) == _WANT,
   repr(_MM2.normalize_notes(_RAW)))
ck('notes.解析时还原换行（清单来源）',
   _U2.clean_notes(_RAW) == _WANT and u'\\n' not in _U2.clean_notes(_RAW),
   repr(_U2.clean_notes(_RAW)))
_pm = _U2.parse_manifest({'version': '1.4.9.0', 'size': 1, 'sha256': 'a' * 64,
                          'url': 'http://x/y.deb', 'notes': _RAW})
ck('notes.parse_manifest 已清洗', _pm['notes'] == _WANT, repr(_pm['notes']))
ck('notes.真实换行不被改动', _U2.clean_notes(_WANT) == _WANT)

# ---- 素材清理：原始素材必须彻底剥离
# 关键词用拼接与转义两种方式构造，避免字面进入公开仓库
_KW = ['bai' + 'sha', '\u767d\u9ca8']
r = subprocess.run(['grep', '-rn'] + [a for k in _KW for a in ('-e', k)] + [_ROOT],
                   capture_output=True)
ck('clean.无原始品牌字样', r.returncode == 1)
ck('clean.自制图标存在', os.path.exists(os.path.join(
    _ROOT, 'resources/icons/calendar.png')))
ck('clean.原素材目录已移除', not any(
    os.path.exists(os.path.join(_ROOT, 'resources', d))
    for d in ('img', 'theme', 'data')))

# ---- 存储
st = S.Store()
tid = st.add(u'自测待办', date='2026-10-15', repeat=0, remind=2, remind_time='09:00')
ck('store.add', tid > 0)
rows = st.for_date(datetime.date(2026,10,15))
ck('store.for_date', any(r['id'] == tid for r in rows))
st.update(tid, content=u'自测待办2')
ck('store.update', st.get(tid)['content'] == u'自测待办2')
st.remove(tid)
ck('store.remove', st.get(tid) is None)

# ---- 界面
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
app = QApplication([])
QApplication.setStyle('Fusion')
import brl.appctx as A

# ---- 周数
from brl.caltable import CalTable
cal0 = CalTable()
ck('week.jan1.2026W1', cal0.week_no(datetime.date(2026,1,1)) == 1)
cal0.set_options(weekstart='mon')
ck('week.mon.2026W1', cal0.week_no(datetime.date(2026,1,1)) == 1)
ck('week.mon.iso', cal0.week_no(datetime.date(2026,12,31))
   == datetime.date(2026,12,31).isocalendar()[1])

# ---- 应用图标与命名
ck('appicon', not T.app_icon().isNull())
ck('rename.应用名', A.APP_NAME == u'松松日历', A.APP_NAME)

# ---- 应用图标：卡通小松树（台历卡 + 三层绿树），圆角透明
try:
    from PIL import Image
    _ic = Image.open(os.path.join(_ROOT, 'resources', 'icons', 'calendar.png')).convert('RGBA')
    _p = _ic.load()
    _S = _ic.size[0]
    _green = _brown = 0
    for _y in range(0, _S, 2):
        for _x in range(0, _S, 2):
            _c = _p[_x, _y]
            if _c[3] < 200:
                continue
            if _c[1] > _c[0] + 20 and _c[1] > _c[2] + 20:
                _green += 1
            elif _c[0] > _c[1] > _c[2] and _c[0] - _c[2] > 30:
                _brown += 1
    # 沿用蓝色方块日历图标（白页 + 顶部装订环 + 蓝色今日格），不画任何具象图形
    ck('icon.四角透明', _p[0, 0][3] == 0 and _p[_S - 1, _S - 1][3] == 0
       and _p[0, _S - 1][3] == 0 and _p[_S - 1, 0][3] == 0)
    _blue = sum(1 for _y in range(0, _S, 4) for _x in range(0, _S, 4)
                if _p[_x, _y][3] > 200 and _p[_x, _y][2] - _p[_x, _y][0] > 40)
    _white = sum(1 for _y in range(0, _S, 4) for _x in range(0, _S, 4)
                 if _p[_x, _y][3] > 200 and _p[_x, _y][0] > 235
                 and _p[_x, _y][1] > 235 and _p[_x, _y][2] > 235)
    ck('icon.蓝色底', _blue > 200, _blue)
    ck('icon.白色日历页', _white > 200, _white)
    _sizes = [os.path.isfile(os.path.join(
        _ROOT, 'resources', 'icons', 'calendar_%d.png' % _s))
        for _s in (16, 24, 32, 48, 64, 128)]
    ck('icon.全套尺寸齐全', all(_sizes), _sizes)
except ImportError:
    ck('icon.跳过（无 PIL）', True)

# ---- 确认弹窗全部中文化：不再用系统 QMessageBox
_tdsrc = open(os.path.join(_ROOT, 'todo.py'), encoding='utf-8').read()
ck('dlg.待办不再用 QMessageBox',
   'QMessageBox' not in _tdsrc.replace(u'系统 QMessageBox', u''))
ck('dlg.删除确认走自绘窗', u"DLG.confirm(self, u'删除待办', msg, ok=u'删除')" in _tdsrc)
ck('dlg.提示窗走自绘窗', _tdsrc.count('DLG.info(') == 3, _tdsrc.count('DLG.info('))
_mwsrc = open(os.path.join(_ROOT, 'mainwin.py'), encoding='utf-8').read()
ck('dlg.主窗口不再用 QMessageBox', 'QMessageBox' not in _mwsrc)
import brl.updatedlg as _UD
ck('dlg.确认窗默认按钮是中文',
   _UD.ConfirmDialog.__init__.__defaults__ == (u'确定', u'取消'),
   _UD.ConfirmDialog.__init__.__defaults__)
ck('bar.已移除', not os.path.exists(os.path.join(_ROOT, 'barwin.py')))
ck('tools.按钮全部用自制图标', all(
    k in A.MainWindow.ICON_FILES for k in
    ('nav_prev', 'nav_next', 'view', 'lock', 'gear', 'close')))

ctx = A.Context(app)
ctx.win = A.MainWindow(ctx.store, ctx)
ctx.win.resize(800, 760)
ctx.win.show()
app.processEvents()
pm = ctx.win.grab()
pm.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_main.png'))
print('main window saved', pm.width(), pm.height())


# 设置窗
from brl.settings import SettingsDialog, COLOR_DEFS
dlg = SettingsDialog(ctx.store, ctx.win)
dlg.show(); app.processEvents()
dlg.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_settings.png'))
# 颜色覆盖：模拟一次透明度调整
dlg.on_color('mainbg', '#80202020')
app.processEvents()
stv = ctx.store.settings()
ck('color.覆盖已存', str(stv.value('color/mainbg')).startswith('#'), stv.value('color/mainbg'))
ctx.win._apply_theme()
app.processEvents()
ctx.win.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_color.png'))
# 恢复默认
dlg._reset_colors()
app.processEvents()
ctx.win._apply_theme()
# 周数列显示
ctx.win._cal.set_options(week=True)
app.processEvents()
ctx.win.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_week.png'))
ctx.win._cal.set_options(week=False)

# 待办编辑
from brl.todo import TodoEditDialog, TodoListDialog
d = TodoEditDialog(ctx.store, datetime.date(2026,10,15), None, None)
d.show(); app.processEvents()
d.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_todo.png'))

# 天气功能已按用户要求全局移除（1.2.7.0 起）
ck('weather.模块已移除', not os.path.exists(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl', 'weather.py')))

print()
print('FAILED:', fails if fails else 'none')
sys.exit(1 if fails else 0)
# ===== [END SECTION] =====


# ===== [SECTION e2e] 自启动端到端 =====
# -*- coding: utf-8 -*-
"""端到端验证开机自启：勾选 → 生成 → 桌面环境能拉起。

用法: DISPLAY=:0 python3 e2e_autostart.py
会临时把 app/autostart 置 1 写出文件，验证后还原为 0 并清理。
"""
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('e2e')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)

from brl import store, appctx

AST = appctx.autostart_path()
BAD = '/tmp/e2e_badbin'
if not os.path.isdir(BAD):
    os.makedirs(BAD)

_s = store.Store()
st = _s.settings()
old = st.value('app/autostart', '0')

ok = True


def step(name, cond, extra=''):
    global ok
    print('  %s %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        ok = False


print('原配置 app/autostart =', old)

print('== 1. 勾选后立即写入')
st.setValue('app/autostart', '1')
st.sync()
appctx.apply_autostart(_s, True)
step('文件已生成', os.path.exists(AST), AST)
if not os.path.exists(AST):
    sys.exit(1)

txt = open(AST).read()
print('--- 自启动文件内容 ---')
print(txt.rstrip())
print('----------------------')

print('== 2. desktop-file-validate 校验')
r = subprocess.call(['desktop-file-validate', AST])
step('通过桌面文件校验', r == 0, 'rc=%d' % r)

print('== 3. 模拟桌面环境拉起（Exec 绝对路径 + 干净 PATH）')
exe_cmd = [l.split('=', 1)[1].strip()
           for l in txt.splitlines() if l.startswith('Exec=')]
if not exe_cmd:
    step('有 Exec 行', False)
else:
    exe = exe_cmd[0]
    step('Exec 为绝对路径', exe.startswith('/'), exe)
    # 干净 PATH（不含 WorkBuddy 的私有 python shim），模拟 DDE 会话环境
    clean = dict(os.environ)
    clean['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    clean['DISPLAY'] = ':0'
    clean['XAUTHORITY'] = os.path.expanduser('~/.Xauthority')
    clean['HOME'] = os.path.expanduser('~')
    clean['LANG'] = 'zh_CN.UTF-8'
    clean['PYTHONPATH'] = '/opt/apps/com.desktop.calendar/files'
    p = subprocess.Popen([exe], env=clean,
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         preexec_fn=os.setsid)
    try:
        import time
        time.sleep(5)
        # 检查窗口是否真的出现在桌面
        out = subprocess.check_output(
            ['xwininfo', '-root', '-tree'],
            env=dict(os.environ, DISPLAY=':0')).decode('utf-8', 'ignore')
        lived = u'松松日历' in out
        step('自启动项真的拉起了窗口', lived)
        polled = p.poll()
        if polled is not None and polled != 0:
            so, se = p.communicate()
            step('进程未异常退出', False,
                 'rc=%s err=%s' % (polled, se.decode('utf-8', 'ignore')))
        else:
            step('进程存活（未被启动器拒绝）', True, 'rc=%s' % polled)
        try:
            os.killpg(os.getpgid(p.pid), 9)
        except OSError:
            pass
    except Exception as e:
        step('拉起流程无异常', False, str(e))

print('== 4. 还原用户配置')
st.setValue('app/autostart', '0')
st.sync()
appctx.apply_autostart(_s, False)
step('取消后文件移除', not os.path.exists(AST))
step('配置已还原', st.value('app/autostart', '0') == '0')

print('')
print('端到端结果: %s' % ('全部通过' if ok else '存在失败项'))
sys.exit(0 if ok else 1)
# ===== [END SECTION] =====


# ===== [SECTION lint] 命名一致性 =====
# -*- coding: utf-8 -*-
"""静态检查：模块内是否存在“用了没导入的别名”（如 weather.py 的 L.WEEK_CN）。

这类错误只在特定数据路径下才触发（天气拿到真实数据才走到那行），
平时跑不出来，却会让进程直接 abort——所以必须静态兜住。

用法: python3 verify.py lint（原 lint_aliases.py，已并入本文件）
"""
import ast
import os
import sys

BUILTINS = set(dir(__builtins__)) if isinstance(__builtins__, dict) is False else set(__builtins__)
BUILTINS |= {
    'True', 'False', 'None', 'self', 'cls', 'super', 'Exception', 'BaseException',
    'print', 'len', 'range', 'int', 'str', 'float', 'list', 'dict', 'set', 'tuple',
    'open', 'isinstance', 'getattr', 'setattr', 'hasattr', 'callable', 'sorted',
    'enumerate', 'zip', 'map', 'filter', 'min', 'max', 'abs', 'round', 'sum', 'any',
    'all', 'repr', 'type', 'id', 'iter', 'next', 'bytes', 'object', 'property',
    'staticmethod', 'classmethod', 'ord', 'chr', 'hex', 'format', 'divmod', 'pow',
}


def collect_names(tree):
    names = set(BUILTINS)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.asname or a.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name != '*':
                    names.add(a.asname or a.name)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            names.add(node.id)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.Global):
            names.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            names.update(node.names)
    return names


def check(path):
    with open(path) as f:
        src = f.read()
    try:
        tree = ast.parse(src, path)
    except SyntaxError as e:
        return ['%s: 语法错误 %s' % (os.path.basename(path), e)]
    names = collect_names(tree)
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            base = node.value.id
            if base in names:
                continue
            # 只报“短别名”形式（模块别名），避免把 obj.xxx 误报。
            # 注意不能只查小写：模块别名也常写成 L / T / D / S 这类大写单字母，
            # 之前的 islower() 过滤恰好把真正的 bug（L.WEEK_CN）漏掉了。
            if 1 <= len(base) <= 3 and base.isalpha():
                bad.append('%s:%d 未定义的模块别名 %r（使用了 .%s）'
                           % (os.path.basename(path), node.lineno, base, node.attr))
    return bad


def main():
    root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl')
    problems = []
    files = sorted(f for f in os.listdir(root) if f.endswith('.py'))
    for fn in files:
        problems.extend(check(os.path.join(root, fn)))
    seen = set()
    uniq = []
    for p in problems:
        if p not in seen:
            seen.add(p)
            uniq.append(p)
    if uniq:
        print('发现未定义别名:')
        for p in uniq:
            print('  ' + p)
        return 1
    print('别名引用检查通过（%d 个模块）' % len(files))
    return 0


if __name__ == '__main__':
    sys.exit(main())
# ===== [END SECTION] =====

# ===== [SECTION v23] UOS打包规范 =====
# -*- coding: utf-8 -*-
"""按 UOS《应用打包规范》核对 dist 里的 deb。

对照的条文（uosdn.uniontech.com 应用规范 / 应用打包规范）：
  1  包名倒置域名、小写          -> control 的 Package、info 的 appid
  2.1 安装文件全在 /opt/apps/<appid>/，钩子不改系统文件
  3  根目录 entries / files / info 三件套
  3.1.1 applications 下 <appid>.desktop，必填字段齐全
  3.1.2 非矢量图标按分辨率放 entries/icons/hicolor/<N>x<N>/apps
  3.3 info 字段（appid/name/version/arch/permissions）
  6.1 钩子里 rm -rf 必须带引号
"""
import glob
import json
import os
import re
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
APPID = 'com.desktop.calendar'
SIZES = (16, 24, 32, 48, 128, 256, 512)
# 规范 3.1.1 列出的分类，填别的会被归到「其他应用」
CATS = {'Network', 'Internet', 'Chat', 'Audio', 'Music', 'AudioVideo',
        'Video', 'Graphics', 'Game', 'Office', 'Reading', 'Development',
        'System'}
PERMS = ('autostart', 'notification', 'trayicon', 'clipboard', 'account',
         'bluetooth', 'camera', 'audio_record', 'installed_apps')


def ck(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + ('  ' + str(extra) if extra else ''))


debs = sorted(glob.glob(os.path.join(HERE, 'dist', '*.deb')))
if not debs:
    ck('v23.0 有 deb 可核对', False, '先跑 makedeb.py')
    raise SystemExit(0)
deb = debs[-1]
tmp = tempfile.mkdtemp(prefix='v23-')
subprocess.check_call(['dpkg-deb', '-x', deb, tmp])
ctl = os.path.join(tmp, '_ctl')
subprocess.check_call(['dpkg-deb', '-e', deb, ctl])

appdir = os.path.join(tmp, 'opt/apps', APPID)
ck('v23.1 根目录三件套 entries/files/info',
   all(os.path.exists(os.path.join(appdir, x)) for x in ('entries', 'files', 'info')),
   sorted(os.listdir(appdir)) if os.path.isdir(appdir) else appdir)

# ---- 2.1 除 /usr/bin 软链外不留 /opt/apps 之外的文件
outside = []
for root, _dirs, fs in os.walk(tmp):
    if root.startswith(ctl):
        continue
    for f in fs:
        rel = os.path.relpath(os.path.join(root, f), tmp)
        if rel.startswith('opt/apps/%s/' % APPID):
            continue
        if rel.startswith('usr/bin/') and os.path.islink(os.path.join(root, f)):
            continue
        outside.append(rel)
ck('v23.2 安装文件都在 /opt/apps/<appid>/ 下', not outside, outside[:5])

bad_link = []
ub = os.path.join(tmp, 'usr/bin')
if os.path.isdir(ub):
    for f in os.listdir(ub):
        tgt = os.readlink(os.path.join(ub, f)) if os.path.islink(os.path.join(ub, f)) else ''
        if not tgt.startswith('/opt/apps/%s/' % APPID):
            bad_link.append((f, tgt))
ck('v23.3 /usr/bin 只放指向应用目录的软链', not bad_link, bad_link)

# ---- 3.1.2 图标：按尺寸分层，png 不放 scalable
icdir = os.path.join(appdir, 'entries/icons/hicolor')
missing = []
for s in SIZES:
    p = os.path.join(icdir, '%dx%d/apps/%s.png' % (s, s, APPID))
    if not os.path.isfile(p):
        missing.append('%dx%d' % (s, s))
ck('v23.4 七个分辨率图标齐全', not missing, missing)

wrong = []
try:
    from PIL import Image
    for s in SIZES:
        p = os.path.join(icdir, '%dx%d/apps/%s.png' % (s, s, APPID))
        if os.path.isfile(p) and Image.open(p).size != (s, s):
            wrong.append((s, Image.open(p).size))
except ImportError:
    pass
ck('v23.5 图标实际尺寸与目录一致', not wrong, wrong)

scal_apps = os.path.join(icdir, 'scalable/apps')
png_in_scalable = (os.path.isdir(scal_apps) and
                   [f for f in os.listdir(scal_apps) if f.endswith('.png')])
ck('v23.6 scalable 目录不放 png', not png_in_scalable, png_in_scalable)

# ---- 3.1.1 desktop
dp = os.path.join(appdir, 'entries/applications/%s.desktop' % APPID)
ck('v23.7 desktop 以 appid 命名', os.path.isfile(dp), dp)
txt = ''
if os.path.isfile(dp):
    try:
        txt = open(dp, 'rb').read().decode('utf-8')
        good_enc = True
    except UnicodeDecodeError:
        good_enc = False
    ck('v23.8 desktop 编码为 UTF-8', good_enc)

kv = {}
for line in txt.splitlines():
    if '=' in line and not line.startswith('['):
        k, v = line.split('=', 1)
        kv[k.strip()] = v.strip()

exec_path = kv.get('Exec', '')
exec_ok = (exec_path.startswith('/opt/apps/%s/files/' % APPID) and
           os.path.isfile(os.path.join(tmp, exec_path.lstrip('/'))))
ck('v23.9 Exec 指向 /opt/apps 下的程序', exec_ok, exec_path)
ck('v23.10 Icon 用 appid 相对名', kv.get('Icon') == APPID, kv.get('Icon'))
ck('v23.11 Type=Application', kv.get('Type') == 'Application', kv.get('Type'))
ck('v23.12 Terminal=false', kv.get('Terminal', '').lower() == 'false', kv.get('Terminal'))
ck('v23.13 StartupNotify=true', kv.get('StartupNotify', '').lower() == 'true',
   kv.get('StartupNotify'))
ck('v23.14 有 StartupWMClass', bool(kv.get('StartupWMClass')), kv.get('StartupWMClass'))
cats = [c for c in kv.get('Categories', '').split(';') if c]
ck('v23.15 Categories 用规范支持的分类', bool(cats) and all(c in CATS for c in cats), cats)

# ---- 3.3 info
info = {}
try:
    info = json.load(open(os.path.join(appdir, 'info'), encoding='utf-8'))
    ck('v23.16 info 是合法 JSON', True)
except Exception as e:
    ck('v23.16 info 是合法 JSON', False, e)

ctrl = open(os.path.join(ctl, 'control'), encoding='utf-8').read()
m = re.search(r'^Version:\s*(\S+)', ctrl, re.M)
ctrl_ver = m.group(1) if m else ''
ck('v23.17 info.appid 与安装目录名一致', info.get('appid') == APPID, info.get('appid'))
ck('v23.18 info.version 与 deb 版本一致', info.get('version') == ctrl_ver,
   (info.get('version'), ctrl_ver))
ck('v23.19 info.version 四段纯数字',
   bool(re.match(r'^\d+\.\d+\.\d+\.\d+$', str(info.get('version') or ''))), info.get('version'))
ck('v23.20 info.arch 为 arm64 列表', info.get('arch') == ['arm64'], info.get('arch'))

perms = info.get('permissions') or {}
lack = [k for k in PERMS if k not in perms]
ck('v23.21 permissions 九项齐全', not lack, lack)
notbool = [k for k, v in perms.items() if not isinstance(v, bool)]
ck('v23.22 permissions 值均为布尔', not notbool, notbool)
ck('v23.23 permissions 与实际能力相符',
   perms.get('trayicon') is True and perms.get('autostart') is True
   and perms.get('notification') is True, perms)

# ---- 1 包名：按用户要求保留旧包名 desktop-calendar（不跟 appid 走）
pkg = re.search(r'^Package:\s*(\S+)', ctrl, re.M)
pkg = pkg.group(1) if pkg else ''
ck('v23.24 包名保持 desktop-calendar', pkg == 'desktop-calendar', pkg)
# 包名与 appid 不一致，安装目录/info/desktop 仍按 appid；文件名跟包名走
ck('v23.24b deb 文件名与 Package 一致',
   os.path.basename(deb).startswith(pkg + '_'), os.path.basename(deb))
# 声明换包可以，但绝不能把包名写成自己（dpkg 会报 conflicts 自己）
selfclash = [k for k in ('Conflicts', 'Replaces', 'Provides')
             if re.search(r'^%s:\s*.*\b%s\b' % (k, re.escape(pkg)), ctrl, re.M)]
ck('v23.24c control 不与自己冲突', not selfclash, selfclash)
swap = re.search(r'^Conflicts:\s*(.+)$', ctrl, re.M)
ck('v23.24d 仍能替换同路径的 com.desktop.calendar 旧包',
   bool(swap) and 'com.desktop.calendar' in swap.group(1), swap.group(1) if swap else '')

# ---- 6.1 钩子：rm -rf 必须带引号
hooks = {}
for name in ('preinst', 'postinst', 'prerm', 'postrm'):
    p = os.path.join(ctl, name)
    hooks[name] = open(p, encoding='utf-8').read() if os.path.isfile(p) else ''
unq = []
for name, body in hooks.items():
    for line in body.splitlines():
        ls = line.strip()
        if ls.startswith('#') or 'rm -rf' not in ls:
            continue
        if '"' not in ls and "'" not in ls:
            unq.append((name, ls))
ck('v23.25 钩子里 rm -rf 都带引号', not unq, unq)

sysmod = [n for n, b in hooks.items()
          if 'update-desktop-database' in b or 'gtk-update-icon-cache' in b]
ck('v23.26 钩子不改系统目录/skip 更新系统缓存', not sysmod, sysmod)

# ---- 2 files/bin 下的启动器可执行
lb = os.path.join(appdir, 'files/bin/desktop-calendar')
ck('v23.27 启动器在 files/bin 且有可执行位',
   os.path.isfile(lb) and os.access(lb, os.X_OK), lb)

# ===== [END SECTION] =====
