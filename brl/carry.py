# -*- coding: utf-8 -*-
"""用户数据随身包 —— 升级时把「自定义设置」和「待办清单」带过去。

时序只有两步，和安装脚本严格对应：

  安装第一步（preinst，新包还没解开）：
      读取当前用户的设置与待办，分别另存成两个特殊命名的文件
          user-settings-<用户>-<时间戳>.ini
          user-todos-<用户>-<时间戳>.db
      并写一个指针 user-carry-<用户>.stamp，记下"这一趟存的是哪一组"。

  安装最后一步（postinst，新包已经就位、旧进程已经退出）：
      只认指针指的那一组，把它们原样放回用户目录。

两个文件共用同一个时间戳，指针又把这次安装和这一组绑死——所以哪怕备份目录里
躺着上次安装留下的旧数据，也不会被翻出来盖掉用户现在的待办。

本文件刻意不 import 任何 brl 模块、不碰 Qt：
preinst 阶段包里还没有这个文件，由 makedeb 把源码整段内联进脚本执行；
装完之后再直接跑这个文件。两边共用同一份源码，不存在实现的漂移。
"""
import os
import shutil
import sqlite3
import sys
import time

SET_PREFIX = 'user-settings-'
TODO_PREFIX = 'user-todos-'
STAMP_PREFIX = 'user-carry-'
INI = 'calendar.ini'
DB = 'calendar.db'
TABLE = 'todo'
KEEP = 3          # 每个用户留最近 3 组，再多就删，免得备份目录无限长

# 退出码：0 成 / 2 无事可做（没东西可存，或没有这一组可放回）/ 3 出错
OK, NOTHING, FAIL = 0, 2, 3


# ---------------------------------------------------------------- 路径与命名
def home_dirs(home):
    """home -> (配置目录, 数据目录)。与 brl/data.py 的默认布局保持一致。"""
    return (os.path.join(home, '.config', 'desktop-calendar'),
            os.path.join(home, '.local', 'share', 'desktop-calendar'))


def new_stamp(t=None):
    return time.strftime('%Y%m%d-%H%M%S', time.localtime(t))


def _tag(user):
    """用户名进文件名：一台机器上多个用户各自的包互不覆盖。"""
    s = ''.join(c if (c.isalnum() or c in '-_.') else '_' for c in (user or 'user'))
    return s or 'user'


def names(user, stamp):
    t = _tag(user)
    return (SET_PREFIX + t + '-' + stamp + '.ini',
            TODO_PREFIX + t + '-' + stamp + '.db')


def stamp_path(root, user):
    return os.path.join(root, STAMP_PREFIX + _tag(user) + '.stamp')


def _write_stamp(root, user, stamp):
    try:
        with open(stamp_path(root, user), 'w') as f:
            f.write(stamp + '\n')
        return True
    except OSError:
        return False


def read_stamp(root, user):
    try:
        with open(stamp_path(root, user)) as f:
            return f.read().strip() or None
    except OSError:
        return None


def read_stamp_any(root):
    """用户名对不上时（安装器里 preinst 与 postinst 各自探测用户，
    极少数情况下会得到不同的名字）退回"最新写下的那个指针"。"""
    best, best_t = None, -1
    try:
        files = os.listdir(root)
    except OSError:
        return None
    for f in files:
        if f.startswith(STAMP_PREFIX) and f.endswith('.stamp'):
            p = os.path.join(root, f)
            try:
                t = os.path.getmtime(p)
                with open(p) as fh:
                    st = fh.read().strip()
            except OSError:
                continue
            if st and t > best_t:
                best, best_t = st, t
    return best


def pairs(root, user=None):
    """备份目录里的组，新的在前；user 为空表示不限用户。

    返回 [(键, ini路径, db路径), ...]，两个文件都在才算一组。
    键是文件名里 <用户>-<时间戳> 那一段，跨用户也唯一。
    """
    out = []
    try:
        files = os.listdir(root)
    except OSError:
        return out
    pre = SET_PREFIX + (_tag(user) + '-' if user else '')
    seen = {}
    for f in files:
        if not (f.startswith(pre) and f.endswith('.ini')):
            continue
        mid = f[len(SET_PREFIX):-4]          # <用户>-<时间戳>
        db = os.path.join(root, TODO_PREFIX + mid + '.db')
        if os.path.isfile(db):
            seen[mid] = (mid, os.path.join(root, f), db)
    for k in sorted(seen, reverse=True):
        out.append(seen[k])
    return out


