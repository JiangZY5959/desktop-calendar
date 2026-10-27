# -*- coding: utf-8 -*-
"""选项设置（两页签：基础设置 / 背景设置）。

基础设置页按原版补齐：
- 开机启动 / 显示周末 / 显示农历 / 显示节日 / 显示格子分割线 /
  悬停 tips 提示 / 显示班休 / 内外边框颜色与透明度
- 设置第一周起点（第几周规则）
- 日历字体大小 / 清单字体大小
- 日历字体 / 星期标题栏字体 / 节日字体 / 今日背景 / 窗口背景 / 格子背景 /
  星期标题栏背景 / 内外边框 颜色（全部含透明度滑杆）
- 默认设置（恢复当前主题默认）
"""
import datetime
import os

from PyQt5.QtCore import Qt, pyqtSignal, QRectF, QPointF, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen
from PyQt5.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout, QGridLayout, QCheckBox, QComboBox,
                             QScrollArea, QFrame, QColorDialog, QStackedWidget,
                             QSlider, QSizePolicy)

from . import data as D
from . import theme as T
from . import update as U
from . import APP_NAME, __version__ as APP_VER


class AlphaSlider(QSlider):
    """自绘进度滑杆：UOS 风格引擎下 QSS 的 sub-page 不渲染，
    滑槽/已调进度只能自己画，保证"百分比进度条"可见可拖。"""

    def __init__(self, parent=None):
        QSlider.__init__(self, Qt.Horizontal, parent)
        self._drag = False
        self.setCursor(Qt.PointingHandCursor)

    def _val_at(self, x):
        m = 9                                   # 半个滑块宽，防止端点溢出
        w = max(1, self.width() - 2 * m)
        frac = min(1.0, max(0.0, (x - m) / float(w)))
        rng = self.maximum() - self.minimum()
        return self.minimum() + int(round(frac * rng))

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = True
            self.setValue(self._val_at(ev.x()))
            ev.accept()
            return
        QSlider.mousePressEvent(self, ev)

    def mouseMoveEvent(self, ev):
        if self._drag:
            self.setValue(self._val_at(ev.x()))
            ev.accept()
            return
        QSlider.mouseMoveEvent(self, ev)

    def mouseReleaseEvent(self, ev):
        self._drag = False
        QSlider.mouseReleaseEvent(self, ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        cy = h / 2.0
        m = 9.0
        w = max(1.0, self.width() - 2 * m)
        # 滑槽
        p.setPen(Qt.NoPen)
        p.setBrush(QColor('#D5DDE8'))
        p.drawRoundedRect(QRectF(m, cy - 3, w, 6), 3, 3)
        # 已调进度
        rng = float(self.maximum() - self.minimum() or 1)
        frac = (self.value() - self.minimum()) / rng
        p.setBrush(QColor('#2F7BFF'))
        p.drawRoundedRect(QRectF(m, cy - 3, w * frac, 6), 3, 3)
        # 滑块
        p.setPen(QPen(QColor('#2F7BFF'), 2))
        p.setBrush(QColor('#FFFFFF'))
        p.drawEllipse(QPointF(m + w * frac, cy), 7, 7)
        p.end()

# 颜色覆盖的设置键：key -> (显示名, 是否带透明度)
COLOR_DEFS = [
    ('txtclr',     u'日历字体颜色', True),
    ('weekclr',    u'星期标题栏字体颜色', True),
    ('jiericlr',   u'节日字体颜色', True),
    ('todayclr',   u'今日背景颜色', True),
    ('mainbg',     u'窗口背景颜色', True),
    ('gridbg',     u'格子背景颜色', True),
    ('weekgridbg', u'星期标题栏背景颜色', True),
    ('borderout',  u'外边框颜色', True),
    ('borderin',   u'内边框颜色', True),
]


def color_key(k):
    return 'color/' + k


class ColorPick(QWidget):
    """颜色选择（点击选颜色，可选内嵌透明度滑杆，等效原版 ClrButton+UISlider）。"""
    changed = pyqtSignal(str, object)      # key, '#AARRGGBB' or None

    def __init__(self, key, color, with_alpha, fallback, parent=None):
        QWidget.__init__(self, parent)
        self._key = key
        self._c = QColor(color) if color else QColor(fallback)
        self._alpha = with_alpha
        self._fallback = QColor(fallback)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._btn = QPushButton()
        self._btn.setFixedSize(64, 26)
        self._btn.clicked.connect(self._pick)
        lay.addWidget(self._btn)
        if with_alpha:
            self._sl = AlphaSlider()
            self._sl.setRange(0, 255)
            self._sl.setValue(self._c.alpha())
            self._sl.setFixedWidth(56)
            self._sl.setFixedHeight(22)
            self._sl.valueChanged.connect(self._on_alpha)
            lay.addWidget(self._sl)
            self._lb = QLabel('%d%%' % round(self._c.alpha() * 100 / 255.0))
            self._lb.setFixedWidth(30)
            lay.addWidget(self._lb)
        self._repaint_btn()

    def _repaint_btn(self):
        pm, used = self._btn.size(), None
        self._btn.setIcon(self._swatch())
        self._btn.setIconSize(pm)

    def _swatch(self):
        from PyQt5.QtGui import QPixmap, QIcon
        pm = QPixmap(48, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(230, 231, 232))
        p.setBrush(self._c)
        p.drawRoundedRect(0, 0, 47, 19, 3, 3)
        p.end()
        return QIcon(pm)

    def paintEvent(self, ev):
        pass

    def _pick(self):
        dlg = T.zh_color_dialog(QColor(self._c.rgb()), self)
        if dlg.exec_() == QDialog.Accepted:
            self._c = QColor(dlg.currentColor().rgb())
            self._c.setAlpha(self._sl.value() if self._alpha else 255)
            self._repaint_btn()
            self.changed.emit(self._key, str(self))

    def _on_alpha(self, v):
        self._c.setAlpha(v)
        if hasattr(self, '_lb'):
            self._lb.setText('%d%%' % round(v * 100 / 255.0))
        self._repaint_btn()
        self.changed.emit(self._key, str(self))

    def set_color(self, c):
        self._c = QColor(c)
        if self._alpha:
            self._sl.blockSignals(True)
            self._sl.setValue(self._c.alpha())
            self._sl.blockSignals(False)
            self._lb.setText('%d%%' % round(self._c.alpha() * 100 / 255.0))
        self._repaint_btn()

    def __str__(self):
        return self._c.name(QColor.HexArgb).upper()


class ColorButton(QPushButton):
    """无透明度的纯色选择按钮。"""
    changed = pyqtSignal(str, object)

    def __init__(self, key, color, fallback, parent=None):
        QPushButton.__init__(self, parent)
        self._key = key
        self._c = QColor(color) if color else QColor(fallback)
        self._fallback = QColor(fallback)
        self.setFixedSize(64, 26)
        self.clicked.connect(self._pick)
        self._repaint()

    def _repaint(self):
        from PyQt5.QtGui import QPixmap, QIcon
        pm = QPixmap(48, 20)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(230, 231, 232))
        p.setBrush(self._c)
        p.drawRoundedRect(0, 0, 47, 19, 3, 3)
        p.end()
        self.setIcon(QIcon(pm))
        self.setIconSize(pm.size())

    def _pick(self):
        dlg = T.zh_color_dialog(QColor(self._c.rgb()), self)
        if dlg.exec_() == QDialog.Accepted:
            self._c = QColor(dlg.currentColor().rgb())
            self._c.setAlpha(255)
            self._repaint()
            # 必须发颜色字符串：早期这里误传 str(self)（对象描述串），
            # 写进配置后被 _color_overrides 判为非法而回退，表现为调了没反应
            self.changed.emit(self._key, self._c.name(QColor.HexRgb).upper())

    def set_color(self, c):
        self._c = QColor(c)
        self._repaint()

    def __str__(self):
        return self._c.name(QColor.HexRgb).upper()


