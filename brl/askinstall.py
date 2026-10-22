# -*- coding: utf-8 -*-
u"""安装后 / 首次运行时的询问对话框（自绘）。

为什么不用 zenity
----------------
不少 UOS 机器上根本没装 zenity / kdialog / yad（本项目的开发环境就是如此），
依赖它们的结果是"装完什么都不弹"。软件自己带着 PyQt5，用它自绘既没有外部
依赖，也不需要 root 去猜 X 授权（以目标用户身份运行即可），观感还与
软件本身一致。

一个窗口问完：早期版本连弹两次（自启、运行），现在合并成一次勾选。
"""
import os
import sys

from PyQt5.QtCore import Qt, QTimer, QRectF, QSettings
from PyQt5.QtGui import QPainter, QColor, QPen, QPixmap
from PyQt5.QtWidgets import (QApplication, QDialog, QLabel, QCheckBox,
                             QPushButton, QVBoxLayout, QHBoxLayout)

from . import APP_NAME
from . import data as D
from . import theme as T
from . import x11fix as X11

TIMEOUT = 60          # 秒；无人应答按"稍后"处理，不卡住安装
CARD = '#FFFFFF'
LINE = '#E3E6EA'
TXT = '#202020'
DIM = '#8A8F99'
BLUE = '#2F7BFF'

CB = ('QCheckBox{color:%s;font-size:13px;spacing:8px;background:transparent;}'
      'QCheckBox::indicator{width:16px;height:16px;border:1px solid #C6CBD2;'
      'border-radius:3px;background:#FFFFFF;}'
      'QCheckBox::indicator:hover{border-color:%s;}'
      'QCheckBox::indicator:checked{background:%s;border:1px solid %s;'
      'image:url(%s);}'
      % (TXT, BLUE, BLUE, BLUE,
         D.res('icons', 'tool_check.png').replace('\\', '/')))


class AskDialog(QDialog):
    """一个窗口问完「开机自启」与「立即运行」。

    ask_run=False 时只问自启（程序已经在跑了，问"立即运行"没意义）。
    """

    def __init__(self, ask_run=True, timeout=TIMEOUT, parent=None):
        QDialog.__init__(self, parent)
        self._ask_run = ask_run
        self._left = timeout
        self._done = False
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setModal(True)
        self.setFixedSize(400, 258 if ask_run else 214)
        self.setWindowModality(Qt.ApplicationModal)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(0)
        card = QVBoxLayout()
        card.setContentsMargins(18, 16, 18, 16)
        card.setSpacing(0)
        outer.addLayout(card)

        head = QHBoxLayout()
        head.setSpacing(10)
        ico = QLabel()
        pm = QPixmap(D.res('icons', 'calendar_32.png'))
        if pm.isNull():
            pm = QPixmap(D.res('icons', 'calendar.png'))
        ico.setPixmap(pm.scaled(26, 26, Qt.KeepAspectRatio,
                                Qt.SmoothTransformation))
        head.addWidget(ico)
        ttl = QLabel(APP_NAME)
        ttl.setStyleSheet('color:%s;font-size:15px;font-weight:bold;' % TXT)
        head.addWidget(ttl)
        head.addStretch(1)
        card.addLayout(head)

        card.addSpacing(12)
        tip = QLabel(u'安装完成，请选择：' if ask_run
                     else u'是否让它在开机后自动启动？')
        tip.setStyleSheet('color:%s;font-size:13px;' % DIM)
        card.addWidget(tip)
        card.addSpacing(12)

        self._cb_auto = QCheckBox(u'开机后自动启动')
        self._cb_auto.setStyleSheet(CB)
        self._cb_auto.setChecked(True)
        self._cb_auto.setCursor(Qt.PointingHandCursor)
        card.addWidget(self._cb_auto)

        self._cb_run = None
        if ask_run:
            card.addSpacing(6)
            self._cb_run = QCheckBox(u'现在就启动 %s' % APP_NAME)
            self._cb_run.setStyleSheet(CB)
            self._cb_run.setChecked(True)
            self._cb_run.setCursor(Qt.PointingHandCursor)
            card.addWidget(self._cb_run)

        card.addStretch(1)

        foot = QHBoxLayout()
        self._lb = QLabel(u'%d 秒后自动关闭' % self._left)
        self._lb.setStyleSheet('color:%s;font-size:12px;' % DIM)
        foot.addWidget(self._lb)
        foot.addStretch(1)
        blater = QPushButton(u'稍后')
        blater.setFixedSize(78, 30)
        blater.setFocusPolicy(Qt.NoFocus)
        blater.setCursor(Qt.PointingHandCursor)
        blater.setStyleSheet(
            'QPushButton{background:#FFFFFF;color:%s;font-size:13px;'
            'border:1px solid %s;border-radius:5px;}'
            'QPushButton:hover{background:#F5F8FF;border-color:%s;}'
            % (TXT, LINE, BLUE))
        blater.clicked.connect(self._later)
        foot.addWidget(blater)
        bok = QPushButton(u'确定')
        bok.setFixedSize(78, 30)
        bok.setFocusPolicy(Qt.NoFocus)
        bok.setCursor(Qt.PointingHandCursor)
        bok.setStyleSheet('QPushButton{background:%s;color:#FFFFFF;border:none;'
                          'border-radius:5px;font-size:13px;}'
                          'QPushButton:hover{background:#4A8CFF;}' % BLUE)
        bok.clicked.connect(self._ok)
        foot.addWidget(bok)
        card.addSpacing(6)
        card.addLayout(foot)

        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        if timeout > 0:
            self._t.start(1000)

    # ---------------- 外观
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(5.5, 5.5, -5.5, -5.5)
        T.paint_round(p, r, 9, CARD)
        p.setPen(QPen(QColor(LINE)))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 9, 9)
        p.end()

    # ---------------- 结果
    def _tick(self):
        self._left -= 1
        if self._left <= 0:
            self._later()
            return
        self._lb.setText(u'%d 秒后自动关闭' % self._left)

    def _ok(self):
        self._done = True
        self._t.stop()
        self.accept()

    def _later(self):
        self._done = False
        self._t.stop()
        self.reject()

    def answers(self):
        """返回 (自启?, 立即运行?)；窗口被关掉时当作全部"不"。"""
        if not self._done:
            return False, False
        return (self._cb_auto.isChecked(),
                bool(self._cb_run and self._cb_run.isChecked()))


