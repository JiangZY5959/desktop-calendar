# -*- coding: utf-8 -*-
"""更新后的「新功能速览」：装好后首次运行弹一次，之后不再打扰。

设计参考（2026-11 调研）：
* UserOnboarding Academy —— 引导的篇幅要跟改动大小匹配，大改动用一次性
  modal / 发布说明，2~5 条为宜；
* Surfer / Notion 的 release notes —— 只给"还没看过的人"自动弹一次；
* zeroheight 设计系统 —— 讲清价值与位置、可跳过、别在用户忙时打断。

落地取舍：这是一个贴桌面的小工具，做多步 tooltip 巡游成本高又容易挡住
日历；所以做成一页浅色卡片（与「关于 / 检查更新」同一套外观），5 条要点
标注功能位置，右上角可关、底部一个「知道了」。

一次性标记用版本键：同一份速览看过即写入 guide/seen_version，下次启动
不再弹。以后又有大改动时，改 GUIDE_VER 即可让新速览再出现一次。
"""
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QPen, QColor, QPixmap
from PyQt5.QtWidgets import (QDialog, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout)

from . import data as D
from . import theme as T
from . import APP_NAME

# 这份速览对应的版本；改这里 + 文案即可用于下一次大更新
GUIDE_VER = '1.5.0.5'
SEEN_KEY = 'guide/seen_version'

# (标题, 说明) —— 说明里尽量写清「在哪找」，而不只是讲功能有多好
ITEMS = (
    (u'左侧常驻待办清单',
     u'待办直接贴在日历左边，不用再点开弹窗；工具栏第一个清单按钮可随时收起 / 展开。'),
    (u'一键切换月 / 周视图',
     u'工具栏的视图按钮点一下就在月历和周历之间切换，不用再展开菜单。'),
    (u'完成勾选与统计筛选',
     u'待办前面的圆圈可勾选完成；点统计条「共 N 项 / 已完成 / 未完成」按完成态筛选，'
     u'还能叠加「今天 / 本周 / 本月」。'),
    (u'新增待办分单次和重复',
     u'单次只填待办日期；重复要选开始 / 截止日期和频率。月末或闰日会自动兜底到'
     u'最近的有效日期，并告诉你原因。'),
    (u'记住窗口大小和位置',
     u'调好大小和位置后会自动保存，下次打开还是上次的样子。'),
)

CARD = '#F2F6FC'
LINE = '#DCE0E6'
TXT = '#202020'
DIM = '#5A6069'
BLUE = '#2F7BFF'
HOVER = '#F5F8FF'


class GuideDialog(QDialog):
    """一页式新功能速览（无边框圆角卡片，风格与关于 / 更新提示一致）。"""

    W, H = 540, 424

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(u'%s 新功能速览' % APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.W, self.H)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 14)
        root.setSpacing(0)

        head = QHBoxLayout()
        head.setSpacing(9)
        ic = QLabel()
        pm = T.pix(D.res('icons', 'calendar.png'))
        ic.setPixmap(pm.scaled(20, 20, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation))
        head.addWidget(ic, 0, Qt.AlignVCenter)
        ttl = QLabel(u'v1.5 新功能速览')
        ttl.setStyleSheet('color:%s;font-size:16px;font-weight:bold;'
                          'background:transparent;' % TXT)
        head.addWidget(ttl, 0, Qt.AlignVCenter)
        head.addStretch(1)
        bx = QPushButton(u'✕')
        bx.setFixedSize(24, 24)
        bx.setFocusPolicy(Qt.NoFocus)
        bx.setCursor(Qt.PointingHandCursor)
        bx.setToolTip(u'关闭')
        bx.setStyleSheet(
            'QPushButton{background:transparent;border:none;color:#8A8F99;'
            'font-size:14px;}'
            'QPushButton:hover{background:%s;border-radius:4px;color:%s;}'
            % (HOVER, TXT))
        bx.clicked.connect(self.accept)
        head.addWidget(bx, 0, Qt.AlignVCenter)
        root.addLayout(head)

        sub = QLabel(u'这次更新改动不少，花半分钟认识一下：')
        sub.setStyleSheet('color:%s;font-size:12px;background:transparent;'
                          % DIM)
        root.addSpacing(8)
        root.addWidget(sub)
        root.addSpacing(12)

        for i, (title, desc) in enumerate(ITEMS, 1):
            row = QHBoxLayout()
            row.setSpacing(10)
            num = QLabel(str(i))
            num.setFixedSize(20, 20)
            num.setAlignment(Qt.AlignCenter)
            num.setStyleSheet(
                'background:%s;color:#FFFFFF;border-radius:10px;'
                'font-size:11px;font-weight:bold;' % BLUE)
            row.addWidget(num, 0, Qt.AlignTop)

            txt = QVBoxLayout()
            txt.setSpacing(2)
            t = QLabel(title)
            t.setStyleSheet('color:%s;font-size:12px;font-weight:bold;'
                            'background:transparent;' % TXT)
            d = QLabel(desc)
            d.setWordWrap(True)
            d.setStyleSheet('color:%s;font-size:11px;background:transparent;'
                            % DIM)
            txt.addWidget(t)
            txt.addWidget(d)
            row.addLayout(txt, 1)
            root.addLayout(row)
            if i < len(ITEMS):
                root.addSpacing(9)

        root.addStretch(1)
        bottom = QHBoxLayout()
        once = QLabel(u'这个提示只会出现一次')
        once.setStyleSheet('color:#8A8F99;font-size:11px;background:transparent;')
        bottom.addWidget(once, 0, Qt.AlignVCenter)
        bottom.addStretch(1)
        ok = QPushButton(u'知道了')
        ok.setFixedSize(88, 30)
        ok.setFocusPolicy(Qt.NoFocus)
        ok.setCursor(Qt.PointingHandCursor)
        ok.setStyleSheet(
            'QPushButton{background:%s;color:#FFFFFF;border:none;'
            'border-radius:5px;font-size:13px;}'
            'QPushButton:hover{background:#4A8CFF;}' % BLUE)
        ok.clicked.connect(self.accept)
        ok.setDefault(True)
        bottom.addWidget(ok, 0, Qt.AlignVCenter)
        root.addLayout(bottom)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        T.paint_round(p, r, 10, CARD)
        p.setPen(QPen(QColor(LINE)))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 10, 10)
        p.end()


def needed(settings):
    """这份速览是否还没给用户看过。设置读不到时按"看过"处理，别打扰。"""
    if settings is None:
        return False
    try:
        return str(settings.value(SEEN_KEY) or '') != GUIDE_VER
    except Exception:
        return False


def mark_seen(settings):
    """看过即落标记；同步失败也不阻断启动。"""
    if settings is None:
        return
    try:
        settings.setValue(SEEN_KEY, GUIDE_VER)
        settings.sync()
    except Exception:
        pass


def show_once(settings, parent=None):
    """弹一次速览。返回是否真的弹了（调用方据此安排后续动作）。"""
    if not needed(settings):
        return False
    dlg = GuideDialog(parent)
    try:
        dlg.exec_()
    finally:
        # 点「知道了」或右上角关闭都算看过，不再弹第二次
        mark_seen(settings)
    return True
