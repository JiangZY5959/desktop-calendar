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

# 全部不可达 -> 报错
U.API_HOSTS = ('http://127.0.0.1:1/unreachable',)
try:
    U.fetch_manifest()
    ck('③.全挂时抛 UpdateError', False)
except U.UpdateError:
    ck('③.全挂时抛 UpdateError', True)
U.API_HOSTS = _real_hosts
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

msgs = {'info': [], 'warn': [], 'q': []}
UD.QMessageBox.information = lambda *a, **k: msgs['info'].append(a)
UD.QMessageBox.warning = lambda *a, **k: msgs['warn'].append(a)
UD.QMessageBox.question = lambda *a, **k: (msgs['q'].append(a), QMessageBox.No)[1]
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
ck('⑧.提示已启动安装程序', len(msgs['info']) == 1 and u'已启动' in str(msgs['info'][0]),
   msgs['info'])
ck('⑧.下载文件校验通过', os.path.exists(os.path.join(updir, 't_9.9.9.9.deb')))

# --- 8.2 安装包已在本地且校验通过 -> 直接安装不再下载
spawned[:] = []
msgs['info'][:] = []
flow2 = UpdateFlow(ctx.store, w)
flow2._parent = w
flow2._download(dict(SRV['manifest']))
ck('⑧.已有安装包直接安装', bool(spawned) and not msgs['warn'], (spawned, msgs['warn']))

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
ck('⑨.手动检查失败有提示', len(msgs['warn']) >= 1, msgs['warn'])

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
