# -*- coding: utf-8 -*-
"""检查更新（数据源：GitCode 公开仓库）—— 只用标准库，不引入第三方依赖。

流程
----
1. 读仓库里的 ``releases/latest.json``：GitCode 的 contents API 会把小文件
   以 base64 直接返回，一次请求即可拿到清单；
2. 版本号按 ``x.y.z.w`` 逐段比较，比当前新才提示；
3. 用户确认后下载 deb（带进度回调），校验体积 / ar 包头 / sha256；
4. 交给系统安装：优先 UOS 自带的 deepin-deb-installer，其次 pkexec apt-get。

清单由 ``make_manifest.py`` 生成。清单里的下载地址用的是仓库 blob 直链
``raw.gitcode.com/<owner>/<repo>/blobs/<blob-sha>/<path>``——blob sha 只取决于
文件内容，可以本地用 ``git hash-object`` 预先算出来，所以客户端不必再查一次
接口就能直接下载。

本模块所有函数都不依赖 Qt，便于命令行自检（``desktop-calendar --check-update``）。
"""
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from . import __version__ as APP_VER

# ---------------------------------------------------------------- 仓库信息
OWNER = 'gcw_6ciOFeue'
REPO = 'desktop-calendar'
BRANCH = 'master'
MANIFEST = 'releases/latest.json'
PAGE = 'https://gitcode.com/%s/%s' % (OWNER, REPO)
BLOB_URL = 'https://raw.gitcode.com/%s/%s/blobs/%%s/%%s' % (OWNER, REPO)
# 两个域名的接口互为备份：api.gitcode.com 有时会被限流，主站接口通常还在
API_HOSTS = ('https://api.gitcode.com/api/v5', 'https://gitcode.com/api/v5')
# 清单的 raw 直链：走文件 CDN，不经过 API，因此不会被接口限流（429）波及。
# 接口频繁 429 时这条就是主力，接口退居兜底。
RAW_MANIFEST = ('https://raw.gitcode.com/%s/%s/raw/%s/%s'
                % (OWNER, REPO, BRANCH, MANIFEST))

# 应用商店（2026-10 起已上架 UOS 商店）：新版本交给商店更新，
# 不再自己下载 deb 覆盖安装——自己 dpkg 会让商店里的版本记录对不上。
STORE_APPID = 'desktop-calendar'                       # 商店里的包名
STORE_CLIENT = 'deepin-home-appstore-client'
STORE_BUS = 'com.home.appstore.client'
STORE_PATH = '/com/home/appstore/client'
STORE_SERVICE = '/usr/share/dbus-1/services/com.home.appstore.client.service'
# 官方支持的两个业务 URI 之一：app_detail_info/<包名> 直接落到应用详情页
STORE_URI = ('appstore://%s?app_detail_info/%s'
             % (STORE_CLIENT, STORE_APPID))

TIMEOUT = 10           # 短请求（清单 / 版本）
DL_TIMEOUT = 30        # 下载时单次读阻塞上限
CHUNK = 64 * 1024

# 检查失败后的退避：接口临时限流时别每小时都去撞一次
FAIL_BACKOFF = 6 * 3600

DEB_TMPL = 'desktop-calendar_%s_arm64.deb'   # 包名_版本_架构


class UpdateError(Exception):
    """检查 / 下载 / 安装过程中的可展示错误。

    ``code`` 是 HTTP 状态码（0 表示网络层错误），``detail`` 只进日志、
    不往用户界面上贴——之前把两个接口的原始异常拼成一句话弹出来，
    用户看到的是 "HTTP 429（https://api.gitcode.com/…）" 这种天书。
    """

    def __init__(self, msg, code=0, detail=''):
        Exception.__init__(self, msg)
        self.code = code
        self.detail = detail or msg


class RateLimited(UpdateError):
    """被接口限流（HTTP 429）。"""

    def __init__(self, detail=''):
        UpdateError.__init__(self, u'更新服务器暂时繁忙，请稍后再试', 429, detail)



class Cancelled(Exception):
    """用户取消下载。"""


