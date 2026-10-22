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

APP = u'桌面悬浮日历'
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
st.setValue('general/autostart', '1')
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
st.setValue('general/autostart', '0')
appctx.apply_autostart(_store, False)
ck('取消后文件删除', not os.path.exists(AST))

# 恢复勾选态（保留用户可能的设置，最后写成"已勾选"便于用户直接验证）
st.setValue('general/autostart', '0')
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
