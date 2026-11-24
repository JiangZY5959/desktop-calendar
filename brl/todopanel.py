# -*- coding: utf-8 -*-
"""常驻待办面板：嵌在主窗口内、日历左侧的自绘清单。

风格直接复用日历主题（透明背景 + 细边框 + 主题文字色），换主题或改颜色
后这里跟着变，不另起一套颜色设置。列表自己画而不用 QListWidget，避免
UOS 上控件视口露出白底、把半透明效果做脏。
"""
import datetime

from PyQt5.QtCore import Qt, QRect, QRectF, QPoint, QPointF, pyqtSignal
from PyQt5.QtGui import (QPainter, QColor, QPen, QFont, QFontMetrics,
                         QPainterPath, QCursor)
from PyQt5.QtWidgets import QWidget, QMenu, QDialog

from . import theme as T
from . import updatedlg as DLG


def hit_on(row, d):
    """一条待办（含重复规则）是否在某天命中。重复项只存基准一条。"""
    date_s = row.get('date') or ''
    if len(date_s) < 10:
        return False
    try:
        y, m, dd = date_s[:10].split('-')
        base = datetime.date(int(y), int(m), int(dd))
    except Exception:
        return False
    rep = row.get('repeat') or 0
    if rep == 0:
        return base == d
    # 重复项不得超过截止日（老数据回退为开始日+1个月）
    from .store import repeat_end, repeat_day
    end = repeat_end(row)
    if end is not None and d > end:
        return False
    if rep == 1:                       # 每年：月固定，日按当年兜底
        return (base.month == d.month and
                d.day == repeat_day(base.day, d.year, d.month) and d >= base)
    if rep == 2:                       # 每月：日按当月兜底
        return d.day == repeat_day(base.day, d.year, d.month) and d >= base
    if rep == 3:                       # 每周
        return base.weekday() == d.weekday() and d >= base
    return False


def repeat_label(row):
    """重复规则的人话标签；不重复返回空串。"""
    return {0: u'', 1: u'每年', 2: u'每月', 3: u'每周'}.get(row.get('repeat') or 0, u'')


def days_left(row, today=None):
    """距离待办到期的天数：今天 0，未来正数，过期负数。
    重复项按「从今天起下一次命中」算，不拿过去的基准日期当逾期。"""
    today = today or datetime.date.today()
    date_s = row.get('date') or ''
    if len(date_s) < 10:
        return None
    if not (row.get('repeat') or 0):
        try:
            y, m, dd = date_s[:10].split('-')
            return (datetime.date(int(y), int(m), int(dd)) - today).days
        except Exception:
            return None
    for i in range(0, 370):
        if hit_on(row, today + datetime.timedelta(days=i)):
            return i
    return None