# ---------------------------------------------------------------- 版本比较
def ver_tuple(s):
    """'v1.4.0.0' / '1.4' / '1.4.0.0-beta' -> (1, 4, 0, 0)"""
    s = str(s or '').strip()
    if s[:1] in ('v', 'V'):
        s = s[1:]
    nums = re.findall(r'\d+', s)
    if not nums:
        return (0, 0, 0, 0)
    out = [int(n) for n in nums[:4]]
    while len(out) < 4:
        out.append(0)
    return tuple(out)


def is_newer(remote, local):
    """远端版本是否比本地新（相等或更旧都返回 False）"""
    return ver_tuple(remote) > ver_tuple(local)


def ver_text(t):
    return '.'.join(str(x) for x in t)


# ---------------------------------------------------------------- 检查周期
# (键, 显示名, 间隔天数)；0 = 不自动检查
MODE_DAYS = [
    ('daily', u'每天检查一次', 1),
    ('weekly', u'每周检查一次', 7),
    ('monthly', u'每月检查一次', 30),
    ('manual', u'仅手动检查', 0),
]
MODE_DEFAULT = 'daily'
MODE_LABEL = dict((k, name) for k, name, _d in MODE_DAYS)


def mode_days(mode):
    for k, _name, days in MODE_DAYS:
        if k == mode:
            return days
    return MODE_DAYS[0][2]


def due(mode, last_ts, now_ts=None):
    """按检查周期判断现在该不该自动检查。"""
    days = mode_days(mode)
    if days <= 0:
        return False
    if not last_ts:
        return True
    import time
    now_ts = time.time() if now_ts is None else now_ts
    try:
        return (now_ts - float(last_ts)) >= days * 86400
    except (TypeError, ValueError):
        return True


# ---------------------------------------------------------------- HTTP
def _headers(accept='application/json, */*'):
    return {'User-Agent': 'desktop-calendar/%s (+%s)' % (APP_VER, PAGE),
            'Accept': accept}


def _get(url, timeout=TIMEOUT, accept='application/json, */*'):
    req = urllib.request.Request(url, headers=_headers(accept))
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        # 429 = 接口限流：这是最常见的一种，单独给它一句人话，
        # 不再把 URL 塞到界面上
        if e.code == 429:
            raise RateLimited(u'HTTP 429 %s' % url.split('?')[0])
        raise UpdateError(u'更新服务器返回错误（HTTP %s）' % e.code,
                          e.code, url.split('?')[0])
    except Exception as e:
        raise UpdateError(u'连不上更新服务器，请检查网络后重试', 0, str(e))
    try:
        return r.read()
    finally:
        try:
            r.close()
        except Exception:
            pass


def _decode_api_content(j):
    """contents 接口的返回 -> 文件字节（base64 内联 / 明文 / download_url）"""
    content = j.get('content') or ''
    enc = str(j.get('encoding') or '').lower()
    if content:
        if enc == 'base64':
            return base64.b64decode(content.encode('utf-8'))
        if isinstance(content, bytes):
            return content
        return content.encode('utf-8')
    du = j.get('download_url')
    if du:
        return _get(du)
    raise UpdateError(u'清单内容为空')


def clean_notes(s):
    """把更新说明里的字面 '\\n'（反斜杠 + n）还原成真换行。

    --notes "a\nb" 这种写法传进清单的是两个字符，弹窗原样显示就会
    看到 \n 本身，所以解析时统一规整一次。
    """
    if not s:
        return ''
    s = str(s).replace('\\r\\n', '\n').replace('\\n', '\n')
    s = s.replace('\r\n', '\n').replace('\r', '\n')
    lines = [ln.rstrip() for ln in s.split('\n')]
    return '\n'.join(lines).strip('\n')


def parse_manifest(d):
    """把 latest.json 字典规整成固定字段；字段缺失也能工作。"""
    if not isinstance(d, dict):
        raise UpdateError(u'版本清单格式不正确')
    ver = str(d.get('version') or d.get('tag') or '').strip()
    if ver[:1] in ('v', 'V'):
        ver = ver[1:]
    if not ver_tuple(ver) > (0, 0, 0, 0):
        raise UpdateError(u'版本清单里没有可用的版本号')
    out = {
        'version': ver,
        'tag': str(d.get('tag') or ('v' + ver)),
        'file': str(d.get('file') or (DEB_TMPL % ver)),
        'notes': clean_notes(d.get('notes')),
        'size': int(d.get('size') or 0),
        'sha256': str(d.get('sha256') or '').lower(),
        'url': str(d.get('url') or ''),
        'released': str(d.get('released') or ''),
        'source': 'manifest',
    }
    return out


