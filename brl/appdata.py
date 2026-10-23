# -*- coding: utf-8 -*-
"""用户数据的保护与跨升级继承。

管三件事：

1. **实例记录**：把当前进程的 pid 写进数据目录，安装脚本和下一个实例
   才能知道"旧版本还开着"，先请它保存退出，再让新版本接管；
2. **升级保护**：覆盖安装前把「待办库 + 设置」备份到用户数据目录之外
   （否则目录一旦被清空，备份也一起没了），装完发现缺失就补回来；
3. **旧路径迁移**：XDG 目录不可用时的 ``~/.desktop-calendar`` 兜底目录、
   或环境变量变化导致读不到数据时，把老文件搬回当前位置。

本模块刻意**不依赖 Qt**，安装脚本在没有图形环境时也能用命令行直接调用。
"""
import os
import shutil
import signal
import sys
import time

PID_NAME = 'app.pid'
INI_NAME = 'calendar.ini'
DB_NAME = 'calendar.db'
BK_PREFIX = 'upgrade'

# 旧版本可能的落脚点（相对 ~），迁移时按这个顺序找
LEGACY_DIRS = ('.desktop-calendar', '.local/share/desktop-calendar')


# ---------------------------------------------------------------- 路径
def _dirs():
    """(配置目录, 数据目录)"""
    from . import data as D
    return D.config_dir(), D.data_dir()


def user_files():
    """[(绝对路径, 类型)]——类型是 ini / db，用于备份与恢复。"""
    cfg, dat = _dirs()
    return [(os.path.join(cfg, INI_NAME), 'ini'),
            (os.path.join(dat, DB_NAME), 'db')]


def pid_file():
    _c, dat = _dirs()
    return os.path.join(dat, PID_NAME)


# ---------------------------------------------------------------- 实例记录
def read_pid():
    """读 pid 文件 -> (pid, 命令行, 版本)；没有/损坏返回 None。"""
    try:
        with open(pid_file(), 'r') as f:
            parts = f.read().strip().split()
    except (IOError, OSError):
        return None
    if not parts:
        return None
    try:
        pid = int(parts[0])
    except ValueError:
        return None
    return (pid, parts[1] if len(parts) > 1 else '',
            parts[2] if len(parts) > 2 else '')


def write_pid(ver=''):
    """登记当前实例（先写临时文件再改名，避免读到写了一半的内容）。"""
    p = pid_file()
    try:
        tmp = p + '.tmp'
        with open(tmp, 'w') as f:
            f.write('%d %s %s\n' % (os.getpid(), sys.argv[0] or 'brl', ver))
        os.replace(tmp, p)
        return True
    except (IOError, OSError):
        return False


def clear_pid(only_self=True):
    """清掉 pid 文件。only_self=True 时只删自己写的那份。"""
    p = pid_file()
    if only_self:
        r = read_pid()
        if r and r[0] != os.getpid():
            return False
    try:
        os.remove(p)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- 进程探测
def _cmdline(pid):
    try:
        with open('/proc/%d/cmdline' % pid, 'rb') as f:
            raw = f.read()
    except (IOError, OSError):
        return ''
    return raw.replace(b'\0', b' ').decode('utf-8', 'replace')


def _comm(pid):
    """进程名（/proc/<pid>/comm）。"""
    try:
        with open('/proc/%d/comm' % pid, 'r') as f:
            return f.read().strip()
    except (IOError, OSError):
        return ''


def _is_ours(pid, cmd=None):
    """这个进程是不是日历本体。

    只看命令行文本是不够的：用户在终端里敲
    ``sudo dpkg -i desktop-calendar_x.y.z_arm64.deb`` 时，那个 shell 和
    dpkg 的命令行里同样有 "desktop-calendar" 这串字，照单全收会把人家的
    shell、甚至正在装我们的 dpkg 一起杀掉。所以必须是
    「进程名是解释器 + 参数里带着 -m brl」才算数。
    """
    if pid <= 1:
        return False
    c = (_cmdline(pid) if cmd is None else cmd).strip()
    if not c:
        return False
    if 'desktop-calendar-upgrade' in c:
        return False
    comm = _comm(pid)
    if comm.startswith('python') or comm == 'brl':
        return '-m brl' in c or c.rstrip().endswith('brl')
    return comm.startswith('desktop-calendar')


def _proc_state(pid):
    """/proc 里的进程状态字符，读不到返回 ''。"""
    try:
        with open('/proc/%d/stat' % pid, 'r') as f:
            st = f.read()
    except (IOError, OSError):
        return ''
    i = st.rfind(')')
    if i < 0:
        return ''
    return st[i + 1:].strip()[:1]


