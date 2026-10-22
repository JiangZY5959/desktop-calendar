# -*- coding: utf-8 -*-
"""Photoshop 风格颜色选择对话框（自制，替代系统 QColorDialog）。

- 左侧大块饱和度/明度方形取色区 + 右侧竖直色相条（均为自绘，点按拖动取色）
- 右侧为 RGB / HSV / 十六进制 数值输入（QLineEdit，无上下小箭头）
- 下半部分：基础色板 + 自定义色板（可"添加到自定义颜色"，QSettings 持久化）
- 屏幕取色：全屏截图覆盖层，点哪里取哪里，Esc 取消
- exec_() / setCurrentColor() / currentColor() 与 QColorDialog 同名接口兼容；
  颜色的透明度分量原样保留（对话框只编辑 RGB，透明度由外部滑杆控制）。
"""
from PyQt5.QtCore import Qt, QPointF, QSettings, QSize
from PyQt5.QtGui import (QColor, QImage, QPainter, QPen, QPixmap,
                         QCursor)
from PyQt5.QtWidgets import (QDialog, QWidget, QHBoxLayout, QVBoxLayout,
                             QGridLayout, QLabel, QLineEdit, QPushButton,
                             QFrame, QApplication, QSizePolicy)

from . import theme as T

STORE_KEY = 'colorpick/custom'

# 基础色板（48 色，行 12 列，模仿常用调色板排布）
BASE_SWATCHES = [
    '#000000', '#404040', '#800000', '#BF4040', '#BF8040', '#806000',
    '#BFBF40', '#808000', '#40BF40', '#008000', '#40BFBF', '#008080',
    '#FFFFFF', '#D9D9D9', '#BF4080', '#BF40BF', '#8040BF', '#4040BF',
    '#4080FF', '#40BFFF', '#40FF80', '#00BF00', '#80FF40', '#FFFF80',
    '#E60000', '#FF8000', '#FFBF00', '#FFFF00', '#BFFF00', '#80FF00',
    '#00FF40', '#00FF80', '#00FFBF', '#00FFFF', '#00BFFF', '#0080FF',
    '#8040FF', '#BF40FF', '#FF40FF', '#FF40BF', '#FF0080', '#FF0040',
    '#FF7F7F', '#FFBF7F', '#FFFF7F', '#BFFF7F', '#7FFF7F', '#7FFFBF',
]


def _clamp(v, lo, hi):
    return lo if v < lo else (hi if v > hi else v)


class _SVSquare(QWidget):
    """饱和度/明度方形取色区。"""
    picked = None

    def __init__(self, dlg, parent=None):
        QWidget.__init__(self, parent)
        self._dlg = dlg
        self._drag = False
        self.setMouseTracking(True)
        self.setMinimumSize(180, 150)
        self._img = None
        self._img_h = -1

    def _rebuild(self, h):
        """按当前色相重建底层渐变图（小图放大，避免逐像素绘制卡顿）。"""
        n = 48
        im = QImage(n, n, QImage.Format_RGB32)
        for y in range(n):
            v = 255 - y * 255 // (n - 1)
            for x in range(n):
                s = x * 255 // (n - 1)
                im.setPixel(x, y, QColor.fromHsv(h, s, v).rgb())
        self._img = im
        self._img_h = h

    def paintEvent(self, ev):
        p = QPainter(self)
        h = self._dlg.hue()
        if self._img is None or self._img_h != h:
            self._rebuild(h)
        r = self.rect()
        p.drawImage(r, self._img)
        # 当前选取点：双圈光标
        x = r.x() + self._dlg.sat() * (r.width() - 1) / 255.0
        y = r.y() + (255 - self._dlg.val()) * (r.height() - 1) / 255.0
        p.setRenderHint(QPainter.Antialiasing)
        c = self._dlg.color()
        pen = QPen(Qt.white if c.valueF() < 0.6 else Qt.black)
        pen.setWidthF(1.4)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(x, y), 6.0, 6.0)
        p.setPen(QPen(Qt.white, 1.0))
        p.drawEllipse(QPointF(x, y), 7.5, 7.5)
        p.end()

    def _apply(self, pos):
        r = self.rect()
        s = _clamp(int((pos.x() - r.x()) * 255.0 / max(1, r.width() - 1)), 0, 255)
        v = _clamp(255 - int((pos.y() - r.y()) * 255.0 / max(1, r.height() - 1)), 0, 255)
        self._dlg.set_ssv(self._dlg.hue(), s, v)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = True
            self._apply(ev.pos())

    def mouseMoveEvent(self, ev):
        if self._drag:
            self._apply(ev.pos())

    def mouseReleaseEvent(self, ev):
        self._drag = False