def _from_release(timeout=TIMEOUT):
    """兜底：没有清单 / 清单读不到时，用 Release 或 Tag 定版本。"""
    for host in API_HOSTS:
        try:
            j = json.loads(_get('%s/repos/%s/%s/releases/latest'
                                % (host, OWNER, REPO), timeout).decode('utf-8'))
            tag = str(j.get('tag_name') or j.get('name') or '')
            if tag:
                ver = tag[1:] if tag[:1] in ('v', 'V') else tag
                return {'version': ver, 'tag': tag,
                        'file': DEB_TMPL % ver,
                        'notes': clean_notes(j.get('body')),
                        'size': 0, 'sha256': '', 'url': '',
                        'released': str(j.get('created_at') or '')[:10],
                        'source': 'release'}
        except Exception:
            continue
    for host in API_HOSTS:
        try:
            arr = json.loads(_get('%s/repos/%s/%s/tags'
                                  % (host, OWNER, REPO), timeout).decode('utf-8'))
            if not isinstance(arr, list):
                continue
            tags = [str(t.get('name') or '') for t in arr if isinstance(t, dict)]
            tags = [t for t in tags if ver_tuple(t) > (0, 0, 0, 0)]
            if not tags:
                continue
            tags.sort(key=ver_tuple)
            tag = tags[-1]
            ver = tag[1:] if tag[:1] in ('v', 'V') else tag
            return {'version': ver, 'tag': tag, 'file': DEB_TMPL % ver,
                    'notes': '', 'size': 0, 'sha256': '', 'url': '',
                    'released': '', 'source': 'tag'}
        except Exception:
            continue
    raise UpdateError(u'读取版本信息失败')


def _from_raw(timeout=TIMEOUT):
    """清单的 raw 直链（走文件 CDN，不经过 API，因此不受接口限流影响）。"""
    body = _get(RAW_MANIFEST, timeout, accept='application/json, text/plain, */*')
    txt = body.decode('utf-8', 'replace').lstrip()
    if txt[:1] != '{':
        # 分支或路径不对时，CDN 会回一个 HTML 页面，当作读不到处理
        raise UpdateError(u'清单不是 JSON', 0, txt[:120])
    m = parse_manifest(json.loads(txt))
    m['source'] = 'raw'
    return m


def fetch_manifest(timeout=TIMEOUT):
    """读版本清单。返回 parse_manifest() 的字典，失败抛 UpdateError。

    顺序：raw 直链 -> 两个接口 -> Release/Tag 兜底。
    raw 放第一位，是因为接口会限流（HTTP 429），而文件 CDN 不会。
    """
    errs = []          # 给日志看
    objs = []          # 给"到底是哪一种失败"判断用
    try:
        return _from_raw(timeout)
    except Exception as e:
        errs.append(u'raw -> %s' % getattr(e, 'detail', e))
        objs.append(e)
    for host in API_HOSTS:
        url = '%s/repos/%s/%s/contents/%s?ref=%s' % (host, OWNER, REPO,
                                                      MANIFEST, BRANCH)
        try:
            j = json.loads(_get(url, timeout).decode('utf-8'))
            m = parse_manifest(json.loads(_decode_api_content(j).decode('utf-8')))
            m['source'] = url
            return m
        except Exception as e:
            errs.append(u'%s -> %s' % (host.split('//')[-1].split('/')[0],
                                       getattr(e, 'detail', e)))
            objs.append(e)
    try:
        return _from_release(timeout)
    except Exception as e:
        errs.append(u'release -> %s' % e)
        objs.append(e)
    # 有一路是 429 就按"服务器忙"处理：这时说"读不到版本信息"会让人
    # 以为是自己网络坏了，实际上是被限流，等一会儿就好
    codes = [getattr(e, 'code', 0) for e in objs]
    if 429 in codes:
        raise RateLimited(u'；'.join(errs))
    raise UpdateError(u'读取版本信息失败，请稍后再试', 0, u'；'.join(errs))