class TodoPanel(QWidget):
    """自绘待办清单。changed 信号在数据变动时发给主窗口刷新日历角标。"""

    changed = pyqtSignal()
    # 顶部两行：第一行是标题，第二行是三个时间 chip；
    # 第三行统计条「共 N 项 / 已完成 / 未完成」本身就是完成态筛选按钮，
    # 点哪段就按哪个完成态过滤，与时间 chip 正交叠加。
    FILTERS = (u'今天', u'本周', u'本月')
    STATS = (u'全部', u'已完成', u'未完成')
    HEAD_H = 62
    HEAD1_H = 28
    CHIP_TOP = 30
    STAT_H = 24
    ROW_H = 46

    def __init__(self, store, parent=None):
        QWidget.__init__(self, parent)
        self._store = store
        self._theme = dict(T.ALL_THEMES[0])
        self._clr = {}
        # _filter >=0 用时间 chip；=-1 不限时间。_stat_sel 是完成态筛选：
        # 0=全部 1=已完成 2=未完成（点统计条三段切换），默认全部。
        self._filter = -1
        self._stat_sel = 0
        self._rows = []
        self._hover = -1
        self._sel = -1
        self._scroll = 0
        self.setMinimumWidth(180)         # 太窄就没法读，拖窗口时保底
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._ctx_menu)
        self.set_theme(self._theme)
        self.reload()

    def sizeHint(self):
        # 出厂宽度约占日历的 1/3：默认窗口 1004 宽时面板 248px，日历仍有 750px
        from PyQt5.QtCore import QSize
        return QSize(248, 600)

    # ------------------------------------------------ 主题 / 外观
    def set_theme(self, cfg):
        self._theme = dict(cfg or {})
        self._clr = {
            'txt': T.qcolor(self._theme.get('txtclr', '#FFFFFF')),
            'week': T.qcolor(self._theme.get('weekclr', '#FFFFFF')),
            'grid': T.qcolor(self._theme.get('gridbgndclr', '#33FFFFFF')),
            'border': T.qcolor(self._theme.get('borderinclr', '#30FFFFFF')),
        }
        self.update()

    # ------------------------------------------------ 数据
    def set_filter(self, idx):
        """点时间 chip（今天/本周/本月）；完成态下拉保持当前选择，两者叠加。

        -1 = 不限时间。默认就是 -1；点已选中的 chip 再点一次可取消回 -1。
        """
        idx = max(-1, min(len(self.FILTERS) - 1, int(idx)))
        if idx != self._filter:
            self._filter = idx
            self._sel = -1
            self._scroll = 0
            self.reload()

    def set_stat(self, idx):
        """点统计条某段切换完成态筛选（0=全部 1=已完成 2=未完成）。"""
        idx = max(0, min(len(self.STATS) - 1, int(idx)))
        if idx != self._stat_sel:
            self._stat_sel = idx
            self._sel = -1
            self._scroll = 0
            self.reload()

    def filter(self):
        return self._filter

    def stat_sel(self):
        return self._stat_sel

    def date_span(self):
        """时间 chip 覆盖的日期集合（含重复项展开）；_filter=-1 返回 None 不限时间。"""
        today = datetime.date.today()
        if self._filter == 0:                        # 今天
            return {today}
        if self._filter == 1:                        # 本周（周一起）
            start = today - datetime.timedelta(days=today.weekday())
            return {start + datetime.timedelta(days=i) for i in range(7)}
        if self._filter == 2:                        # 本月
            start = today.replace(day=1)
            import calendar
            n = calendar.monthrange(start.year, start.month)[1]
            return {start + datetime.timedelta(days=i) for i in range(n)}
        return None                                  # 不限时间

    def reload(self):
        span = self.date_span()
        # base_rows = 仅按时间 chip 过滤的完整集合，统计三段都基于它，
        # 这样点「已完成」后仍能看全三条数字，不会被自己筛掉。
        base = []
        for r in self._store.all(order='date'):
            if span is None or any(hit_on(r, d) for d in span):
                base.append(r)
        self._base_rows = base
        out = []
        for r in base:
            if self._stat_sel == 1 and not r.get('done'):
                continue
            if self._stat_sel == 2 and r.get('done'):
                continue
            out.append(r)
        self._rows = out
        if self._sel >= len(out):
            self._sel = -1
        self.update()

    def set_selected_date(self, d):
        """主窗口选中日期变化时，让「今天」之外的视图不必跟随，只高亮同日项。"""
        self._focus_date = d
        self.update()

    def _toggle_done(self, row):
        self._store.update(row['id'], done=0 if row.get('done') else 1)
        self.reload()
        self.changed.emit()

    def _stat_counts(self):
        """统计条三段数字，基于时间过滤后的完整集合（不受完成态筛选影响）。"""
        rows = getattr(self, '_base_rows', self._rows)
        done = sum(1 for r in rows if r.get('done'))
        return len(rows), done, len(rows) - done

    # ------------------------------------------------ 命中测试
    def _row_at(self, y):
        i = int((y - self.HEAD_H - self.STAT_H) / self.ROW_H) + self._scroll
        if i < 0 or i >= len(self._rows):
            return -1
        return i

    def _stat_rects(self):
        """统计条三段的命中矩形。"""
        seg = self.width() / 3.0
        y0 = self.HEAD_H
        return [QRectF(6 + i * seg, y0 + 1, seg, self.STAT_H - 3)
                for i in range(3)]

    def _filter_chip_rects(self):
        """第二行三个快捷 chip，均分整行宽度，不再跟标题抢位置。"""
        pad, gap = 6, 4
        avail = self.width() - pad * 2 - gap * (len(self.FILTERS) - 1)
        w = max(34, avail // len(self.FILTERS))
        h = self.HEAD_H - self.CHIP_TOP - 4
        return [(i, QRect(pad + i * (w + gap), self.CHIP_TOP, w, h))
                for i in range(len(self.FILTERS))]

    # ------------------------------------------------ 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        self._draw_head(p)
        self._draw_stat(p)
        self._draw_rows(p)
        p.end()

    def _draw_head(self, p):
        c = self._clr
        # 标题换成思源黑体（原来落在宋体上，一笔一画太硬）
        f = QFont()
        f.setFamily(u'思源黑体')
        f.setPointSizeF(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(c['week']))
        p.drawText(QRectF(6, 0, 84, self.HEAD1_H), Qt.AlignVCenter, u'待办列表')

        # 第二行：三个快捷 chip
        for i, r in self._filter_chip_rects():
            cr = QRectF(r)
            if i == self._filter:
                path = QPainterPath()
                path.addRoundedRect(cr.adjusted(0.5, 0.5, -0.5, -0.5), 6, 6)
                bg = QColor(c['grid'])
                bg.setAlpha(max(bg.alpha(), 90))
                p.fillPath(path, bg)
            ff = QFont()
            ff.setFamily(u'思源黑体')
            ff.setPointSizeF(9)
            p.setFont(ff)
            col = QColor(c['txt'])
            if i != self._filter:
                col.setAlpha(max(120, col.alpha()))
            p.setPen(QPen(col))
            p.drawText(cr, Qt.AlignCenter, self.FILTERS[i])

        p.setPen(QPen(c['border']))
        p.drawLine(QPoint(6, self.HEAD_H - 1),
                   QPoint(self.width() - 6, self.HEAD_H - 1))

    def _draw_stat(self, p):
        """统计条本身就是完成态筛选：共/已完成/未完成三段，点哪段筛哪段。"""
        c = self._clr
        total, done, undone = self._stat_counts()
        labels = (u'共 %d 项' % total, u'已完成 %d' % done, u'未完成 %d' % undone)
        rects = self._stat_rects()
        f = QFont()
        f.setFamily(u'思源黑体')
        f.setPointSizeF(8)
        for i, r in enumerate(rects):
            if i == self._stat_sel:            # 选中段高亮填充
                path = QPainterPath()
                path.addRoundedRect(r.adjusted(1, 0, -1, 0), 5, 5)
                bg = QColor(c['grid'])
                bg.setAlpha(max(bg.alpha(), 110))
                p.fillPath(path, bg)
            col = QColor(c['week'])
            if i != self._stat_sel:
                col.setAlpha(max(120, col.alpha()))
            p.setFont(f)
            p.setPen(QPen(col))
            p.drawText(r, Qt.AlignCenter, labels[i])

    def _draw_rows(self, p):
        c = self._clr
        top = self.HEAD_H + self.STAT_H
        bottom = self.height()
        n = len(self._rows)
        font_date = QFont()
        font_date.setPointSizeF(8)
        font_body = QFont()
        font_body.setPointSizeF(10)
        for k in range(n - self._scroll):
            idx = self._scroll + k
            row = self._rows[idx]
            y = top + k * self.ROW_H
            if y > bottom:
                break
            rect = QRectF(0, y, self.width(), self.ROW_H)
            if idx == self._hover:
                bg = QColor(c['grid'])
                bg.setAlpha(max(bg.alpha(), 55))
                path = QPainterPath()
                path.addRoundedRect(rect.adjusted(2, 1, -2, -1), 5, 5)
                p.fillPath(path, bg)

            done = bool(row.get('done'))
            # 勾选圆圈（cx 横向固定，cy 随行下移）
            cx, cy, rad = 17, y + self.ROW_H / 2.0, 6
            pen = QPen(c['txt'])
            pen.setWidthF(1.3)
            p.setPen(pen)
            if done:
                b = QColor(c['txt'])
                b.setAlpha(max(b.alpha(), 190))
                p.setBrush(b)
            else:
                p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))
            if done:
                chk = QPen(QColor(c['grid']))
                chk.setWidthF(1.6)
                p.setPen(chk)
                p.drawLine(QPointF(cx - 3, cy), QPointF(cx - 0.5, cy + 2.4))
                p.drawLine(QPointF(cx - 0.5, cy + 2.4), QPointF(cx + 3.4, cy - 2.4))

            # 内容文字（第一行：正文；第二行：日期 + 重复标记）
            tx = 32
            tw = self.width() - tx - 8
            txt_col = QColor(c['txt'])
            if done:
                txt_col.setAlpha(max(90, int(txt_col.alpha() * 0.55)))
            p.setFont(font_body)
            p.setPen(QPen(txt_col))
            content = row.get('content') or u''
            fm = QFontMetrics(font_body)
            elided = fm.elidedText(content, Qt.ElideRight, int(tw))
            p.drawText(QRectF(tx, y + 3, tw, 20), Qt.AlignVCenter, elided)
            if done:
                # 删除线
                w = min(fm.width(elided), int(tw))
                p.drawLine(QPointF(tx, y + 13), QPointF(tx + w, y + 13))
            sub = row.get('date') or u'未设日期'
            rep = repeat_label(row)
            if rep:
                sub = u'%s · %s' % (sub, rep)
            # 剩余天数右对齐在日期行末尾；已完成的待办不显示
            left = days_left(row)
            show_left = (not done and left is not None)
            rem_w = 66 if show_left else 0
            p.setFont(font_date)
            sc = QColor(c['week'])
            sc.setAlpha(max(110, sc.alpha()))
            p.setPen(QPen(sc))
            fm_date = QFontMetrics(font_date)
            p.drawText(QRectF(tx, y + 22, tw - rem_w, 18), Qt.AlignVCenter,
                       fm_date.elidedText(sub, Qt.ElideRight, int(tw - rem_w)))
            if show_left:
                rem = u'剩余 %d 天' % max(0, left)   # 当日=0，逾期也按 0 显示
                p.drawText(QRectF(tx + tw - rem_w, y + 22, rem_w, 18),
                           Qt.AlignRight | Qt.AlignVCenter, rem)

            # 分隔线
            p.setPen(QPen(c['border']))
            p.drawLine(QPoint(6, int(y + self.ROW_H - 1)),
                       QPoint(self.width() - 6, int(y + self.ROW_H - 1)))

        if n == 0:
            col = QColor(c['week'])
            col.setAlpha(150)
            p.setPen(QPen(col))
            f = QFont()
            f.setPointSizeF(10)
            p.setFont(f)
            p.drawText(QRectF(0, top, self.width(), 120), Qt.AlignCenter,
                       u'暂无待办\n双击或右键添加')

    # ------------------------------------------------ 交互
    def mouseMoveEvent(self, ev):
        i = self._row_at(ev.pos().y())
        if i != self._hover:
            self._hover = i
            self.update()
        QWidget.mouseMoveEvent(self, ev)

    def leaveEvent(self, ev):
        self._hover = -1
        self.update()
        QWidget.leaveEvent(self, ev)

    def wheelEvent(self, ev):
        n = len(self._rows)
        visible = max(1, int((self.height() - self.HEAD_H - self.STAT_H) / self.ROW_H))
        maxscroll = max(0, n - visible)
        step = -1 if ev.angleDelta().y() > 0 else 1
        self._scroll = max(0, min(maxscroll, self._scroll + step))
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        if ev.pos().y() < self.HEAD_H:
            for i, r in self._filter_chip_rects():
                if r.contains(ev.pos()):
                    # 再点一次已选中的 chip → 取消时间限制（回到不限时间）
                    self.set_filter(-1 if i == self._filter else i)
                    return
            return
        # 统计条三段：点哪段按哪个完成态筛选
        if self.HEAD_H <= ev.pos().y() < self.HEAD_H + self.STAT_H:
            for i, r in enumerate(self._stat_rects()):
                if r.contains(ev.pos()):
                    self.set_stat(i)
                    return
            return
        i = self._row_at(ev.pos().y())
        if i < 0:
            self._sel = -1
            self.update()
            return
        row = self._rows[i]
        if ev.pos().x() <= 30:          # 圆圈：切换完成
            self._toggle_done(row)
            return
        self._sel = i
        self.update()

    def mouseDoubleClickEvent(self, ev):
        if ev.pos().y() < self.HEAD_H + self.STAT_H:
            return
        i = self._row_at(ev.pos().y())
        if i >= 0:
            self._edit(self._rows[i])
        else:
            self._add()

    def _ctx_menu(self, pos):
        m = QMenu(self)
        i = self._row_at(pos.y())
        if i >= 0:
            row = self._rows[i]
            m.addAction(u'编辑待办', lambda: self._edit(row))
            m.addAction(u'取消完成' if row.get('done') else u'标记完成',
                        lambda: self._toggle_done(row))
            m.addSeparator()
            m.addAction(u'删除待办', lambda: self._delete(row))
        else:
            m.addAction(u'添加待办', self._add)
        m.exec_(self.mapToGlobal(pos))

    def _add(self):
        from .todo import TodoEditDialog
        dlg = TodoEditDialog(self._store, datetime.date.today(), None, self)
        if dlg.exec_() == QDialog.Accepted:
            self._store.add(**dlg.result_data)
            self.reload()
            self.changed.emit()

    def _edit(self, row):
        from .todo import TodoEditDialog
        t = self._store.get(row['id'])
        if not t:
            return
        dlg = TodoEditDialog(self._store, None, t, self)
        if dlg.exec_() == QDialog.Accepted:
            self._store.update(row['id'], **dlg.result_data)
            self.reload()
            self.changed.emit()

    def _delete(self, row):
        if not DLG.confirm(self, u'删除待办',
                           u'确定删除这条待办吗？\n\n%s' % (row.get('content') or ''),
                           ok=u'删除'):
            return
        self._store.remove(row['id'])
        self.reload()
        self.changed.emit()
