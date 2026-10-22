# -*- coding: utf-8 -*-
"""月历 / 周历 表格（还原 UICalTable 的自绘逻辑）。

支持：
- 月视图 / 周视图
- 显示第几周（第一周起点：1月1日 / 周一）
- 鼠标悬停格子弹 tips 提示
- 各元素颜色与透明度（主题 + 用户覆盖）
- 清单字体大小
"""
import datetime

from PyQt5.QtCore import Qt, QRectF, QPointF, QRect, pyqtSignal, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QFont, QFontMetrics, QPainterPath
from PyQt5.QtWidgets import QWidget, QMenu, QAction, QToolTip

from . import lunar as L
from . import data as D
from . import theme as T

WEEK_HEAD = [u'周日', u'周一', u'周二', u'周三', u'周四', u'周五', u'周六']
COLOR_KEYS = ('txtclr', 'weekclr', 'jiericlr', 'todayclr',
              'mainbg', 'gridbg', 'weekgridbg', 'borderin')


class CalTable(QWidget):
    """月历表格。signal: daySelected(date) / dayActivated(date) / monthChanged(date)"""
    daySelected = pyqtSignal(object)
    dayActivated = pyqtSignal(object)
    monthChanged = pyqtSignal(object)

    def __init__(self, parent=None):
        QWidget.__init__(self, parent)
        self.setMouseTracking(True)
        self._view = 'month'          # month / week
        self._month = None            # datetime.date 当月任意一天
        self._today = datetime.date.today()
        self._selected = self._today
        self._hover = None
        self._cells = []              # [(date, rect)]
        self._counts = {}
        self._todos = {}
        self._show_weekend = True
        self._show_lunnar = True
        self._show_jieri = True
        self._show_line = True
        self._show_ban = True
        self._show_week = False       # 显示第几周
        self._show_tips = True        # 悬停 tips
        self._weekstart = 'jan1'      # jan1 / mon
        self._qscale = 11             # 清单字体大小(pt)
        self._theme = T.ALL_THEMES[0]
        self._clr = {}                # 当前生效颜色（含覆盖）
        self._scale = 1.0
        self._firstday = 0            # 0=周日 1=周一
        self.set_theme(T.ALL_THEMES[0])

    # ------------------------------------------------ 配置
    def _theme_colors(self, cfg):
        return {
            'txtclr': T.qcolor(cfg.get('txtclr')),
            'weekclr': T.qcolor(cfg.get('weekclr')),
            'jiericlr': T.qcolor(cfg.get('jiericlr')),
            'todayclr': T.qcolor(cfg.get('todayclr')),
            'mainbg': T.qcolor(cfg.get('mainbgndclr'), QColor(Qt.transparent)),
            'gridbg': T.qcolor(cfg.get('gridbgndclr'), QColor(Qt.transparent)),
            'weekgridbg': T.qcolor(cfg.get('weekgridbgndclr'), QColor(Qt.transparent)),
            'borderin': T.qcolor(cfg.get('borderinclr'), QColor(255, 255, 255, 40)),
        }

    def set_theme(self, cfg, overrides=None):
        self._theme = cfg
        self._clr = self._theme_colors(cfg)
        if overrides:
            for k, c in overrides.items():
                if k in self._clr and c is not None:
                    self._clr[k] = QColor(c)
        self.update()

    def set_color(self, key, color):
        """单个颜色覆盖（key 见 COLOR_KEYS；color=None 恢复主题色）"""
        if key in self._clr:
            self._clr[key] = QColor(color) if color is not None \
                else self._theme_colors(self._theme).get(key, QColor(Qt.white))
            self.update()

    def set_scale(self, s):
        self._scale = max(0.6, min(2.0, s))
        self.update()

    def set_options(self, weekend=None, lunnar=None, jieri=None, line=None, ban=None,
                    firstday=None, week=None, tips=None, weekstart=None, qscale=None):
        if weekend is not None:
            self._show_weekend = weekend
        if lunnar is not None:
            self._show_lunnar = lunnar
        if jieri is not None:
            self._show_jieri = jieri
        if line is not None:
            self._show_line = line
        if ban is not None:
            self._show_ban = ban
        if week is not None:
            self._show_week = week
        if tips is not None:
            self._show_tips = tips
        if weekstart is not None:
            self._weekstart = weekstart
        if qscale is not None:
            self._qscale = max(8, min(16, int(qscale)))
        self.rebuild()

    def set_view(self, v):
        self._view = v
        self.rebuild()

    def view(self):
        return self._view

    # ------------------------------------------------ 数据
    def set_month(self, d):
        self._month = datetime.date(d.year, d.month, 1)
        self.rebuild()
        self.monthChanged.emit(self._month)

    def month(self):
        return self._month

    def set_selected(self, d):
        self._selected = d
        self.daySelected.emit(d)
        self.update()

    def selected(self):
        return self._selected

    def set_counts(self, counts):
        self._counts = counts
        self.update()

    def set_todos(self, todos):
        self._todos = todos
        self.update()

    def refresh_today(self):
        self._today = datetime.date.today()
        self.rebuild()

    def rebuild(self):
        if self._month is None:
            self._month = datetime.date(self._today.year, self._today.month, 1)
        self.update()

    # ------------------------------------------------ 周数
    def week_no(self, d):
        if self._weekstart == 'mon':
            return d.isocalendar()[1]
        jan1 = datetime.date(d.year, 1, 1)
        return (d - jan1).days // 7 + 1

    # ------------------------------------------------ 布局
    def _head_h(self):
        return int(30 * self._scale)

    def _week_col_w(self, w):
        return int(26 * self._scale) if self._show_week else 0

    def _days(self):
        """返回要显示的日期列表"""
        if self._view == 'week':
            start = self._selected - datetime.timedelta(days=(self._selected.weekday() + 1) % 7)
            return [start + datetime.timedelta(days=i) for i in range(7)]
        y, m = self._month.year, self._month.month
        first = datetime.date(y, m, 1)
        if self._firstday == 1:
            lead = first.weekday()                 # 周一为第一列
        else:
            lead = (first.weekday() + 1) % 7       # 周日为第一列
        start = first - datetime.timedelta(days=lead)
        out = []
        for i in range(42):
            out.append(start + datetime.timedelta(days=i))
        return out

    # ------------------------------------------------ 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), self._clr['mainbg'])
        head = self._head_h()
        wk_w = self._week_col_w(w)
        cols, rows = 7, 6
        if self._view == 'week':
            rows = 1
        cw = (w - wk_w) / 7.0
        ch = (h - head) / float(rows)
        # 第几周列
        if self._show_week:
            p.setFont(T.font(max(8, 10 * self._scale)))
            p.setPen(QPen(QColor(self._clr['weekclr'])))
            days = self._days()
            for r in range(rows):
                d = days[r * 7]
                rect = QRectF(0, head + r * ch, wk_w - 4, ch)
                p.drawText(rect, Qt.AlignCenter | Qt.AlignVCenter,
                           str(self.week_no(d + datetime.timedelta(days=3))))
        # 表头
        for i, name in enumerate(WEEK_HEAD):
            r = QRectF(wk_w + i * cw, 0, cw, head)
            if self._show_line:
                p.fillRect(r, self._clr['weekgridbg'])
            idx = (i - self._firstday) % 7
            f = T.font(max(9, 12 * self._scale), bold=(idx == 0 or idx == 6))
            p.setFont(f)
            p.setPen(QPen(self._clr['weekclr']))
            p.drawText(r, Qt.AlignCenter | Qt.AlignVCenter, name)
        # 网格线
        if self._show_line:
            pen = QPen(self._clr['borderin'])
            pen.setWidthF(0.6)
            p.setPen(pen)
            for i in range(1, 7):
                x = wk_w + i * cw
                p.drawLine(QPointF(x, 0), QPointF(x, h))
            for j in range(1, rows + 1):
                p.drawLine(QPointF(0, head + j * ch), QPointF(w, head + j * ch))
        # 单元格
        self._cells = []
        days = self._days()
        for k, d in enumerate(days):
            r, c = divmod(k, 7)
            rect = QRectF(wk_w + c * cw, head + r * ch, cw, ch)
            self._cells.append((d, rect))
            self._paint_cell(p, d, rect)
        # 悬停高亮
        if self._hover is not None:
            for d, rect in self._cells:
                if d == self._hover:
                    p.setPen(QPen(QColor(255, 255, 255, 70)))
                    p.setBrush(Qt.NoBrush)
                    p.drawRect(rect.adjusted(1, 1, -1, -1))
                    break

    def _paint_cell(self, p, d, rect):
        x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
        is_cur = (d.month == self._month.month) if self._view == 'month' else True
        is_today = d == self._today
        is_sel = d == self._selected
        free = D.HOLIDAY.is_free(d)
        if self._show_line:
            p.fillRect(rect, self._clr['gridbg'])
        # 文字颜色
        clr = QColor(self._clr['txtclr'])
        if not is_cur:
            clr.setAlpha(int(clr.alpha() * 0.45))
        elif free and self._show_jieri:
            clr = QColor(self._clr['jiericlr'])
        # 统一内边距，避免文字紧贴格子边框
        pad_x = 10 if w >= 64 else 6
        pad_y = 6 if h >= 40 else 4
        # 先取副文字并计算两行高度，便于整体排版
        sub, subclr = self._sub_text(d) if self._show_lunnar else ('', None)
        fs = max(11, min(17 * self._scale, (h - 2 * pad_y - 13) / 2.4))
        num_h = fs * 1.45
        sub_h = max(9, min(14 * self._scale, h - 2 * pad_y - num_h)) if sub else 0
        # 高亮块：今日格与选中格都整格填充——不留边距、不画圆角，
        # 两种状态可以叠加（选中的今天会同时铺今日色 + 一层白）
        if is_today:
            p.fillRect(QRectF(x, y, w, h), self._clr['todayclr'])
        if is_sel:
            p.fillRect(QRectF(x, y, w, h), QColor(255, 255, 255, 52))
        # 文字横向位置与是否高亮无关——点选时文字不能再位移
        tx = x + pad_x
        tw = max(0.0, w - 2 * pad_x)
        # 垂直布局：所有格子一律顶部对齐——今日/选中格不下移，
        # 否则同一行里不同格子的日期会高低错落。
        todos = self._todos.get(d.isoformat()) or []
        block_h = num_h + (sub_h + 1 if sub else 0)
        ty0 = y + pad_y
        # 日数字
        p.setFont(T.font(fs, bold=is_today))
        p.setPen(QPen(clr))
        p.drawText(QRectF(tx, ty0, tw, num_h), Qt.AlignLeft | Qt.AlignVCenter, str(d.day))
        # 农历 / 节气 / 节日（副行字号随剩余空间收缩，保证完整显示）
        if sub:
            p.setFont(T.font(max(8, min(11 * self._scale, sub_h * 0.75))))
            p.setPen(QPen(QColor(subclr) if not isinstance(subclr, QColor) else subclr))
            srect = QRectF(tx, ty0 + num_h + 1, tw, sub_h)
            p.drawText(srect, Qt.AlignLeft | Qt.AlignVCenter,
                       p.fontMetrics().elidedText(sub, Qt.ElideRight, int(tw)))
        # 班/休
        if self._show_ban and free is not None:
            badge = None
            if free and d.weekday() < 5:
                badge = u'休'
            elif (not free) and d.weekday() >= 5:
                badge = u'班'
            if badge:
                bw, bh = 20 * self._scale, 14 * self._scale
                br = QRectF(x + w - bw - 10, y + 8, bw, bh)
                path = QPainterPath()
                path.addRoundedRect(br, 3, 3)
                p.fillPath(path, QColor(0xF9, 0x4D, 0x4D, 230))
                p.setFont(T.font(max(7, 9 * self._scale), bold=True))
                p.setPen(QPen(QColor(Qt.white)))
                p.drawText(br, Qt.AlignCenter, badge)
        # 待办：紧接日期/农历下方自上而下排列（不再从格子底部往上堆），
        # 条数按剩余高度自动裁剪，保证任何尺寸下都不会溢出格子。
        if todos:
            # 待办字号单位是「磅」，行高必须按字体真实度量计算：
            # 早期用「字号+3」当行高，用户把字号调大后行高不够，
            # 文字就会被下一行或格子下沿裁掉（表现为显示不全）。
            top = ty0 + block_h + 1
            avail = (y + h - pad_y) - top
            target_fs = max(8, self._qscale * self._scale)
            # 自适应：先用设定字号尝试把条目一条条全部列出；
            # 装不下就逐级缩小字号（最低 7pt），而不是折叠成「共 N 项」
            todo_fs, line_h, maxn = target_fs, 0.0, 0
            fs = target_fs
            while fs >= 7:
                lh = float(QFontMetrics(T.font(fs)).height() + 1)
                if lh * len(todos) <= avail:
                    todo_fs, line_h, maxn = fs, lh, len(todos)
                    break
                fs -= 1
            shown = list(todos)
            overflow = False
            if maxn < len(todos):
                # 缩到下限仍放不下：按最小字号能容纳的行数尽量列，
                # 末行留一个省略提示（不写数量，条目信息不丢失）
                min_fs = 7
                lh = float(QFontMetrics(T.font(min_fs)).height() + 1)
                n = int(avail // lh) if avail >= lh else 0
                if n >= 1:
                    overflow = n < len(todos)
                    shown = list(todos[:n - 1]) if overflow else list(todos[:n])
                    todo_fs, line_h, maxn = min_fs, lh, len(shown)
                else:
                    maxn = 0
            if maxn >= 1:
                p.setFont(T.font(todo_fs))
                fm = p.fontMetrics()
                for i, t in enumerate(shown):
                    tr = QRectF(x + pad_x, top + i * line_h, w - 2 * pad_x, line_h)
                    tc = T.qcolor(t.get('color'), QColor(Qt.white))
                    if t.get('done'):
                        tc.setAlpha(140)
                    p.setPen(QPen(tc))
                    mark = u'✓ ' if t.get('done') else u'• '
                    p.drawText(tr, Qt.AlignLeft | Qt.AlignVCenter,
                               fm.elidedText(mark + t.get("content", ''), Qt.ElideRight,
                                             int(w - 2 * pad_x - 6)))
                if overflow:
                    p.setPen(QPen(QColor(255, 255, 255, 150)))
                    p.setFont(T.font(max(7, min(todo_fs, 9 * self._scale))))
                    # 末行高度同样取真实度量，且字号不大于待办，必然放得下；
                    # 只留省略号，不再显示「共 N 项」——条目要一条条看得见
                    more_h = float(p.fontMetrics().height())
                    p.drawText(QRectF(x + pad_x, top + len(shown) * line_h,
                                      w - 2 * pad_x, more_h),
                               Qt.AlignLeft | Qt.AlignVCenter, u'…')
            else:
                # 格子太小放不下整行待办：右下角点一颗指示点，
                # 避免用户以为当天没有待办。
                r = max(2.5, 3.2 * self._scale)
                cx = x + w - pad_x - r
                cy = y + h - pad_y - r
                undone = any(not t.get('done') for t in todos)
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(0x4D, 0xA3, 0xFF, 230) if undone
                           else QColor(160, 160, 160, 190))
                p.drawEllipse(QPointF(cx, cy), r, r)
                p.setBrush(Qt.NoBrush)

    def _sub_text(self, d):
        """单元格副文字：节气 > 节日 > 农历"""
        ld = L.lunar_from_solar(d)
        term = L.year_terms(d.year).get(d)
        if term:
            return term, self._clr['jiericlr']
        fest, islunar = L.festival_name(d, ld)
        if fest:
            return fest, self._clr['jiericlr']
        hf = D.HOLIDAY.fest(d)
        if hf:
            return hf, self._clr['jiericlr']
        if ld is None:
            return '', self._clr['txtclr']
        if ld.day == 1:
            return ld.month_cn, self._clr['txtclr']
        return ld.day_cn, self._clr['txtclr']

    # ------------------------------------------------ tips
    def _tip_text(self, d):
        ld = L.lunar_from_solar(d)
        term = L.year_terms(d.year).get(d)
        fest, _ = L.festival_name(d, ld)
        hf = D.HOLIDAY.fest(d)
        free = D.HOLIDAY.is_free(d)
        lines = ['%s %s' % (d.strftime('%Y-%m-%d'), L.WEEK_CN[(d.weekday() + 1) % 7])]
        if ld:
            gz, sx = L.ganzhi_year(ld.year)
            lines.append(u'%s%s %s%s（%s%s）' % (gz, sx, ld.month_cn, ld.day_cn, sx, u'年'))
        if term:
            lines.append(u'节气：%s' % term)
        if fest:
            lines.append(u'节日：%s' % fest)
        elif hf:
            lines.append(u'节日：%s' % hf)
        if free is True:
            lines.append(u'休息日')
        elif free is False and d.weekday() >= 5:
            lines.append(u'调休上班')
        n = len(self._todos.get(d.isoformat()) or [])
        if n:
            lines.append(u'待办：%d 项' % n)
        return '\n'.join(lines)

    # ------------------------------------------------ 交互
    def _cell_at(self, pos):
        for d, rect in self._cells:
            if rect.contains(pos):
                return d
        return None

    def mouseMoveEvent(self, ev):
        d = self._cell_at(ev.pos())
        if d != self._hover:
            self._hover = d
            self.update()
            if d is not None and self._show_tips:
                QToolTip.showText(ev.globalPos(), self._tip_text(d), self,
                                  self.rect(), 6000)
            elif d is None:
                QToolTip.hideText()

    def leaveEvent(self, ev):
        self._hover = None
        QToolTip.hideText()
        self.update()

    def mousePressEvent(self, ev):
        d = self._cell_at(ev.pos())
        if d:
            self.set_selected(d)

    def mouseDoubleClickEvent(self, ev):
        d = self._cell_at(ev.pos())
        if d:
            self.dayActivated.emit(d)

    def wheelEvent(self, ev):
        # 手感约定（与苹果日历一致）：滚轮往上 = 往前翻 = 上一个月的航路；
        # 滚轮往下 = 翻到下一页 = 下一个月。
        step = -1 if ev.angleDelta().y() > 0 else 1
        if self._view == 'month':
            y, m = self._month.year, self._month.month
            m += step
            if m < 1:
                y, m = y - 1, 12
            elif m > 12:
                y, m = y + 1, 1
            self.set_month(datetime.date(y, m, 1))
        else:
            self.set_selected(self._selected + datetime.timedelta(days=7 * step))

    def sizeHint(self):
        return self.size()