# ---------------------------------------------------------------- 读写
def _rows(path):
    """库里的待办条数；文件不在或打不开返回 -1。"""
    if not os.path.isfile(path):
        return -1
    try:
        cn = sqlite3.connect('file:%s?mode=ro' % path, uri=True, timeout=3)
        try:
            cur = cn.execute('select count(*) from %s' % TABLE)
            return int(cur.fetchone()[0])
        finally:
            cn.close()
    except Exception:
        return -1


def snapshot_db(src, dst):
    """把库另存一份。

    程序开着的时候数据可能还在 -wal 里，直接 cp 会少几条待办；
    SQLite 自己的 backup 接口拿到的是一致快照，所以优先用它。
    库损坏 / 被独占时退回到连旁路文件一起拷。
    """
    try:
        cn = sqlite3.connect('file:%s?mode=ro' % src, uri=True, timeout=3)
        try:
            out = sqlite3.connect(dst)
            try:
                cn.backup(out)
            finally:
                out.close()
        finally:
            cn.close()
        if os.path.getsize(dst) > 0:
            return True
    except Exception:
        pass
    try:
        shutil.copyfile(src, dst)
        for suf in ('-wal', '-shm'):
            p = src + suf
            if os.path.isfile(p) and os.path.getsize(p) > 0:
                shutil.copyfile(p, dst + suf)
        return True
    except Exception:
        return False


def _drop_sidecars(path):
    """换库之前先清掉旧库的 -wal/-shm：
    留着它们，SQLite 打开新库时会把上一份未合并的日志回放进去。"""
    for suf in ('-wal', '-shm'):
        p = path + suf
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass


def _chown(path, owner):
    """以 root 身份落盘时把属主交还用户，否则用户下次开程序写不进去。"""
    if not owner or os.geteuid() != 0:
        return
    try:
        import pwd
        u = pwd.getpwnam(owner)
        os.chown(path, u.pw_uid, u.pw_gid)
    except Exception:
        pass


# ---------------------------------------------------------------- 存
def save(cfg, dat, root, user, stamp=None):
    """把设置与待办各存一份。返回 dict：stamp / ini / db（1=存了）。"""
    res = {'stamp': stamp or new_stamp(), 'ini': 0, 'db': 0, 'dir': root}
    try:
        if not os.path.isdir(root):
            os.makedirs(root)
    except OSError as e:
        res['error'] = 'mkdir: %s' % e
        return res

    name_ini, name_db = names(user, res['stamp'])
    dst_ini = os.path.join(root, name_ini)
    dst_db = os.path.join(root, name_db)

    src_ini = os.path.join(cfg, INI)
    if os.path.isfile(src_ini) and os.path.getsize(src_ini) > 0:
        try:
            shutil.copyfile(src_ini, dst_ini)
            res['ini'] = 1
        except OSError as e:
            res['error'] = 'ini: %s' % e

    src_db = os.path.join(dat, DB)
    if os.path.isfile(src_db) and os.path.getsize(src_db) > 0:
        if snapshot_db(src_db, dst_db):
            res['db'] = 1
            res['rows'] = _rows(dst_db)
        else:
            res['error'] = 'db: snapshot failed'

    if not (res['ini'] or res['db']):
        # 用户还没开始用（或者两样都读不到）：不写指针，
        # 免得最后一步拿着空包去覆盖一个本来就有数据的目录。
        return res

    res['stamped'] = _write_stamp(root, user, res['stamp'])
    res['kept'] = prune(root, user)
    return res


def prune(root, user, keep=KEEP):
    """只留最近 keep 组，返回删掉的组名。"""
    gone = []
    for st, ini, db in pairs(root, user)[keep:]:
        for p in (ini, db, db + '-wal', db + '-shm'):
            try:
                if os.path.exists(p):
                    os.remove(p)
            except OSError:
                pass
        gone.append(st)
    return gone