class _HueStrip(QWidget):
    """竖直色相条。"""

    def __init__(self, dlg, parent=None):
        QWidget.__init__(self, parent)
        self._dlg = dlg
        self._drag = False
        self.setFixedWidth(18)
        self.setMouseTracking(True)

    def paintEvent(self, ev):
        p = QPainter(self)
        r = self.rect()
        im = QImage(1, 360, QImage.Format_RGB32)
        for y in range(360):
            im.setPixel(0, y, QColor.fromHsv(y, 255, 255).rgb())
        p.drawImage(r, im)
        y = r.y() + self._dlg.hue() * (r.height() - 1) / 359.0
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(Qt.white, 1.6))
        p.setBrush(Qt.NoBrush)
        p.drawEllipse(QPointF(r.center().x(), y), 8.0, 8.0)
        p.setPen(QPen(Qt.black, 1.0))
        p.drawEllipse(QPointF(r.center().x(), y), 9.5, 9.5)
        p.end()

    def _apply(self, pos):
        h = _clamp(int((pos.y() - self.rect().y()) * 359.0 /
                       max(1, self.height() - 1)), 0, 359)
        self._dlg.set_hue(h)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = True
            self._apply(ev.pos())

    def mouseMoveEvent(self, ev):
        if self._drag:
            self._apply(ev.pos())

    def mouseReleaseEvent(self, ev):
        self._drag = False


