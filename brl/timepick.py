# -*- coding: utf-8 -*-
"""提醒时间选择：仿 iPhone 闹钟的滚轮时间盘。

全部自绘实现，不依赖系统风格引擎（本机 UOS 下 QSS 子控件/系统的
QTimeEdit 微调箭头都不可靠），保证外观与交互在任何主题下都一致。
"""
from PyQt5.QtCore import Qt, QRectF, QTime, QPoint, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPen, QCursor
from PyQt5.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel,
                             QPushButton, QVBoxLayout, QDialog, QWidget)

from . import data as D
from . import theme as T

ACCENT = '#2F7BFF'


class TimeWheel(QWidget):
    """滚动滚轮：鼠标拖动 / 滚轮滚动 / 直接点行都能选值，松手自动吸附。"""

    ITEM_H = 36
    VISIBLE = 5
    valueChanged = pyqtSignal(int)

    def __init__(self, values, index=0, parent=None, show_band=True):
        QWidget.__init__(self, parent)
        self._show_band = show_band
        self._vals = list(values)
        self._idx = max(0, min(len(self._vals) - 1, int(index)))
        self._off = float(self._idx * self.ITEM_H)     # 像素偏移，吸附到整行
        self._drag_y = None
        self._drag_off = 0.0
        self._moved = 0
        self._target = self._off
        self._anim = QTimer(self)
        self._anim.setInterval(16)
        self._anim.timeout.connect(self._step)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedWidth(76)

    # ---------------- 取值
    def count(self):
        return len(self._vals)

    def index(self):
        return self._idx

    def value(self):
        return self._vals[self._idx]

    def set_index(self, i):
        i = max(0, min(len(self._vals) - 1, int(i)))
        if i != self._idx:
            self._idx = i
            self.valueChanged.emit(i)
        self._off = float(i * self.ITEM_H)
        self._target = self._off
        self.update()

    def sizeHint(self):
        return QSize(76, self.ITEM_H * self.VISIBLE)

    # ---------------- 交互
    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton:
            return
        self._anim.stop()
        self._drag_y = ev.y()
        self._drag_off = self._off
        self._moved = 0

    def mouseMoveEvent(self, ev):
        if self._drag_y is None:
            return
        dy = self._drag_y - ev.y()
        self._moved = max(self._moved, abs(dy))
        limit = float((len(self._vals) - 1) * self.ITEM_H)
        soft = self.ITEM_H * 0.4
        self._off = max(-soft, min(limit + soft, self._drag_off + dy))
        self.update()

    def mouseReleaseEvent(self, ev):
        if self._drag_y is None:
            return
        if self._moved < 3:                     # 单击：选中被点中的那一行
            mid = self.height() / 2.0
            row = int((ev.y() - mid + self._off) / self.ITEM_H + 0.5)
            row = max(0, min(len(self._vals) - 1, row))
            self._target = float(row * self.ITEM_H)
        else:
            self._target = self._clamp_off(self._off)
        self._drag_y = None
        self._anim.start()
        self.update()

    def wheelEvent(self, ev):
        dy = ev.angleDelta().y()
        if dy == 0:
            return
        self.set_index(self._idx + (-1 if dy > 0 else 1))

    def _clamp_off(self, off):
        row = int(off / self.ITEM_H + 0.5)
        row = max(0, min(len(self._vals) - 1, row))
        return float(row * self.ITEM_H)

    def _step(self):
        d = self._target - self._off
        if abs(d) < 0.6:
            self._off = self._target
            self._anim.stop()
            i = int(self._off / self.ITEM_H + 0.5)
            if i != self._idx:
                self._idx = i
                self.valueChanged.emit(i)
            self.update()
            return
        self._off += d * 0.32
        self.update()

    # ---------------- 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        mid = self.height() / 2.0
        # 中间选中条（组合使用时可关掉，由外层画一整条）
        if self._show_band:
            T.paint_round(p, QRectF(4, mid - self.ITEM_H / 2.0,
                                    self.width() - 8, self.ITEM_H), 8,
                          '#122F7BFF')
        for i, txt in enumerate(self._vals):
            y = mid + i * self.ITEM_H - self._off
            if y < -self.ITEM_H or y > self.height() + self.ITEM_H:
                continue
            d = abs(y - mid) / float(self.ITEM_H)
            if d < 0.55:                          # 正中间：主色加粗
                f = T.font(22, bold=True)
                col = QColor(ACCENT)
            else:
                f = T.font(int(21 - 6 * min(d, 2.0)))
                col = QColor(32, 38, 48, max(40, int(225 - 90 * d)))
            p.setFont(f)
            p.setPen(QPen(col))
            p.drawText(QRectF(0, y - self.ITEM_H / 2.0, self.width(), self.ITEM_H),
                       Qt.AlignCenter, txt)
        p.end()


class _BandRow(QWidget):
    """时/分滚轮的容器：在中间行画一整条高亮（iOS 样式）。"""

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        T.paint_round(p, QRectF(28, self.height() / 2.0 - TimeWheel.ITEM_H / 2.0,
                                self.width() - 56, TimeWheel.ITEM_H), 8,
                      '#122F7BFF')
        p.end()


