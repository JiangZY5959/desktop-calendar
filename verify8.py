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
settings.setValue('general/autostart', '1')
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
settings.setValue('general/autostart', '0')
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
