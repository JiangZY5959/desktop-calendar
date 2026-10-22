# -*- coding: utf-8 -*-
"""资源定位 / 法定节假日 数据访问层。"""
import os
import threading

from . import lunar as L      # noqa: F401  （供外部按需使用农历能力）
from . import holidays as HD


def app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def res(*p):
    return os.path.join(app_dir(), 'resources', *p)


def data_dir():
    base = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    d = os.path.join(base, 'desktop-calendar')
    if not os.path.isdir(d):
        try:
            os.makedirs(d)
        except OSError:
            d = os.path.expanduser('~/.desktop-calendar')
            if not os.path.isdir(d):
                os.makedirs(d)
    return d


def config_dir():
    base = os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))
    d = os.path.join(base, 'desktop-calendar')
    if not os.path.isdir(d):
        try:
            os.makedirs(d)
        except OSError:
            d = data_dir()
    return d


# ---------------------------------------------------------------- 节假日
class HolidayDB(object):
    """法定节假日：FESTS=节日名, FREE=放假日, DUTY=调休上班日

    数据全部来自内置的 holidays.py，不依赖任何外部数据文件。
    """

    def __init__(self):
        self.fests = {}     # 'YYYYMMDD' -> 描述
        self.free = set()   # 放假日
        self.duty = set()   # 调休上班日
        self._lock = threading.Lock()
        self.reload()

    def reload(self):
        fests, free, duty = dict(HD.FESTS), set(HD.FREE), set(HD.DUTY)
        with self._lock:
            self.fests, self.free, self.duty = fests, free, duty

    @staticmethod
    def _k(d):
        return '%04d%02d%02d' % (d.year, d.month, d.day)

    def fest(self, d):
        return self.fests.get(self._k(d))

    def is_free(self, d):
        """True=休息日(周末或法定假)  False=上班日  None=未知(无调休数据)"""
        wk = d.weekday() >= 5
        k = self._k(d)
        if k in self.free:
            return True
        if k in self.duty:
            return False
        return wk if self._has_year(d.year) else None

    def _has_year(self, year):
        return any(k.startswith('%04d' % year) for k in self.free) or \
               any(k.startswith('%04d' % year) for k in self.duty)


HOLIDAY = HolidayDB()