# ---------------------------------------------------------------- 放回
def load(cfg, dat, root, user, stamp=None, force=False, owner=None):
    """把存下的两样东西放回去。

    stamp 为空时读指针；指针也没有就退回"最新一组"。
    force=False 时，若当前库里的待办比存的那份还多，就不动它
    （安装期间用户又记了事，不能反被旧快照盖掉）。
    """
    res = {'stamp': stamp or read_stamp(root, user) or read_stamp_any(root),
           'ini': 0, 'db': 0, 'kept_current': 0, 'src': ''}
    # 先按用户找；用户名对不上（安装器两段脚本各自探测用户）就不限用户再找一次
    all_ = pairs(root, user) or pairs(root)
    if not all_:
        return res
    pick = None
    if res['stamp']:
        for key, ini, db in all_:
            # key = <用户>-<时间戳>，只比时间戳那一段
            if key == res['stamp'] or key.endswith('-' + res['stamp']):
                pick = (key, ini, db)
                break
    if pick is None:
        # 指定的那一组不在（比如被手工清过）：用最新一组，总比什么都不做强
        pick = all_[0]
        res['fallback'] = 1
    key, src_ini, src_db = pick
    res['stamp'] = key[-15:]      # 时间戳固定 YYYYMMDD-HHMMSS
    res['src'] = root

    try:
        if not os.path.isdir(cfg):
            os.makedirs(cfg)
        if not os.path.isdir(dat):
            os.makedirs(dat)
    except OSError as e:
        res['error'] = 'mkdir: %s' % e
        return res

    if os.path.isfile(src_ini) and os.path.getsize(src_ini) > 0:
        dst = os.path.join(cfg, INI)
        try:
            shutil.copyfile(src_ini, dst)
            _chown(dst, owner)
            res['ini'] = 1
        except OSError as e:
            res['error'] = 'ini: %s' % e

    if os.path.isfile(src_db) and os.path.getsize(src_db) > 0:
        dst = os.path.join(dat, DB)
        now, saved = _rows(dst), _rows(src_db)
        if now > saved and not force:
            res['kept_current'] = now
            res['saved_rows'] = saved
        else:
            _drop_sidecars(dst)
            try:
                shutil.copyfile(src_db, dst)
                _chown(dst, owner)
                res['db'] = 1
                res['rows'] = saved
            except OSError as e:
                res['error'] = 'db: %s' % e
    return res


# ---------------------------------------------------------------- 命令行
def _arg(argv, key, default=''):
    if key in argv:
        i = argv.index(key)
        if i + 1 < len(argv):
            return argv[i + 1]
    return default


def main(argv):
    if not argv:
        sys.stdout.write('usage: carry.py save|load --home DIR [--root DIR] '
                         '[--user NAME] [--stamp S] [--force]\n')
        return FAIL
    act = argv[0]
    home = _arg(argv, '--home', os.path.expanduser('~'))
    user = _arg(argv, '--user', os.environ.get('USER') or 'user')
    cfg = _arg(argv, '--cfg', home_dirs(home)[0])
    dat = _arg(argv, '--dat', home_dirs(home)[1])
    root = _arg(argv, '--root', '')
    if not root:
        root = ('/var/backups/desktop-calendar'
                if os.path.isdir('/var/backups') and os.access('/var/backups', os.W_OK)
                else os.path.join(home, '.desktop-calendar-backup'))
    stamp = _arg(argv, '--stamp', '') or None

    if act == 'save':
        r = save(cfg, dat, root, user, stamp)
        sys.stdout.write('action=save stamp=%s ini=%d db=%d rows=%s dir=%s%s\n'
                         % (r['stamp'], r['ini'], r['db'], r.get('rows', '-'),
                            r['dir'], (' error=' + r['error']) if r.get('error') else ''))
        return OK if (r['ini'] or r['db']) else NOTHING

    if act == 'load':
        r = load(cfg, dat, root, user, stamp,
                 force=('--force' in argv), owner=_arg(argv, '--owner', ''))
        sys.stdout.write('action=load stamp=%s ini=%d db=%d rows=%s kept_current=%d '
                         'fallback=%d%s\n'
                         % (r['stamp'], r['ini'], r['db'], r.get('rows', '-'),
                            r['kept_current'], r.get('fallback', 0),
                            (' error=' + r['error']) if r.get('error') else ''))
        if r.get('error'):
            return FAIL
        return OK if (r['ini'] or r['db'] or r['kept_current']) else NOTHING

    sys.stdout.write('unknown action: %s\n' % act)
    return FAIL


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