def _new_settings():
    p = os.path.join(D.config_dir(), 'calendar.ini')
    return QSettings(p, QSettings.IniFormat)


def asked_before():
    """这个用户是不是已经被问过开机自启了（升级包时不再打扰）。"""
    try:
        st = _new_settings()
        return str(st.value('general/autostart_asked') or '0') == '1'
    except Exception:
        return False


def mark_asked():
    try:
        st = _new_settings()
        st.setValue('general/autostart_asked', 1)
        st.sync()
    except Exception:
        pass


def ask(ask_run=True, parent=None):
    """弹窗询问，返回 (自启?, 运行?)；弹不出来返回 None。"""
    if not X11.display_ok(os.environ.get('DISPLAY')):
        return None
    app = QApplication.instance()
    if app is None:
        return None          # 由 CLI 入口自己创建 QApplication
    dlg = AskDialog(ask_run=ask_run, parent=parent)
    dlg.exec_()
    return dlg.answers()


def main(ask_run=True, argv=None):
    """命令行入口：把结果打印出去，安装脚本照着做。

    退出码：0=问过（含用户选"稍后"），2=之前已问过不必再问，
    3=这里弹不了窗（交给安装脚本的其它手段），4=异常。
    """
    try:
        if asked_before():
            sys.stdout.write('asked=1\n')
            return 2
        if not X11.display_ok(os.environ.get('DISPLAY')):
            sys.stdout.write('no-display\n')
            return 3
        app = QApplication.instance() or QApplication(argv or sys.argv[:1])
        dlg = AskDialog(ask_run=ask_run)
        dlg.exec_()
        auto, run = dlg.answers()
        mark_asked()
        sys.stdout.write('autostart=%d\n' % (1 if auto else 0))
        if ask_run:
            sys.stdout.write('run=%d\n' % (1 if run else 0))
        return 0
    except Exception:
        return 4