class ThemeCard(QPushButton):
    def __init__(self, index, preview, win, parent=None):
        QPushButton.__init__(self, parent)
        self._idx = index
        self._win = win
        self.setFixedSize(280, 170)
        self._pm = T.pix(preview) if preview else None
        self.clicked.connect(lambda: self._win.on_theme(index))

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        T.paint_round(p, self.rect().adjusted(0, 0, -1, -1), 6, '#FFFFFFFF')
        up = self.rect().adjusted(1, 1, -1, -41)   # 预览区止于底部标签条上方
        if self._pm and not self._pm.isNull():
            p.drawPixmap(up, self._pm, self._pm.rect())
        else:
            self._draw_preview(p, up, T.ALL_THEMES[self._idx])
        # 底部标签条用主题自身底色（不透明），文字按底色亮度自动反色
        bg = T.qcolor(T.ALL_THEMES[self._idx].get('mainbgndclr'), Qt.darkGray)
        bg.setAlpha(255)
        p.fillRect(self.rect().adjusted(1, self.height() - 40, -1, -1), bg)
        lum = (bg.red() * 299 + bg.green() * 587 + bg.blue() * 114) // 1000
        p.setPen(QColor('#3A3A3A') if lum > 150 else QColor(Qt.white))
        p.setFont(T.font(11))
        p.drawText(self.rect().adjusted(8, self.height() - 36, -8, -4),
                   Qt.AlignLeft | Qt.AlignVCenter, T.ALL_THEMES[self._idx].get('name', ''))
        p.drawText(self.rect().adjusted(-70, self.height() - 36, -8, -4),
                   Qt.AlignRight | Qt.AlignVCenter, u'使用主题')

    def _draw_preview(self, p, r, th):
        """按主题自身配色绘制迷你月历预览（自制，无需外部图片）"""
        p.save()
        p.setClipRect(r)
        T.paint_round(p, r, 6, th.get('mainbgndclr', '#FFFFFFFF'))
        cols, rows = 7, 5
        cw, ch = r.width() / float(cols), r.height() / float(rows)
        today = 17
        n = 1
        for i in range(cols * rows):
            row, col = i // cols, i % cols
            cell = QRectF(r.x() + col * cw, r.y() + row * ch, cw + 1, ch + 1)
            if i == today:
                bc = th.get('todayclr')
            elif col >= 5:
                bc = th.get('weekgridbgndclr')
            else:
                bc = th.get('gridbgndclr')
            if bc:
                p.fillRect(cell, T.qcolor(bc))
            if 1 <= n <= 31:
                p.setPen(T.qcolor(th.get('txtclr') or th.get('weekclr'), Qt.white))
                p.setFont(T.font(9))
                p.drawText(cell, Qt.AlignCenter, str(n))
                n += 1
        p.restore()


