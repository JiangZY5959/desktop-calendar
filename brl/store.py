# -*- coding: utf-8 -*-
"""本地数据存储：待办/记事（SQLite）+ 设置（INI）。不依赖任何云端/账号。"""
import os
import sqlite3
import datetime
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
    date TEXT NOT NULL DEFAULT '',
    repeat INTEGER NOT NULL DEFAULT 0,     -- 0不重复 1每年 2每月 3每周
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
        self._lock = threading.Lock()
        self._apply_defaults()

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
        p = os.path.join(D.config_dir(), 'calendar.ini')
        return QSettings(p, QSettings.IniFormat)

    # ---------------- todo CRUD ----------------
    def _rows(self, cur):
        return [dict(r) for r in cur.fetchall()]

    def add(self, content, category='生活', color='#FFFFFFFF', italic=0, underline=0,
            date='', repeat=0, remind=0, remind_time='09:00'):
        with self._lock:
            with self._conn:
                cur = self._conn.execute(
                    'INSERT INTO todo(content,category,color,italic,underline,date,repeat,'
                    'remind,remind_time,done,created) VALUES(?,?,?,?,?,?,?,?,?,0,?)',
                    (content, category, color, italic, underline, date, repeat,
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
        """某天的待办（含重复规则展开）"""
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
            elif rep == 1:                      # 每年
                hit = base.month == d.month and base.day == d.day
            elif rep == 2:                      # 每月
                hit = base.day == d.day and d >= base
            elif rep == 3:                      # 每周
                hit = base.weekday() == d.weekday() and d >= base
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


STORE = Store()
