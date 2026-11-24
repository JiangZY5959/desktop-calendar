# -*- coding: utf-8 -*-
"""本地数据存储：待办/记事（SQLite）+ 设置（INI）。不依赖任何云端/账号。"""
import os
import sqlite3
import datetime
import calendar
import threading

try:
    from PyQt5.QtCore import QSettings
except ImportError:      # 允许无 Qt 环境下做核心逻辑自测
    QSettings = None

from . import data as D

SCHEMA = """
CREATE TABLE IF NOT EXISTS todo(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT '生活',
    color TEXT NOT NULL DEFAULT '#FFFFFFFF',
    italic INTEGER NOT NULL DEFAULT 0,
    underline INTEGER NOT NULL DEFAULT 0,
    date TEXT NOT NULL DEFAULT '',         -- 单次=到期日；重复=开始日
    repeat INTEGER NOT NULL DEFAULT 0,     -- 0不重复 1每年 2每月 3每周
    end_date TEXT NOT NULL DEFAULT '',     -- 重复的截止日（必填；老数据迁移为开始日+1月）
    remind INTEGER NOT NULL DEFAULT 0,     -- 0不提醒 1前一天 2当天
    remind_time TEXT NOT NULL DEFAULT '09:00',
    done INTEGER NOT NULL DEFAULT 0,
    created TEXT NOT NULL DEFAULT ''
);
"""


