# -*- coding: utf-8 -*-
"""端到端验证开机自启：勾选 → 生成 → 桌面环境能拉起。

用法: DISPLAY=:0 python3 e2e_autostart.py
会临时把 general/autostart 置 1 写出文件，验证后还原为 0 并清理。
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
old = st.value('general/autostart', '0')

ok = True


def step(name, cond, extra=''):
    global ok
    print('  %s %s %s' % ('PASS' if cond else 'FAIL', name, extra))
    if not cond:
        ok = False


print('原配置 general/autostart =', old)

print('== 1. 勾选后立即写入')
st.setValue('general/autostart', '1')
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
        lived = u'桌面悬浮日历' in out
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
st.setValue('general/autostart', '0')
st.sync()
appctx.apply_autostart(_s, False)
step('取消后文件移除', not os.path.exists(AST))
step('配置已还原', st.value('general/autostart', '0') == '0')

print('')
print('端到端结果: %s' % ('全部通过' if ok else '存在失败项'))
sys.exit(0 if ok else 1)