def resolve_url(manifest, timeout=TIMEOUT):
    """定位 deb 下载地址：清单自带的 blob 直链优先，其次现查 contents 接口。"""
    url = str(manifest.get('url') or '')
    if url:
        return url
    path = 'releases/' + str(manifest.get('file') or '')
    for host in API_HOSTS:
        try:
            j = json.loads(_get('%s/repos/%s/%s/contents/%s?ref=%s'
                                % (host, OWNER, REPO, path, BRANCH),
                                timeout).decode('utf-8'))
            du = str(j.get('download_url') or '')
            if du:
                return du
        except Exception:
            continue
    raise UpdateError(u'找不到安装包的下载地址')


# ---------------------------------------------------------------- 下载 / 校验
def download(url, dest, total_hint=0, on_progress=None, cancelled=None,
             timeout=DL_TIMEOUT):
    """流式下载到 dest（先写 .part 再改名）。返回 (字节数, 总字节数)。

    on_progress(read, total) 在工作线程里调用；cancelled() 返回 True 则中止。
    """
    tmp = dest + '.part'
    d = os.path.dirname(dest)
    if d and not os.path.isdir(d):
        try:
            os.makedirs(d)
        except OSError:
            pass
    req = urllib.request.Request(url, headers=_headers('application/octet-stream, */*'))
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.HTTPError as e:
        raise UpdateError(u'下载失败：HTTP %s' % e.code)
    except Exception as e:
        raise UpdateError(u'下载失败：%s' % (e,))
    total = 0
    try:
        total = int(r.headers.get('Content-Length') or 0)
    except Exception:
        total = 0
    if not total:
        total = int(total_hint or 0)
    got = 0
    try:
        f = open(tmp, 'wb')
    except OSError as e:
        raise UpdateError(u'无法写入下载目录：%s' % (e,))
    try:
        while True:
            if cancelled is not None and cancelled():
                raise Cancelled()
            chunk = r.read(CHUNK)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if on_progress is not None:
                on_progress(got, total)
        f.flush()
        os.fsync(f.fileno())
    finally:
        f.close()
        try:
            r.close()
        except Exception:
            pass
    if cancelled is not None and cancelled():
        _safe_remove(tmp)
        raise Cancelled()
    if total and got != total:
        _safe_remove(tmp)
        raise UpdateError(u'下载不完整（%d/%d 字节）' % (got, total))
    try:
        os.replace(tmp, dest)
    except OSError as e:
        _safe_remove(tmp)
        raise UpdateError(u'保存安装包失败：%s' % (e,))
    return got, total


def _safe_remove(p):
    try:
        if os.path.exists(p):
            os.remove(p)
    except OSError:
        pass


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def verify_deb(path, size=0, sha256=''):
    """安装前自检：体积、ar 包头、sha256。返回 (ok, 说明)。"""
    if not os.path.exists(path):
        return False, u'安装包不存在'
    real = os.path.getsize(path)
    if size and real != int(size):
        return False, u'安装包体积不符（%d ≠ %d）' % (real, int(size))
    try:
        with open(path, 'rb') as f:
            magic = f.read(8)
    except OSError as e:
        return False, u'读不到安装包：%s' % (e,)
    if not magic.startswith(b'!<arch>'):
        return False, u'下载到的不是有效的 deb 安装包'
    if sha256:
        got = sha256_file(path)
        if got.lower() != str(sha256).lower():
            return False, u'安装包校验失败（sha256 不匹配）'
    return True, u'校验通过'


# ---------------------------------------------------------------- 安装
def _which(name):
    for d in (os.environ.get('PATH') or '/usr/bin:/bin:/usr/sbin:/sbin').split(os.pathsep):
        p = os.path.join(d, name)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return ''