class Store(object):
    def __init__(self):
        path = os.path.join(D.data_dir(), 'calendar.db')
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.executescript(SCHEMA)
            self._migrate_end_date()
        self._lock = threading.Lock()
        self._qs = None
        self._apply_defaults()

    @staticmethod
    def plus_month(date_s, months=1):
        """日期字符串加 N 个月，月末自动收敛（1/31 +1月 = 2/28）。"""
        try:
            y, m, d = date_s[:10].split('-')
            y, m, d = int(y), int(m), int(d)
        except (ValueError, AttributeError):
            return ''
        total = y * 12 + (m - 1) + months
        ny, nm = total // 12, total % 12 + 1
        nday = min(d, calendar.monthrange(ny, nm)[1])
        return datetime.date(ny, nm, nday).isoformat()

    def _migrate_end_date(self):
        """老库升级：补 end_date 列；无截止日的重复项按开始日+1个月处理。

        用户拍板：老数据的重复项没有结束日期，统一按「重复一个月」兼容，
        新界面里再编辑时能看到这个截止日并可自行改。单次项保持空串。
        """
        cols = [r[1] for r in self._conn.execute('PRAGMA table_info(todo)')]
        if 'end_date' not in cols:
            self._conn.execute(
                "ALTER TABLE todo ADD COLUMN end_date TEXT NOT NULL DEFAULT ''")
        rows = self._conn.execute(
            "SELECT id, date FROM todo WHERE repeat > 0 AND (end_date IS NULL OR end_date='')"
        ).fetchall()
        for r in rows:
            end = self.plus_month(r['date'] or '')
            if end:
                self._conn.execute('UPDATE todo SET end_date=? WHERE id=?',
                                   (end, r['id']))

    # ---------------- settings ----------------
    def _apply_defaults(self):
        """首次运行写入出厂默认设置（已存在的键不动）。

        默认值来自 defaults.DEFAULTS，内容即您当前这套配置：
        主题、背景/网格/今日格颜色、边框透明度等。
        """
        from . import defaults as DF
        st = self.settings()
        if st is None:
            return
        changed = False
        for k, v in DF.DEFAULTS.items():
            if not st.contains(k):
                st.setValue(k, v)
                changed = True
        if changed:
            st.sync()

    def settings(self):
        if QSettings is None:
            return None
        # 进程内共享一个 QSettings 实例。
        # 之前每次调用都新建，新对象会从文件重新读取；一旦文件在进程
        # 存活期间被外部动过（比如升级时被清空再恢复），退出时 sync
        # 就只写后加的那几个键，其余设置全部丢失。
        if self._qs is None:
            p = os.path.join(D.config_dir(), 'calendar.ini')
            self._qs = QSettings(p, QSettings.IniFormat)
        return self._qs

    # ---------------- todo CRUD ----------------
    def _rows(self, cur):
        return [dict(r) for r in cur.fetchall()]

    def add(self, content, category='生活', color='#FFFFFFFF', italic=0, underline=0,
            date='', repeat=0, end_date='', remind=0, remind_time='09:00'):
        with self._lock:
            with self._conn:
                cur = self._conn.execute(
                    'INSERT INTO todo(content,category,color,italic,underline,date,repeat,'
                    'end_date,remind,remind_time,done,created) VALUES(?,?,?,?,?,?,?,?,?,?,0,?)',
                    (content, category, color, italic, underline, date, repeat, end_date,
                     remind, remind_time, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                return cur.lastrowid

    def update(self, tid, **kw):
        if not kw:
            return
        cols = ','.join('%s=?' % k for k in kw)
        vals = list(kw.values()) + [tid]
        with self._lock:
            with self._conn:
                self._conn.execute('UPDATE todo SET %s WHERE id=?' % cols, vals)

    def remove(self, tid):
        with self._lock:
            with self._conn:
                self._conn.execute('DELETE FROM todo WHERE id=?', (tid,))

    def get(self, tid):
        with self._lock:
            cur = self._conn.execute('SELECT * FROM todo WHERE id=?', (tid,))
            r = cur.fetchone()
        return dict(r) if r else None

    def all(self, only_undone=False, category=None, keyword=None, order='date'):
        sql = 'SELECT * FROM todo'
        cond, args = [], []
        if only_undone:
            cond.append('done=0')
        if category:
            cond.append('category=?')
            args.append(category)
        if keyword:
            cond.append("content LIKE ?")
            args.append('%' + keyword + '%')
        if cond:
            sql += ' WHERE ' + ' AND '.join(cond)
        if order == 'date':
            sql += " ORDER BY CASE WHEN date='' THEN 1 ELSE 0 END, date, id"
        else:
            sql += ' ORDER BY id DESC'
        with self._lock:
            cur = self._conn.execute(sql, args)
            return self._rows(cur)

    def for_date(self, d):
        """某天的待办（含重复规则展开）

        年/月重复的「日」用 repeat_day 求解：基准日在该月不存在时
        （闰日 2/29 遇到平年、31 号遇到小月）兜底到当月最后一天，
        避免整月/整年凭空消失。日历角标、当日清单、提醒都走这里。
        """
        out = []
        for r in self.all(only_undone=False):
            if not r['date']:
                continue
            y, m, dd = r['date'][:10].split('-')
            base = datetime.date(int(y), int(m), int(dd))
            rep = r['repeat']
            hit = False
            if rep == 0:
                hit = base == d
            else:
                end = repeat_end(r)             # 重复项不得超过截止日
                in_range = end is None or d <= end
                if rep == 1:                    # 每年：月固定，日按当年兜底
                    hit = (d.month == base.month and
                           d.day == repeat_day(base.day, d.year, d.month) and
                           d >= base)
                elif rep == 2:                  # 每月：日按当月兜底
                    hit = (d.day == repeat_day(base.day, d.year, d.month) and
                           d >= base)
                elif rep == 3:                  # 每周
                    hit = base.weekday() == d.weekday() and d >= base
                hit = hit and in_range
            if hit:
                row = dict(r)
                row['base_date'] = base.isoformat()
                out.append(row)
        return out

    def counts_by_date(self, d0, d1):
        """[d0, d1] 区间内每天未完成待办数（含重复展开），返回 {date: n}"""
        out = {}
        n = (d1 - d0).days + 1
        for i in range(n):
            d = d0 + datetime.timedelta(days=i)
            c = len(self.for_date(d))
            if c:
                out[d.isoformat()] = c
        return out


def repeat_day(base_day, year, month):
    """重复项在 (year, month) 的到期「日」：基准日存在就用它，否则兜底到月末。

    - 每年重复遇闰日 2/29：平年 2 月只有 28 天 -> 落到 28 日
    - 每月重复遇大月末 31 号：小月只有 30 天 -> 落到 30 日；2 月落到 28/29 日
    这样重复待办不会因为某个月/某一年没有那一天而整段消失。
    """
    last = calendar.monthrange(year, month)[1]
    return min(int(base_day), last)


def fallback_reason(repeat, base_day, base_month=0):
    """重复项是否会发生日期兜底，返回人话原因；不需要兜底返回空串。

    repeat: 1 每年 / 2 每月；base_day 基准日；base_month 基准月（年重复用得到）。
    文案区分「闰年 2/29」和「X 月没有 31 日」两种，供编辑窗保存时提示。
    """
    if repeat == 1:                       # 每年：只有 2/29 会撞平年
        if base_month == 2 and base_day == 29:
            return (u'2 月 29 日只在闰年出现，平年的 2 月没有 29 日；'
                    u'这些年份已自动按 2 月 28 日（月底最后一天）提醒。')
        return u''
    if repeat == 2:                       # 每月：29/30/31 号会撞小月
        if base_day == 31:
            return (u'部分月份没有 31 日（如 4、6、9、11 月，2 月更少）；'
                    u'这些月份已自动按当月最后一天提醒。')
        if base_day == 30:
            return (u'2 月没有 30 日（平年只有 28 天、闰年 29 天）；'
                    u'2 月已自动按当月最后一天提醒。')
        if base_day == 29:
            return (u'平年的 2 月没有 29 日（只有 28 天）；'
                    u'这些月份已自动按当月最后一天提醒。')
    return u''


def repeat_end(row):
    """重复项的截止日期；空则回退为开始日+1个月（老数据兼容）。"""
    s = (row.get('end_date') or '')[:10]
    if len(s) == 10:
        try:
            y, m, d = s.split('-')
            return datetime.date(int(y), int(m), int(d))
        except (ValueError, AttributeError):
            pass
    fallback = Store.plus_month(row.get('date') or '')
    if fallback:
        y, m, d = fallback.split('-')
        return datetime.date(int(y), int(m), int(d))
    return None


STORE = Store()