def _alive(pid):
    """进程真的还在吗？

    僵尸进程 /proc 目录还在、os.kill(pid, 0) 也照样成功，
    不排除的话旧版本会被当成"死赖着不走"，白白等满超时。
    """
    if _proc_state(pid) == 'Z':
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def alive_pid():
    """pid 文件记录的那个实例还在跑吗？在则返回 pid，否则 None。"""
    r = read_pid()
    if not r:
        return None
    pid = r[0]
    if pid == os.getpid():
        return None
    if not _alive(pid) or not _is_ours(pid):
        return None
    return pid


def running_pids():
    """扫 /proc 找出所有日历进程（不含自己）。老版本没写 pid 文件时靠它。"""
    me = os.getpid()
    out = []
    try:
        names = os.listdir('/proc')
    except OSError:
        return out
    for name in names:
        if not name.isdigit():
            continue
        pid = int(name)
        if pid == me or not _alive(pid):
            continue
        if _is_ours(pid):
            out.append(pid)
    return out


def other_instances():
    """当前机器上除自己以外的日历进程 pid 列表（去重、有序）。"""
    pids = set(running_pids())
    p = alive_pid()
    if p:
        pids.add(p)
    pids.discard(os.getpid())
    return sorted(pids)


def request_quit(timeout=4.0, kill=True):
    """请其它实例保存退出。返回 (已停止的 pid, 仍在跑的 pid)。

    先 SIGTERM（新版装了处理器，会保存窗口位置与设置后自行退出），
    超时仍不走的才 SIGKILL——老版本没有处理器，会直接被终止。
    """
    pids = other_instances()
    if not pids:
        return [], []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
    end = time.time() + max(0.0, float(timeout))
    left = list(pids)
    while time.time() < end:
        time.sleep(0.2)
        left = [p for p in pids if _alive(p)]
        if not left:
            break
    stopped = [p for p in pids if p not in left]
    if kill and left:
        for pid in left:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.3)
        left = [p for p in left if _alive(p)]
        stopped = [p for p in pids if p not in left]
    return stopped, left


def take_over(timeout=4.0):
    """启动时接管：让旧实例先退出，避免新旧两份配置互相覆盖。"""
    return request_quit(timeout=timeout)


# ---------------------------------------------------------------- 备份
def backup_roots():
    """备份目录候选（按优先级）。

    刻意放在用户数据目录之外：数据目录本身被清空的极端情况下，
    备份才能留得住。root 身份时用 /var/backups，否则回落到家目录。
    """
    roots = []
    env = os.environ.get('DC_BACKUP_ROOT')
    if env:
        roots.append(env)
    if os.path.isdir('/var/backups') and _writable('/var/backups'):
        roots.append(os.path.join('/var/backups', 'desktop-calendar'))
    home = os.path.expanduser('~')
    roots.append(os.path.join(home, '.desktop-calendar-backup'))
    return roots


def _writable(d):
    return os.access(d, os.W_OK)


def make_backup(tag=None):
    """把设置与待办库备份一份。返回 (目录, ['ini','db'])，失败返回 ('', [])。"""
    tag = tag or (BK_PREFIX + '-' + time.strftime('%Y%m%d-%H%M%S'))
    for root in backup_roots():
        d = os.path.join(root, tag)
        try:
            os.makedirs(d)
        except OSError:
            continue
        got = []
        for src, kind in user_files():
            try:
                if not os.path.isfile(src) or os.path.getsize(src) <= 0:
                    continue
            except OSError:
                continue
            try:
                shutil.copy2(src, os.path.join(d, os.path.basename(src)))
                got.append(kind)
            except (IOError, OSError):
                pass
        if got:
            return d, sorted(set(got))
        try:
            os.rmdir(d)
        except OSError:
            pass
    return '', []


def list_backups():
    """所有可用的备份目录，新的在前。"""
    out = []
    for root in backup_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in sorted(names, reverse=True):
            d = os.path.join(root, n)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, INI_NAME)) \
                    or os.path.isdir(d) and os.path.isfile(os.path.join(d, DB_NAME)):
                out.append(d)
    return out


def latest_backup():
    bs = list_backups()
    return bs[0] if bs else ''


