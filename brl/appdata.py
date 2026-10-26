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
import sqlite3
import sys
import time

PID_NAME = 'app.pid'
INI_NAME = 'calendar.ini'
DB_NAME = 'calendar.db'
BK_PREFIX = 'upgrade'

# 旧版本可能的落脚点（相对 ~），迁移时按这个顺序找
LEGACY_DIRS = ('.desktop-calendar', '.local/share/desktop-calendar')

# 待办表的字段（合并时只搬这些列，老库缺列也不会炸）。
# 与 store.SCHEMA 保持一致；这里刻意不 import store——store 在模块导入时
# 就会建库，恢复动作必须赶在那之前完成（详见 ensure_data 的说明）。
TODO_COLS = ('content', 'category', 'color', 'italic', 'underline', 'date',
             'repeat', 'remind', 'remind_time', 'done', 'created')

_SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS todo(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '生活',
    color TEXT NOT NULL DEFAULT '#FFFFFFFF',
    italic INTEGER NOT NULL DEFAULT 0,
    underline INTEGER NOT NULL DEFAULT 0,
    date TEXT NOT NULL DEFAULT '',
    repeat INTEGER NOT NULL DEFAULT 0,
    remind INTEGER NOT NULL DEFAULT 0,
    remind_time TEXT NOT NULL DEFAULT '09:00',
    done INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL DEFAULT ''
);
"""


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
        # 显式指定备份根（安装脚本 / 测试隔离）：只用它，别再去翻系统备份区，
        # 否则测试机器上真机安装留下的那份会把结果带偏。
        roots.append(env)
    else:
        # 系统级备份区：安装脚本以 root 身份备份时就落在这儿。普通用户虽然
        # 写不进去，但目录和文件都可读——"恢复"要能读到它，否则真机上最
        # 权威的那份备份反而被跳过。
        vroot = os.path.join('/var/backups', 'desktop-calendar')
        if os.path.isdir(vroot) or (os.path.isdir('/var/backups')
                                    and _writable('/var/backups')):
            roots.append(vroot)
    home = os.path.expanduser('~')
    roots.append(os.path.join(home, '.desktop-calendar-backup'))
    return roots


def _writable(d):
    return os.access(d, os.W_OK)


# ---------------------------------------------------------------- 待办库工具
def db_count(path):
    """一个待办库里有几条待办。文件不存在 / 打不开 / 没有 todo 表都算 0。

    "0 条"是判断"这个库是不是空的"的唯一可靠依据：文件大小靠不住——
    Store 一启动就会建表建库，一个 12KB 却一条待办都没有的库，光看
    size 会被当成"有数据"，于是再也不敢用备份覆盖它。
    """
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return 0
        cn = sqlite3.connect(path, timeout=3.0)
        try:
            return int(cn.execute('SELECT COUNT(*) FROM todo').fetchone()[0])
        finally:
            cn.close()
    except (sqlite3.Error, OSError, ValueError):
        return 0


def db_max_id(path):
    """这个库里"历史上最大的一条待办编号"。读不到返回 0。

    空库有两种，长得一模一样，必须分清：
      · **用户自己把待办删光了**——库还是原来那个，sqlite_sequence 里
        记着最大编号（比如 50），只是没行了；
      · **库被换成了新建的空库**（升级时 Store 抢先建表就是这个）——
        编号从未分配过，是 0。
    前者绝不能用备份"救回来"（那等于把用户删掉的东西又变出来），
    后者必须救。文件大小、mtime 都区分不了这两者，唯独这个编号可以。
    """
    try:
        if not path or not os.path.isfile(path) or os.path.getsize(path) <= 0:
            return 0
        cn = sqlite3.connect(path, timeout=3.0)
        try:
            row = cn.execute(
                "SELECT seq FROM sqlite_sequence WHERE name='todo'").fetchone()
            return int(row[0]) if row and row[0] else 0
        except (sqlite3.Error, TypeError, IndexError):
            return 0
        finally:
            cn.close()
    except (sqlite3.Error, OSError, ValueError):
        return 0


def newest_backup():
    """时间上最新的那份备份（合并首选它：它就是升级前那一刻的状态）。"""
    best, best_mt = '', -1.0
    for root in backup_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            d = os.path.join(root, n)
            if not os.path.isdir(d):
                continue
            db = os.path.join(d, DB_NAME)
            ini = os.path.join(d, INI_NAME)
            if not (os.path.isfile(db) or os.path.isfile(ini)):
                continue
            try:
                mt = os.path.getmtime(db if os.path.isfile(db) else ini)
            except OSError:
                continue
            if mt > best_mt:
                best, best_mt = d, mt
    return best


def _snapshot_db(src, dst):
    """用 SQLite 自己的备份接口做一份一致快照（会把 WAL 里没合并的记录一起带上）。

    以前是直接 cp 文件：程序正开着的时候，刚写完还没落盘的那部分在
    -wal / -journal 里，cp 出来的库可能少几条待办，偏偏备份链就是这么
    一步步被"瘦"没的。
    """
    cn = sqlite3.connect(src, timeout=5.0)
    try:
        out = sqlite3.connect(dst)
        try:
            cn.backup(out)
        finally:
            out.close()
    finally:
        cn.close()


def _ensure_schema(cn):
    try:
        cn.executescript(_SCHEMA_DDL)
    except sqlite3.Error:
        pass


def merge_rows(src_db, dst_db):
    """把 src 里"dst 还没有"的待办补进 dst。只增不减，返回补了几条。

    去重键用（内容 + 日期 + 分类 + 创建时间）：同一秒里手打两条一模一样
    的待办本来就少见，就算真撞上了也只是少补一条，不会把别人的数据冲掉。
    """
    if db_count(src_db) <= 0:
        return 0
    src = sqlite3.connect(src_db, timeout=5.0)
    src.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in src.execute('SELECT * FROM todo').fetchall()]
    except sqlite3.Error:
        return 0
    finally:
        src.close()
    if not rows:
        return 0
    dst = sqlite3.connect(dst_db, timeout=5.0)
    dst.row_factory = sqlite3.Row
    try:
        _ensure_schema(dst)
        cols = [r[1] for r in dst.execute('PRAGMA table_info(todo)').fetchall()]
        have = set()
        for r in dst.execute('SELECT content, date, created, category FROM todo'):
            have.add((r[0], r[1], r[2], r[3]))
        added = 0
        with dst:
            for r in rows:
                key = (r.get('content'), r.get('date'), r.get('created'),
                       r.get('category'))
                if key in have:
                    continue
                use = [c for c in TODO_COLS if c in cols and c in r]
                if not use:
                    continue
                try:
                    dst.execute('INSERT INTO todo(%s) VALUES(%s)'
                                % (','.join(use), ','.join('?' * len(use))),
                                [r[c] for c in use])
                except sqlite3.Error:
                    continue
                have.add(key)
                added += 1
        return added
    except sqlite3.Error:
        return 0
    finally:
        dst.close()


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
            dst = os.path.join(d, os.path.basename(src))
            try:
                if kind == 'db':
                    _snapshot_db(src, dst)
                else:
                    shutil.copy2(src, dst)
                got.append(kind)
            except (IOError, OSError, sqlite3.Error):
                try:
                    os.remove(dst)
                except OSError:
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


def best_backup():
    """挑最"有料"的一份备份：待办条数最多优先，条数相同才比新旧。

    只看时间会踩坑：升级链路上有可能先落一份"空库"备份（Store 抢先
    建表、或者备份时库刚好是空的），按时间取最新就会一直拿到空的，
    真正有数据的那几份被压在后面，恢复出来当然是"待办全没了"。
    """
    best, best_key = '', (-1, -1.0)
    for root in backup_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            d = os.path.join(root, n)
            if not os.path.isdir(d):
                continue
            db = os.path.join(d, DB_NAME)
            ini = os.path.join(d, INI_NAME)
            if not (os.path.isfile(db) or os.path.isfile(ini)):
                continue
            try:
                mt = os.path.getmtime(db if os.path.isfile(db) else ini)
            except OSError:
                continue
            key = (db_count(db), mt)
            if key > best_key:
                best, best_key = d, key
    return best


def _copy_into(src, dst):
    try:
        dd = os.path.dirname(dst)
        if dd and not os.path.isdir(dd):
            os.makedirs(dd)
        shutil.copy2(src, dst)
        return True
    except (IOError, OSError):
        return False


def _first_existing(dirs, base):
    """按顺序找第一个存在且非空的备份文件，找不到返回 ''。"""
    for d in dirs:
        if not d:
            continue
        p = os.path.join(d, base)
        try:
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                return p
        except OSError:
            continue
    return ''


def _newest_with_rows(base):
    """最新的、里面确实有待办的备份文件（从新到旧挑）。"""
    cands = []
    for root in backup_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n, base)
            try:
                if not os.path.isfile(p) or os.path.getsize(p) <= 0:
                    continue
                cands.append((os.path.getmtime(p), p))
            except OSError:
                continue
    for _mt, p in sorted(cands, reverse=True):
        if db_count(p) > 0:
            return p
    return ''


def restore_missing(backup=None, merge=False):
    """把备份里"现在缺的"补回来，只增不减。返回 ['ini','db']。

    四种情形分开处理：

    ① 库文件不存在 / 0 字节 —— 直接从备份整份拷回来；
    ② 库在、一条待办都没有 —— 先用 sqlite_sequence 判断这是"用户自己
       删光了"还是"库被换成了新建的空库"：前者不动，后者补回来。
       这一步很关键：以前只看"文件在、不是 0 字节"，空库就被当成有数据，
       备份再也不敢用，用户的待办等于永久丢失；
    ③ 库里有数据且 merge=True（升级收尾）—— 从**最新**那份备份里把
       "目标没有的"行补进来。正常情况一条都不会补（两边一样），所以不会
       把用户删掉的待办又变出来；
    ④ 设置文件只在缺失时整份拷回：安装过程根本不会碰 calendar.ini，
       能走到这一步说明它真被清掉了，这时整份拿回来最安全。
    """
    d_rich = backup or best_backup()
    d_new = backup or newest_backup()
    got = []
    for src, kind in user_files():
        base = os.path.basename(src)
        b = _first_existing((d_rich, d_new), base)
        try:
            alive = os.path.isfile(src) and os.path.getsize(src) > 0
        except OSError:
            alive = False
        if kind == 'ini':
            if alive:
                continue
            if b and _copy_into(b, src):
                got.append('ini')
            continue
        # ---- 待办库
        if not alive:
            if b and db_count(b) > 0 and _copy_into(b, src):
                got.append('db')
            continue
        if db_count(src) > 0:
            # 有数据：升级收尾才合并，且只用"最新那份"（= 升级前一瞬的状态），
            # 免得把很久以前的待办又塞回来
            if merge:
                b = _first_existing((d_new, d_rich), base)
                if b and db_count(b) <= 0:
                    # 最新那份是空的（本身就没内容可合），往前找有数据的
                    b = _newest_with_rows(base)
                if b and merge_rows(b, src) > 0:
                    got.append('db')
            continue
        # 空库：用户自己删光的就别动，被换成新建空库的才补
        if db_max_id(src) > 0:
            continue
        if b and db_count(b) > 0 and merge_rows(b, src) > 0:
            got.append('db')
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
            # 备份目录内部按子目录找最新的那个（只翻家目录里这份；
            # 系统级备份区归 restore_missing 统一管，在这里翻容易把
            # 别的机器/历史安装留下的陈年数据搬回来）
            root = os.path.join(home, '.desktop-calendar-backup')
            try:
                subs = sorted(os.listdir(root), reverse=True)
            except OSError:
                subs = []
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


def ensure_data(backup=None, merge=False):
    """启动 / 升级收尾：先补备份的，再补旧路径的。返回 ['ini','db']。

    backup 可显式指定备份目录（安装脚本/测试用），不传则自动挑条数最多的
    那份（见 best_backup）。顺序必须是「备份优先」：显式备份是这次升级前
    刚做的那份，是最权威的快照；要是让 migrate_legacy 先跑，它从别的角落
    翻出来的陈年数据先把缺的文件填上，真正的备份反而因为"文件已存在"被跳过
    （v20 回归踩过：机器 /var/backups 里留着一份真机安装时的备份，
    测试就恢复出了别人家的数据）。

    merge=True 时连"库里有数据"的情况也补一遍缺的行——升级收尾用。
    """
    got = restore_missing(backup, merge=merge)
    for k in migrate_legacy():
        if k not in got:
            got.append(k)
    return got


def auto_snapshot(interval=12 * 3600.0):
    """平时给待办库留一份"近日快照"，离上一份不够久就跳过。

    升级备份只在升级那一瞬间做，万一数据是在平时没的（磁盘清理、手动
    误删、同步软件、断电写坏），升级链路一点忙都帮不上。这里每次启动
    顺手看一眼：半天没备份过、而且库里确实有东西，就再存一份。
    返回备份目录，没做则返回 ''。
    """
    db = user_files()[1][0]
    if db_count(db) <= 0:
        return ''
    newest = 0.0
    for root in backup_roots():
        try:
            names = os.listdir(root)
        except OSError:
            continue
        for n in names:
            if not n.startswith('auto-'):
                continue
            p = os.path.join(root, n, DB_NAME)
            try:
                newest = max(newest, os.path.getmtime(p))
            except OSError:
                continue
    if newest and (time.time() - newest) < interval:
        return ''
    d, kinds = make_backup('auto-' + time.strftime('%Y%m%d-%H%M%S'))
    if d:
        prune_backups(keep=8)
    return d


def prune_backups(keep=5):
    """只留最近 keep 份备份，避免越攒越多。
    唯一例外：待办最多的那一份永不删。否则连着几次"空库备份"就能把
    唯一一份有数据的备份挤出保留窗口——那才是真的救不回来了。
    """
    for root in backup_roots():
        try:
            names = [n for n in os.listdir(root)
                     if os.path.isdir(os.path.join(root, n))]
        except OSError:
            continue
        if len(names) <= keep:
            continue
        def _rank(n):
            d = os.path.join(root, n)
            db = os.path.join(d, DB_NAME)
            try:
                mt = os.path.getmtime(db if os.path.isfile(db) else d)
            except OSError:
                mt = 0.0
            return (db_count(db), mt)
        ranked = sorted(names, key=_rank, reverse=True)
        gold = ranked[0]                      # 待办最多的那份，永不删
        rest = [n for n in ranked if n != gold]
        keep_n = max(0, keep - 1)
        for n in rest[keep_n:]:
            d = os.path.join(root, n)
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
    if action == 'restore':
        # 升级收尾用：挑条数最多的备份做"只增不减"的合并
        d = best_backup()
        got = ensure_data(d or None, merge=True)
        if not d:
            return 'backup=- restored=-', 0
        return 'backup=%s restored=%s' % (d, ','.join(got) or '-'), 0
    if action == 'pid':
        r = read_pid()
        return ('pid=%s' % r[0]) if r else 'none', 0
    return 'unknown action', 2