class TimePopup(QDialog):
    """时间盘：标题 + 时/分滚轮 + 取消/确定。点盘外自动关闭。"""

    def __init__(self, t=None, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowFlags(Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(300, 300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        card = QWidget()
        card.setObjectName('timeCard')
        card.setStyleSheet('QWidget#timeCard{background:#FFFFFF;border-radius:14px;}')
        lay.addWidget(card)
        cv = QVBoxLayout(card)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)

        head = QLabel(u'设置提醒时间')
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet('color:#202020;font-size:14px;padding:8px 0 2px;')
        cv.addWidget(head)

        wheel = _BandRow()
        wl = QHBoxLayout(wheel)
        wl.setContentsMargins(0, 2, 0, 4)
        wl.setSpacing(0)
        self._wh = TimeWheel(['%02d' % i for i in range(24)])
        self._wm = TimeWheel(['%02d' % i for i in range(60)])
        colon = QLabel(':')
        colon.setFixedWidth(14)
        colon.setStyleSheet('color:#202020;font-size:22px;font-weight:bold;')
        wl.addStretch(1)
        wl.addWidget(self._wh, 0, Qt.AlignVCenter)
        wl.addWidget(colon, 0, Qt.AlignVCenter)
        wl.addWidget(self._wm, 0, Qt.AlignVCenter)
        wl.addStretch(1)
        cv.addWidget(wheel, 1)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet('background:#E9EDF2;border:none;')
        cv.addWidget(line)

        btns = QHBoxLayout()
        btns.setContentsMargins(0, 0, 0, 0)
        btns.setSpacing(0)
        for txt, ok, cb in ((u'取消', False, self.reject),
                            (u'确定', True, self.accept)):
            b = QPushButton(txt)
            b.setFlat(True)
            b.setFixedHeight(44)
            b.setFocusPolicy(Qt.NoFocus)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(cb)
            b.setStyleSheet(
                'QPushButton{border:none;background:transparent;font-size:15px;'
                'color:%s;%s}' % (ACCENT if ok else '#7A8794',
                                  'font-weight:bold;' if ok else ''))
            btns.addWidget(b)
        cv.addLayout(btns)

        self.setTime(t if t is not None else QTime.currentTime())

    def setTime(self, t):
        self._wh.set_index(t.hour())
        self._wm.set_index(t.minute())

    def time(self):
        return QTime(self._wh.index(), self._wm.index())

    def current(self):
        return self._wh.index(), self._wm.index()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 26))          # 轻微投影，让时间盘浮起来
        p.drawRoundedRect(QRectF(self.rect()).adjusted(4, 4, -4, -4), 16, 16)
        p.end()


class TimePick(QFrame):
    """提醒时间输入框：点一下弹出上面那个时间盘。

    对外接口与 QTimeEdit 兼容（time()/text()/setTime()），
    分钟可选到每一分钟（00-59），且完全靠鼠标操作。
    """

    popupClass = TimePopup

    def __init__(self, parent=None):
        QFrame.__init__(self, parent)
        self.setObjectName('timePick')
        self.setStyleSheet(
            'QFrame#timePick{background:#FFFFFF;border:1px solid #DEE3E8;'
            'border-radius:6px;}'
            'QFrame#timePick:hover{border:1px solid %s;}'
            'QFrame#timePick:disabled{background:#F5F6F8;border-color:#E9ECEF;}'
            % ACCENT)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFixedHeight(34)
        self.setMinimumWidth(190)
        self.setCursor(Qt.PointingHandCursor)
        self._h, self._m = 9, 0
        self._pop = None

    # ---------------- 数据接口
    def time(self):
        return QTime(self._h, self._m)

    def text(self):
        return '%02d:%02d' % (self._h, self._m)

    def setTime(self, t):
        self._h = max(0, min(23, t.hour()))
        self._m = max(0, min(59, t.minute()))
        self.update()

    # ---------------- 交互
    def mousePressEvent(self, ev):
        if not self.isEnabled():
            return
        QFrame.mousePressEvent(self, ev)
        self.open_popup()

    def open_popup(self):
        """弹出时间盘；返回 None 表示取消，否则返回新时间。"""
        pop = self.popupClass(QTime(self._h, self._m), self)
        self._pop = pop
        pos = self.mapToGlobal(QPoint(0, self.height() + 4))
        g = QApplication.desktop().availableGeometry()
        if pos.y() + pop.height() > g.bottom():     # 下方放不下就翻到上面
            pos.setY(max(g.top(),
                         self.mapToGlobal(QPoint(0, 0)).y() - pop.height() - 4))
        pop.move(pos)
        r = pop.exec_()
        self._pop = None
        if r == QDialog.Accepted:
            self.setTime(pop.time())
            return self.time()
        return None

    # ---------------- 绘制
    def paintEvent(self, ev):
        QFrame.paintEvent(self, ev)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        x = 10
        pm = T.pix(D.res('icons', 'clock.png'))
        if not pm.isNull():
            p.drawPixmap(QPoint(x, (self.height() - 15) / 2),
                         pm.scaled(15, 15, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation))
        x += 22
        pen = QPen(QColor('#202020') if self.isEnabled() else QColor('#A8AEB6'))
        p.setPen(pen)
        p.setFont(T.font(15))
        p.drawText(QRectF(x, 0, 32, self.height()), Qt.AlignCenter, '%02d' % self._h)
        x += 32
        p.setFont(T.font(15, bold=True))
        p.drawText(QRectF(x, 0, 10, self.height()), Qt.AlignCenter, ':')
        x += 10
        p.setFont(T.font(15))
        p.drawText(QRectF(x, 0, 32, self.height()), Qt.AlignCenter, '%02d' % self._m)
        p.end()