def restore_missing(backup=None):
    """目标文件缺失或为空时才补回来。返回 ['ini','db']。"""
    d = backup or latest_backup()
    if not d:
        return []
    got = []
    for src, kind in user_files():
        try:
            if os.path.isfile(src) and os.path.getsize(src) > 0:
                continue
        except OSError:
            pass
        b = os.path.join(d, os.path.basename(src))
        try:
            if not os.path.isfile(b) or os.path.getsize(b) <= 0:
                continue
        except OSError:
            continue
        try:
            dd = os.path.dirname(src)
            if dd and not os.path.isdir(dd):
                os.makedirs(dd)
            shutil.copy2(b, src)
            got.append(kind)
        except (IOError, OSError):
            pass
    return got


def migrate_legacy():
    """从旧路径把数据搬回来（只搬目标缺失的）。返回 ['ini','db']。

    场景：XDG 目录不可用时的 ``~/.desktop-calendar`` 兜底目录，
    或 XDG_DATA_HOME/XDG_CONFIG_HOME 变化后读不到原来的数据。
    """
    cfg, dat = _dirs()
    home = os.path.expanduser('~')
    cands = []
    for name in LEGACY_DIRS:
        cands.append(os.path.join(home, name))
    cands.append(os.path.join(home, '.local/share/desktop-calendar'))
    cands.append(os.path.join(home, '.config/desktop-calendar'))
    cands.append(os.path.join(home, '.desktop-calendar-backup'))

    got = []
    for src, kind in user_files():
        try:
            if os.path.isfile(src) and os.path.getsize(src) > 0:
                continue
        except OSError:
            pass
        base = os.path.basename(src)
        best, best_mt = '', -1
        for c in cands:
            p = os.path.join(c, base)
            try:
                if c in (cfg, dat) or not os.path.isfile(p):
                    continue
                if os.path.getsize(p) <= 0:
                    continue
                mt = os.path.getmtime(p)
            except OSError:
                continue
            # 备份目录里的子目录（upgrade-xxx）也要翻一翻
            if c.endswith('.desktop-calendar-backup'):
                continue
            if mt > best_mt:
                best, best_mt = p, mt
        if not best:
            # 备份目录内部按子目录找最新的那个
            for root in (os.path.join(home, '.desktop-calendar-backup'),
                         '/var/backups/desktop-calendar'):
                try:
                    subs = sorted(os.listdir(root), reverse=True)
                except OSError:
                    continue
                for s in subs:
                    p = os.path.join(root, s, base)
                    try:
                        if not os.path.isfile(p) or os.path.getsize(p) <= 0:
                            continue
                        mt = os.path.getmtime(p)
                    except OSError:
                        continue
                    if mt > best_mt:
                        best, best_mt = p, mt
        if not best:
            continue
        try:
            dd = os.path.dirname(src)
            if dd and not os.path.isdir(dd):
                os.makedirs(dd)
            shutil.copy2(best, src)
            got.append(kind)
        except (IOError, OSError):
            pass
    return got


def ensure_data(backup=None):
    """升级收尾：先补旧路径的，再补备份的。返回 ['ini','db']。

    backup 可显式指定备份目录（测试用），不传则按备份根里的最新一份；
    显式指定可以避免机器上其它历史备份（如 /var/backups 里的残留）
    抢先被当成数据源。
    """
    got = migrate_legacy()
    for k in restore_missing(backup):
        if k not in got:
            got.append(k)
    return got


def prune_backups(keep=5):
    """只留最近 keep 份备份，避免越攒越多。"""
    for root in backup_roots():
        try:
            names = sorted(os.listdir(root), reverse=True)
        except OSError:
            continue
        for n in names[keep:]:
            d = os.path.join(root, n)
            if os.path.isdir(d):
                try:
                    shutil.rmtree(d)
                except (IOError, OSError):
                    pass


# ---------------------------------------------------------------- 命令行
def cli(action):
    """安装脚本 / 命令行用的入口，返回 (说明, 退出码)。"""
    if action == 'quit':
        stopped, left = request_quit()
        if not stopped and not left:
            return 'idle', 0
        return 'stopped=%s left=%s' % (','.join(str(x) for x in stopped),
                                       ','.join(str(x) for x in left)), \
            0 if not left else 1
    if action == 'instances':
        ps = other_instances()
        return ('running=%s' % ','.join(str(x) for x in ps)) if ps else 'idle', 0
    if action == 'backup':
        d, kinds = make_backup()
        if not d:
            return 'nothing', 1
        prune_backups()
        return 'backup=%s %s' % (d, ','.join(kinds)), 0
    if action == 'ensure':
        got = ensure_data()
        return ('restored=%s' % ','.join(got)) if got else 'nothing', 0
    if action == 'pid':
        r = read_pid()
        return ('pid=%s' % r[0]) if r else 'none', 0
    return 'unknown action', 2