class _SwatchGrid(QFrame):
    """色板网格（基础色 + 自定义色）。"""
    clicked = None     # dlg.on_swatch(QColor)

    def __init__(self, colors, cols, parent=None):
        QFrame.__init__(self, parent)
        self._colors = list(colors)
        self._cols = cols
        self._dlg = None
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        self.setMinimumHeight(0)

    def bind(self, dlg):
        self._dlg = dlg

    def set_colors(self, colors):
        self._colors = list(colors)
        self.updateGeometry()
        self.update()

    def colors(self):
        return list(self._colors)

    def _cell(self, pos):
        cw, ch = 18, 18
        col = int((pos.x() - 1) // cw)
        row = int((pos.y() - 1) // ch)
        if 0 <= col < self._cols and 0 <= row < len(self._colors) // self._cols:
            return row * self._cols + col
        return -1

    def mousePressEvent(self, ev):
        i = self._cell(ev.pos())
        if (i >= 0 and i < len(self._colors) and self._colors[i]
                and self._dlg is not None):
            self._dlg.on_swatch(QColor(self._colors[i]))

    def paintEvent(self, ev):
        p = QPainter(self)
        cw, ch = 18, 18
        for i, cs in enumerate(self._colors):
            if not cs:
                continue
            x = 1 + (i % self._cols) * cw
            y = 1 + (i // self._cols) * ch
            p.fillRect(x, y, cw - 1, ch - 1, QColor(cs))
        p.end()

    def sizeHint(self):
        rows = max(1, (len(self._colors) + self._cols - 1) // self._cols)
        return QSize(2 + self._cols * 18, 2 + rows * 18)


class _ScreenGrab(QDialog):
    """全屏取色覆盖层：截取当前屏幕，点哪里取哪里。"""
    picked = None

    def __init__(self, on_pick, parent=None):
        QDialog.__init__(self, parent)
        self._on_pick = on_pick
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.X11BypassWindowManagerHint)
        self.setCursor(Qt.CrossCursor)
        scr = QApplication.primaryScreen()
        self._pm = scr.grabWindow(0) if scr else QPixmap()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self._pm, self._pm.rect())
        p.end()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            img = self._pm.toImage()
            c = img.pixel(_clamp(ev.pos().x(), 0, img.width() - 1),
                          _clamp(ev.pos().y(), 0, img.height() - 1))
            self._on_pick(QColor(c).rgb())
            self.accept()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.reject()


class ColorDialog(QDialog):
    """Photoshop 风格选色。接口对齐 QColorDialog 的 exec_/currentColor/setCurrentColor。"""

    def __init__(self, initial=None, parent=None, title=u'选择颜色'):
        QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self._init = QColor(initial) if initial is not None else QColor('#ffffff')
        self._c = QColor(self._init.rgb())          # 只编辑 RGB
        self._editing = False                       # 字段回填保护
        st = QSettings()
        self._custom = [c for c in st.value(STORE_KEY, []) or []]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        # ---- 上半部：取色区 + 数值区
        top = QHBoxLayout()
        top.setSpacing(10)
        self._sv = _SVSquare(self)
        self._sv.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        top.addWidget(self._sv, 1)
        top.addWidget(_HueStrip(self))

        right = QGridLayout()
        right.setHorizontalSpacing(6)
        right.setVerticalSpacing(6)
        self._fields = {}
        self._labels = {}
        row = 0
        for key, lab in (('r', u'红'), ('g', u'绿'), ('b', u'蓝')):
            right.addWidget(self._fld_label(lab, key), row, 0)
            right.addWidget(self._fld(key), row, 1)
            row += 1
        for key, lab in (('h', u'色相'), ('s', u'饱和'), ('v', u'明度')):
            right.addWidget(self._fld_label(lab, key), row % 3, 2)
            right.addWidget(self._fld(key), row % 3, 3)
            row += 1
        right.addWidget(self._fld_label(u'十六进制', 'hex'), 3, 0)
        right.addWidget(self._fld('hex'), 3, 1, 1, 2)
        # 新旧颜色对比
        self._prev = QLabel()
        self._prev.setFixedSize(52, 30)
        self._prev.setFrameStyle(QFrame.StyledPanel | QFrame.Plain)
        right.addWidget(self._prev, 4, 0, 2, 2)
        ok = QPushButton(u'确定')
        cancel = QPushButton(u'取消')
        ok.setFixedWidth(72)
        cancel.setFixedWidth(72)
        for b in (ok, cancel):
            b.setFocusPolicy(Qt.NoFocus)
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        btns = QVBoxLayout()
        btns.setSpacing(6)
        btns.addWidget(ok)
        btns.addWidget(cancel)
        right.addLayout(btns, 4, 2, 2, 2)
        top.addLayout(right)
        lay.addLayout(top, 1)

        # ---- 取色器按钮
        tools = QHBoxLayout()
        eye = QPushButton(u'屏幕取色')
        eye.setFixedWidth(96)
        eye.setFocusPolicy(Qt.NoFocus)
        eye.clicked.connect(self._screen_pick)
        tools.addWidget(eye)
        tools.addStretch(1)
        lay.addLayout(tools)

        # ---- 色板
        lay.addWidget(QLabel(u'基础颜色'))
        self._base = _SwatchGrid(BASE_SWATCHES, 12)
        self._base.bind(self)
        lay.addWidget(self._base)
        custom_row = QHBoxLayout()
        custom_row.setSpacing(8)
        custom_row.addWidget(QLabel(u'自定义颜色'))
        self._custom_grid = _SwatchGrid(self._custom + [''] *
                                        max(0, 12 - len(self._custom)), 12)
        self._custom_grid.bind(self)
        custom_row.addWidget(self._custom_grid, 1)
        addbtn = QPushButton(u'添加到自定义颜色')
        addbtn.setFixedWidth(140)
        addbtn.setFocusPolicy(Qt.NoFocus)
        addbtn.clicked.connect(self._add_custom)
        custom_row.addWidget(addbtn)
        lay.addLayout(custom_row)

        self._sync_all()
        self._refresh_prev()

    # ---- 字段构造
    def _fld_label(self, text, key):
        lb = QLabel(text)
        self._labels[key] = lb
        return lb

    def _fld(self, key):
        e = QLineEdit()
        e.setFixedWidth(52 if key != 'hex' else 64)
        e.setFocusPolicy(Qt.ClickFocus)
        e.returnPressed.connect(lambda k=key: self._on_field(k))
        e.editingFinished.connect(lambda k=key: self._on_field(k))
        self._fields[key] = e
        return e

    # ---- 状态访问（子控件用）
    def hue(self):
        h, s, v, _ = self._c.getHsv()
        return h if h >= 0 else 0

    def sat(self):
        h, s, v, _ = self._c.getHsv()
        return s

    def val(self):
        h, s, v, _ = self._c.getHsv()
        return v

    def color(self):
        return self._c

    def set_hue(self, h):
        self.set_ssv(h, self.sat(), self.val())

    def set_ssv(self, h, s, v):
        self._c.setHsv(h, s, v)
        self._sync_all()
        self._refresh_prev()
        self._sv.update()
        self._sv._rebuild(h)

    # ---- 与 QColorDialog 兼容的接口
    def setCurrentColor(self, c):
        self._init = QColor(c)
        self._c = QColor(QColor(c).rgb())
        self._sync_all()
        self._refresh_prev()
        self._sv._rebuild(self.hue())
        self._sv.update()

    def currentColor(self):
        out = QColor(self._c)
        out.setAlpha(self._init.alpha())     # 透明度原样带回
        return out

    # ---- 内部
    def on_swatch(self, c):
        self._c = QColor(c.rgb())
        self._sync_all()
        self._refresh_prev()
        self._sv._rebuild(self.hue())
        self._sv.update()

    def _add_custom(self):
        cs = '#%06X' % (QColor(self._c).rgb() & 0xFFFFFF)
        if cs in self._custom:
            return
        self._custom = ([cs] + self._custom)[:12]
        self._custom_grid.set_colors(self._custom + [''] *
                                     max(0, 12 - len(self._custom)))
        QSettings().setValue(STORE_KEY, self._custom)

    def _screen_pick(self):
        dlg = _ScreenGrab(self._on_screen_color, self)
        dlg.exec_()

    def _on_screen_color(self, rgb):
        self._c = QColor(rgb)
        self._sync_all()
        self._refresh_prev()
        self._sv._rebuild(self.hue())
        self._sv.update()

    def _refresh_prev(self):
        pm = QPixmap(48, 26)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.fillRect(0, 0, 47, 11, self._c)
        p.fillRect(0, 14, 47, 11, self._init)
        p.end()
        self._prev.setPixmap(pm)
        self._prev.setToolTip(u'上：新颜色  下：原颜色')

    def _put(self, key, text):
        e = self._fields[key]
        e.blockSignals(True)
        e.setText(text)
        e.blockSignals(False)

    def _sync_fields(self):
        self._put('r', str(self._c.red()))
        self._put('g', str(self._c.green()))
        self._put('b', str(self._c.blue()))
        self._put('h', str(self.hue()))
        self._put('s', str(self.sat()))
        self._put('v', str(self.val()))
        self._put('hex', '%02X%02X%02X' % (self._c.red(),
                                           self._c.green(), self._c.blue()))

    def _sync_all(self):
        if self._editing:
            return
        self._editing = True
        try:
            self._sync_fields()
        finally:
            self._editing = False

    def _on_field(self, key):
        if self._editing:
            return
        e = self._fields[key]
        txt = str(e.text()).strip().lstrip('#')
        try:
            if key == 'hex':
                c = QColor('#' + txt) if len(txt) in (3, 6) else None
                if not c or not c.isValid():
                    raise ValueError
                self._c = QColor(c.rgb())
            elif key in ('r', 'g', 'b'):
                n = _clamp(int(txt), 0, 255)
                self._c = QColor(n, self._c.green(), self._c.blue()) \
                    if key == 'r' else \
                    QColor(self._c.red(), n, self._c.blue()) if key == 'g' \
                    else QColor(self._c.red(), self._c.green(), n)
            else:
                n = _clamp(int(txt), 0, 359 if key == 'h' else 255)
                h, s, v = self.hue(), self.sat(), self.val()
                if key == 'h':
                    self._c.setHsv(n, s, v)
                elif key == 's':
                    self._c.setHsv(h, n, v)
                else:
                    self._c.setHsv(h, s, n)
        except (ValueError, TypeError):
            pass                                # 非法输入：仅回填当前值
        self._editing = True
        try:
            self._sync_fields()
        finally:
            self._editing = False
        self._refresh_prev()
        self._sv._rebuild(self.hue())
        self._sv.update()


def make_color_dialog(initial, parent=None, title=u'选择颜色'):
    """替换 T.zh_color_dialog 的工厂函数。"""
    return ColorDialog(initial, parent, title)
