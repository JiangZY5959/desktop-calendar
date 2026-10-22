# -*- coding: utf-8 -*-
"""主题配色（原创设计）与界面辅助工具。"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QPainter, QPixmap, QIcon, QFont
from PyQt5.QtWidgets import QWidget

from . import data as D

# 主题配色（原创设计，8 套）
# 字段：name 显示名 / txtclr 日历文字 / weekclr 周末与表头文字 / jiericlr 节日文字 /
#       mainbgndclr 窗口背景 / gridbgndclr 格子背景 / weekgridbgndclr 周末格子背景 /
#       todayclr 今日高亮 / borderoutclr 外边框 / borderinclr 内边框(格子分割线) / gridline 分割线开关
THEMES = [
    dict(name=u'玄夜', txtclr='#F2FFFFFF', weekclr='#CCFFFFFF', jiericlr='#FFFFD54F',
         mainbgndclr='#B4101216', gridbgndclr='#33FFFFFF', weekgridbgndclr='#26FFFFFF',
         todayclr='#8C1AEAE8', borderoutclr='#3CFFFFFF', borderinclr='#30FFFFFF',
         gridline=True),
    dict(name=u'星空蓝', txtclr='#FFE3F2FD', weekclr='#FFBBDEFB', jiericlr='#FF4FC3F7',
         mainbgndclr='#C2101A2E', gridbgndclr='#2E4FC3F7', weekgridbgndclr='#1F4FC3F7',
         todayclr='#8C0288D1', borderoutclr='#3C4FC3F7', borderinclr='#2A4FC3F7',
         gridline=True),
    dict(name=u'石墨灰', txtclr='#FFF5F5F5', weekclr='#FFB0BEC5', jiericlr='#FFFF7043',
         mainbgndclr='#E837474F', gridbgndclr='#2EFFFFFF', weekgridbgndclr='#1FFFFFFF',
         todayclr='#8C607D8B', borderoutclr='#3CB0BEC5', borderinclr='#28B0BEC5',
         gridline=True),
    dict(name=u'曙光橙', txtclr='#FF4E342C', weekclr='#FF6D4C41', jiericlr='#FFD84315',
         mainbgndclr='#E5FFF3E0', gridbgndclr='#59FFCC80', weekgridbgndclr='#45FFAB91',
         todayclr='#8CFF7043', borderoutclr='#4DFFAB91', borderinclr='#40FFCC80',
         gridline=False),
    dict(name=u'青瓷', txtclr='#FF00695C', weekclr='#FF00796B', jiericlr='#FFC62828',
         mainbgndclr='#D9E0F2F1', gridbgndclr='#4D80CBC4', weekgridbgndclr='#3AB2DFDB',
         todayclr='#8C00897B', borderoutclr='#4D80CBC4', borderinclr='#4080CBC4',
         gridline=False),
    dict(name=u'蜜桃粉', txtclr='#FFAD1457', weekclr='#FFEC407A', jiericlr='#FFD81B60',
         mainbgndclr='#D9FCE4EC', gridbgndclr='#4DF48FB1', weekgridbgndclr='#3AF8BBD0',
         todayclr='#8CEC407A', borderoutclr='#4DF48FB1', borderinclr='#40F48FB1',
         gridline=False),
    dict(name=u'原野绿', txtclr='#FF1B5E20', weekclr='#FF2E7D32', jiericlr='#FFC62828',
         mainbgndclr='#D9E8F5E9', gridbgndclr='#4DA5D6A7', weekgridbgndclr='#3AC8E6C9',
         todayclr='#8C43A047', borderoutclr='#4DA5D6A7', borderinclr='#40A5D6A7',
         gridline=False),
    dict(name=u'樱紫', txtclr='#FF6A1B9A', weekclr='#FF8E24AA', jiericlr='#FFD500F9',
         mainbgndclr='#D9F3E5F5', gridbgndclr='#4DCE93D8', weekgridbgndclr='#3AE1BEE7',
         todayclr='#8C8E24AA', borderoutclr='#4DCE93D8', borderinclr='#40CE93D8',
         gridline=False),
]


def load_themes():
    """原创 8 套配色，全部内置，不读取任何外部 xml 文件"""
    return [dict(t) for t in THEMES]


ALL_THEMES = load_themes()


def qcolor(s, fallback=Qt.white):
    """'#aarrggbb' / '#rrggbb' / QColor -> QColor"""
    if isinstance(s, QColor):
        return QColor(s)
    c = QColor(fallback)
    if not s:
        return c
    s = str(s).strip()
    if s.startswith('#'):
        h = s[1:]
        try:
            if len(h) == 8:
                c = QColor(int(h[2:4] + h[4:6] + h[6:8], 16))
                c.setAlpha(int(h[0:2], 16))
            elif len(h) == 6:
                c = QColor('#' + h)
        except Exception:
            pass
    return c


def pix(path):
    if not os.path.exists(path):
        return QPixmap()
    return QPixmap(path)


def tint(pm, color):
    """把单色图标染成任意颜色（透明背景保持不变）"""
    if pm is None or pm.isNull():
        return QPixmap()
    out = QPixmap(pm.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.drawPixmap(0, 0, pm)
    p.setCompositionMode(QPainter.CompositionMode_SourceIn)
    p.fillRect(out.rect(), QColor(color))
    p.end()
    return out


APP_ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'resources', 'icons')


def app_icon(size=0):
    """新扁平化应用图标（基于 Bootstrap Icons, MIT）。size=0 取 256。"""
    name = 'calendar.png' if size == 0 else 'calendar_%d.png' % size
    return icon(os.path.join(APP_ICONS, name))


def icon(path):
    p = pix(path)
    if p.isNull():
        return QIcon()
    return QIcon(p)


def paint_round(painter, rect, radius, color, border=None, border_w=1):
    """画圆角矩形（等效原版 back="clr:...|round=N|border=..."）"""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing, True)
    pen = painter.pen()
    if border:
        from PyQt5.QtGui import QPen
        pen = QPen(qcolor(border), border_w)
    painter.setPen(pen if border else Qt.NoPen)
    if color is not None:
        painter.setBrush(qcolor(color))
    else:
        painter.setBrush(Qt.NoBrush)
    painter.drawRoundedRect(rect, radius, radius)
    painter.restore()


# Qt 自带对话框（如 QColorDialog）的英文文案 → 简体中文
_ZH_LABELS = {
    'OK': u'确定', 'Cancel': u'取消', '&OK': u'确定', '&Cancel': u'取消',
    'Basic colors': u'基本颜色', 'Custom colors': u'自定义颜色',
    'Add to Custom Colors': u'添加到自定义颜色',
    '&Add to Custom Colors': u'添加到自定义颜色',
    'Pick Screen Color': u'拾取屏幕颜色', '&Pick Screen Color': u'拾取屏幕颜色',
    'Cursor at:': u'光标位置：', 'Screen:': u'屏幕：', 'Color:': u'颜色：',
    'HTML:': u'HTML：', '&HTML:': u'HTML：',
    'Red': u'红', 'Green': u'绿', 'Blue': u'蓝',
    'Hue': u'色相', 'Sat': u'饱和度', 'Val': u'明度', 'Alpha': u'透明度',
    'Alpha channel': u'Alpha 通道',
}


def localize_dialog(dlg):
    """把 Qt 自带对话框里的英文控件文案替换成简体中文（无 qt_zh_CN 时的兜底）。"""
    if dlg is None:
        return
    try:
        from PyQt5.QtWidgets import (QPushButton, QLabel, QGroupBox,
                                     QCheckBox, QRadioButton)
        for cls in (QPushButton, QLabel, QGroupBox, QCheckBox, QRadioButton):
            for w in dlg.findChildren(cls):
                t = w.text()
                if not t:
                    continue
                hit = _ZH_LABELS.get(t) or _ZH_LABELS.get(t.replace('&', ''))
                if hit:
                    w.setText(hit)
    except Exception:
        pass


def zh_color_dialog(initial, parent=None, title=u'选择颜色'):
    """颜色选择对话框（自制 Photoshop 风格，见 colorpick.py）。"""
    from .colorpick import ColorDialog
    return ColorDialog(initial, parent, title)


def font(size, bold=False, italic=False):
    f = QFont()
    f.setPointSizeF(size)
    f.setBold(bold)
    f.setItalic(italic)
    return f


class HSep(QWidget):
    """横向分隔线（等效原版 pos=..,2.. 的色块）"""

    def __init__(self, color='#fff0f5f9', parent=None):
        QWidget.__init__(self, parent)
        self._c = color
        self.setFixedHeight(2)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), qcolor(self._c))