def installer_plan(path):
    """给出可用的安装方式列表：[(kind, argv, 说明)]，kind ∈ {'gui','cli'}。

    gui = 交给系统图形安装器，装完要用户自己点；cli = 我们等它跑完。
    """
    path = os.path.abspath(path)
    plan = []
    debi = _which('deepin-deb-installer')
    if debi:
        plan.append(('gui', [debi, path], u'系统软件包安装器'))
    pk = _which('pkexec')
    if pk and _which('apt-get'):
        plan.append(('cli', [pk, _which('apt-get'), 'install', '-y', path],
                     u'apt-get'))
    if pk and _which('dpkg'):
        plan.append(('cli', [pk, _which('dpkg'), '-i', path], u'dpkg'))
    xo = _which('xdg-open')
    if xo:
        plan.append(('gui', [xo, path], u'默认打开方式'))
    return plan


def install_env():
    """安装时静默 dpkg 交互，避免 postinst 里的 zenity 询问打断升级。"""
    env = dict(os.environ)
    env['DEBIAN_FRONTEND'] = 'noninteractive'
    return env


def updates_dir():
    from . import data as D
    d = os.path.join(D.data_dir(), 'updates')
    try:
        if not os.path.isdir(d):
            os.makedirs(d)
    except OSError:
        pass
    return d


def restart_command():
    """重启自身用的命令：优先启动器，其次当前解释器。"""
    exe = _which('desktop-calendar')
    if exe:
        return [exe]
    return [sys.executable, '-m', 'brl']


# ---------------------------------------------------------------- 应用商店
def store_present():
    """系统里有没有 UOS 应用商店（有客户端或它的 DBus 服务都算）。"""
    return bool(_which(STORE_CLIENT)) or os.path.exists(STORE_SERVICE)


def _spawn(argv):
    """把命令丢到后台，不等它退出（商店窗口什么时候起来不归我们管）。"""
    subprocess.Popen(argv,
                     stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL,
                     start_new_session=True,
                     close_fds=True)


def open_store():
    """打开应用商店里本应用的详情页。返回 (ok, 说明)。

    两条路都走官方支持的方式：
      1. 客户端带业务 URI：商店已运行时由单实例机制转给已有窗口；
         没运行时会顺带把窗口拉起来并直接落在详情页；
      2. DBus ``openBusinessUri``：商店的服务由 DBus 激活。
    """
    if not store_present():
        return False, u'系统里没有找到应用商店'
    cli = _which(STORE_CLIENT)
    if cli:
        try:
            _spawn([cli, STORE_URI])
            return True, cli
        except Exception as e:
            first = u'%s' % (e,)
    else:
        first = u'没有找到 %s' % STORE_CLIENT
    ds = _which('dbus-send')
    if ds:
        try:
            _spawn([ds, '--session', '--print-reply=literal',
                    '--dest=%s' % STORE_BUS, STORE_PATH,
                    '%s.openBusinessUri' % STORE_BUS,
                    'string:app_detail_info/%s' % STORE_APPID])
            return True, 'dbus'
        except Exception as e:
            return False, u'%s / %s' % (first, e)
    return False, first


def fail_backoff(ts, now_ts=None):
    """检查失败后是否还在退避期（失败一次就别每小时都去撞）。"""
    if not ts:
        return False
    import time
    now_ts = time.time() if now_ts is None else now_ts
    try:
        return (now_ts - float(ts)) < FAIL_BACKOFF
    except (TypeError, ValueError):
        return False


def relaunch(delay=1.0, env=None):
    """另起一个独立进程，delay 秒后把新版本拉起来。

    关键在于「等旧进程先走」：新版本起来时会把还在跑的旧版本请出去，
    但更稳妥的是让旧版本先保存退出、新的再接手，两者不并存，
    配置与待办库就不会被两份内存状态互相覆盖。
    """
    cmd = restart_command()
    argv = ['/bin/sh', '-c',
            'sleep %g; exec "$0" "$@"' % max(0.2, float(delay))]
    argv.extend(cmd)
    try:
        subprocess.Popen(argv,
                         stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         start_new_session=True,
                         close_fds=True,
                         env=env or install_env())
        return True, u' '.join(cmd)
    except Exception as e:
        return False, u'%s' % (e,)