class SettingsDialog(QDialog):
    settingChanged = pyqtSignal(str, object)
    checkRequested = pyqtSignal()          # 「立即检查」更新

    def __init__(self, store, parent=None):
        QDialog.__init__(self, parent)
        self._store = store
        self.setWindowTitle(APP_NAME + u' - 选项设置')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(830, 620)
        self.setStyleSheet(
            'QDialog{background:#F2F6FC;border-radius:10px;}'
            'QLabel{color:#202020;font-size:13px;}'
            'QCheckBox{color:#202020;font-size:14px;}'
            'QPushButton{font-size:13px;}')
        self._theme_idx = int(store.settings().value('ui/theme') or 0)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)

        mid = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(12)
        self._tabs = []
        for i, name in enumerate((u'基础设置', u'背景设置', u'检查更新')):
            b = QPushButton(name)
            b.setFixedSize(140, 36)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(T.tab_style())   # 与菜单、关于窗口同一套浅色卡片
            b.clicked.connect(lambda checked=False, i=i: self._switch(i))
            left.addWidget(b)
            self._tabs.append(b)
        left.addStretch(1)
        mid.addLayout(left)
        self._stack = QStackedWidget()
        mid.addWidget(self._stack, 1)
        lay.addLayout(mid, 1)
        self._color_picks = {}
        self._build_basic()
        self._build_theme()
        self._build_update()
        self._switch(0)
        # 状态那行小字跟着后台检查结果自动刷新（检查在另一个线程里跑）
        self._upd_t = QTimer(self)
        self._upd_t.timeout.connect(self.refresh_update_status)
        self._upd_t.start(2000)

    def _switch(self, i):
        for k, b in enumerate(self._tabs):
            b.setChecked(k == i)
        self._stack.setCurrentIndex(i)

    # ---------------- 颜色覆盖读写 ----------------
    def _theme_cfg(self):
        return T.ALL_THEMES[self._theme_idx % len(T.ALL_THEMES)]

    def _fallback(self, key):
        cfg = self._theme_cfg()
        m = {'mainbg': 'mainbgndclr', 'gridbg': 'gridbgndclr',
             'weekgridbg': 'weekgridbgndclr',
             'borderout': 'borderoutclr', 'borderin': 'borderinclr'}
        return cfg.get(m.get(key, key), '#FFFFFFFF')

    def _stored(self, key):
        v = self._store.settings().value(color_key(key))
        return str(v) if v else None

    # ---------------- 基础设置 ----------------
    def _build_basic(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        page.setStyleSheet('#basicInner{background:transparent;}')
        lay = QVBoxLayout()
        lay.setContentsMargins(15, 10, 10, 10)
        lay.setSpacing(10)
        st = self._store.settings()

        def chk(key, label, default=False):
            c = QCheckBox(label)
            c.setChecked(str(st.value(key, '1' if default else '0')) == '1')
            c.toggled.connect(lambda v, k=key: self.on_check(k, v))
            return c

        grid = QWidget()
        gl = QGridLayout(grid)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setHorizontalSpacing(30)
        gl.setVerticalSpacing(12)
        gl.addWidget(chk('app/autostart', u'开机启动桌面日历'), 0, 0)
        gl.addWidget(chk('cal/showweek', u'显示第几周'), 1, 0)
        gl.addWidget(chk('cal/showlunnar', u'显示农历', True), 1, 1)
        gl.addWidget(chk('cal/showjieri', u'显示节日', True), 2, 0)
        gl.addWidget(chk('cal/showline', u'显示格子分割线', True), 2, 1)
        gl.addWidget(chk('cal/showtips', u'鼠标在格子时弹tips提示', True), 3, 0)
        gl.addWidget(chk('cal/showban', u'显示班假', True), 3, 1)
        gl.addWidget(chk('cal/showweekend', u'高亮周末', True), 4, 0)
        lay.addWidget(grid)

        # 第一周起点 + 日历字体大小 + 清单字体大小
        row = QHBoxLayout()
        row.addWidget(QLabel(u'设置第一周起点:'))
        cb = QComboBox()
        cb.setStyleSheet(T.combo_style(min_width=80))
        cb.addItem(u'1月1日', 'jan1')
        cb.addItem(u'周一', 'mon')
        cur = str(st.value('cal/weekstart') or 'jan1')
        cb.setCurrentIndex(1 if cur == 'mon' else 0)
        cb.currentIndexChanged.connect(
            lambda i: self.on_value('cal/weekstart', cb.itemData(i)))
        row.addWidget(cb)
        row.addSpacing(8)
        row.addWidget(QLabel(u'日历字体大小:'))
        cb2 = QComboBox()
        cb2.setStyleSheet(T.combo_style(compact=True))
        for i in (9, 10, 11, 12, 13, 14, 15, 16):
            cb2.addItem('%d' % i)
        cb2.setCurrentText(str(st.value('cal/scale') or 10))
        cb2.currentTextChanged.connect(lambda v: self.on_value('cal/scale', v))
        row.addWidget(cb2)
        row.addSpacing(8)
        row.addWidget(QLabel(u'清单字体大小:'))
        cb3 = QComboBox()
        cb3.setStyleSheet(T.combo_style(compact=True))
        for i in (8, 9, 10, 11, 12, 13, 14):
            cb3.addItem('%d' % i)
        cb3.setCurrentText(str(st.value('cal/qscale') or 11))
        cb3.currentTextChanged.connect(lambda v: self.on_value('cal/qscale', v))
        row.addWidget(cb3)
        row.addStretch(1)
        lay.addLayout(row)

        # 颜色设置：两列网格对齐（标签定宽、色块定宽），同一对象的颜色
        # 左右挨着——星期标题栏的字体/背景一行，外边框/内边框一行
        _meta = dict((k, (lb, al)) for k, lb, al in COLOR_DEFS)
        _PAIRS = [
            ('txtclr', 'jiericlr'),        # 日历字体 | 节日字体
            ('weekclr', 'weekgridbg'),     # 星期标题栏字体 | 星期标题栏背景
            ('todayclr', 'mainbg'),        # 今日背景 | 窗口背景
            ('borderout', 'borderin'),     # 外边框 | 内边框
            ('gridbg', None),              # 格子背景
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(9)
        for r, pair in enumerate(_PAIRS):
            for c, key in enumerate(pair):
                if key is None:
                    continue
                label, alpha = _meta[key]
                lb = QLabel(label + ':')
                lb.setFixedWidth(132)
                grid.addWidget(lb, r, c * 2)
                if alpha:
                    cp = ColorPick(key, self._stored(key), alpha,
                                   self._fallback(key))
                else:
                    cp = ColorButton(key, self._stored(key),
                                     self._fallback(key))
                cp.changed.connect(self.on_color)
                self._color_picks[key] = cp
                grid.addWidget(cp, r, c * 2 + 1)
        grid.setColumnStretch(4, 1)
        lay.addLayout(grid)

        # 默认设置
        rowd = QHBoxLayout()
        bdef = QPushButton(u'默认设置')
        bdef.setFixedSize(120, 30)
        bdef.clicked.connect(self._reset_colors)
        rowd.addWidget(bdef)
        rowd.addStretch(1)
        lay.addLayout(rowd)

        lay.addStretch(1)
        inner = QWidget()
        inner.setObjectName('basicInner')
        inner.setLayout(lay)
        sc.setWidget(inner)
        outer.addWidget(sc)
        self._stack.addWidget(page)

    def _upd_status(self):
        """更新页里的状态行：上次检查时间 / 结果 / 是否跳过过某版本。"""
        st = self._store.settings()
        last = 0
        try:
            last = int(st.value('update/last') or 0)
        except (TypeError, ValueError):
            last = 0
        when = u'从未检查'
        if last:
            try:
                when = datetime.datetime.fromtimestamp(last).strftime('%Y-%m-%d %H:%M')
            except Exception:
                when = u'未知'
        bits = [u'上次检查：%s' % when]
        lastver = str(st.value('update/lastver') or '')
        if lastver and U.is_newer(lastver, APP_VER):
            bits.append(u'发现新版本 v%s' % lastver)
        elif last:
            bits.append(u'远端无更新')
        skip = str(st.value('update/skip') or '')
        if skip:
            bits.append(u'已跳过 v%s' % skip)
        return u'　·　'.join(bits)

    def refresh_update_status(self):
        if getattr(self, '_upd_lb', None) is not None:
            self._upd_lb.setText(self._upd_status())

    def _reset_colors(self):
        """恢复默认颜色。

        以前这里把每个颜色写成空串，会把用户原本的配置"洗掉"；
        现在改成：出厂默认值里有的写回默认值，没有的直接删除该键（回退到主题色）。
        """
        from . import defaults as DF
        st = self._store.settings()
        for key, _label, _a in COLOR_DEFS:
            k = color_key(key)
            if k in DF.DEFAULTS:
                st.setValue(k, DF.DEFAULTS[k])
            else:
                st.remove(k)
            cp = self._color_picks.get(key)
            if cp:
                cp.set_color(self._stored(key) or self._fallback(key))
        st.sync()
        self.settingChanged.emit('color/reset', None)

    # ---------------- 背景设置 ----------------
    def _build_theme(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(15, 15, 15, 15)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        g = QGridLayout(inner)
        g.setSpacing(14)
        for i in range(len(T.ALL_THEMES)):    # ⑤ 只建当前主题数量的卡片，防越界崩溃
            # 预览由卡片按主题自身配色绘制，不依赖任何外部图片
            g.addWidget(ThemeCard(i, None, self), i // 2, i % 2)
        sc.setWidget(inner)
        lay.addWidget(sc)
        self._stack.addWidget(page)

    # ---------------- 检查更新（与基础/背景设置同级的独立页签）----------------
    def _build_update(self):
        page = QWidget()
        page.setStyleSheet('#updPage{background:transparent;}')
        lay = QVBoxLayout(page)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)
        st = self._store.settings()

        ttl = QLabel(u'检查更新')
        ttl.setStyleSheet('color:#202020;font-size:16px;font-weight:bold;')
        lay.addWidget(ttl)
        self._ver_lb = QLabel(u'当前版本 v%s' % APP_VER)
        self._ver_lb.setStyleSheet('color:#5A6069;font-size:13px;')
        lay.addWidget(self._ver_lb)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setFixedHeight(1)
        sep1.setStyleSheet('background:#E6E7E8;border:none;')
        lay.addWidget(sep1)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel(u'检查频率:'))
        cbu = QComboBox()
        cbu.setStyleSheet(T.combo_style(min_width=168))
        for key, name, _days in U.MODE_DAYS:
            cbu.addItem(name, key)
        cur = str(st.value('update/mode') or U.MODE_DEFAULT)
        idx = cbu.findData(cur)
        cbu.setCurrentIndex(idx if idx >= 0 else 0)
        cbu.setToolTip(u'到点后自动到 GitCode 查一次版本；\n'
                       u'「仅手动检查」只在点「立即检查」时联网')
        cbu.currentIndexChanged.connect(
            lambda i: self.on_value('update/mode', cbu.itemData(i)))
        self._upd_cb = cbu
        row.addWidget(cbu)
        bupd = QPushButton(u'立即检查')
        bupd.setFixedSize(96, 30)
        bupd.setCursor(Qt.PointingHandCursor)
        bupd.setStyleSheet('QPushButton{background:#FFFFFF;color:#202020;'
                           'border:1px solid #DCE0E6;border-radius:5px;font-size:13px;}'
                           'QPushButton:hover{background:#F5F8FF;'
                           'border-color:#A9CDF7;color:#202020;}')
        bupd.clicked.connect(self.checkRequested.emit)
        self._upd_btn = bupd
        row.addWidget(bupd)
        row.addStretch(1)
        lay.addLayout(row)

        self._upd_lb = QLabel(self._upd_status())
        self._upd_lb.setStyleSheet('color:#8A8F99;font-size:12px;')
        lay.addWidget(self._upd_lb)

        hint = QLabel(
            u'发现新版本时会弹出提示；确认更新后会自动从 GitCode 下载安装包，\n'
            u'校验后调用系统安装程序完成安装。\n'
            u'检查更新只读取版本清单，不上传任何数据。')
        hint.setWordWrap(True)
        hint.setStyleSheet('color:#8A8F99;font-size:12px;')
        lay.addWidget(hint)

        lay.addStretch(1)
        self._stack.addWidget(page)


    # ---------------- 回调 ----------------
    def on_check(self, key, val):
        st = self._store.settings()
        st.setValue(key, '1' if val else '0')
        st.sync()
        self.settingChanged.emit(key, val)

    def on_value(self, key, val):
        st = self._store.settings()
        st.setValue(key, val)
        st.sync()
        self.settingChanged.emit(key, val)

    def on_color(self, key, val):
        st = self._store.settings()
        st.setValue(color_key(key), val or '')
        st.sync()
        self.settingChanged.emit('color/' + key, val)

    def on_theme(self, idx):
        st = self._store.settings()
        st.setValue('ui/theme', idx)
        st.sync()
        self._theme_idx = idx
        # 换主题后，颜色覆盖显示为主题默认色（覆盖值保留）
        for key, _label, _a in COLOR_DEFS:
            cp = self._color_picks.get(key)
            if cp:
                stored = self._stored(key)
                cp.set_color(stored or self._fallback(key))
        self.settingChanged.emit('ui/theme', idx)
