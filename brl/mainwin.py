# -*- coding: utf-8 -*-
"""主窗口（桌面悬浮日历）。"""
import os
import datetime

from PyQt5.QtCore import Qt, QTimer, QRectF, QRect, QSize, QUrl
from PyQt5.QtGui import (QPainter, QColor, QPixmap, QCursor, QPen, QIcon,
                         QFont, QDesktopServices)
from PyQt5.QtWidgets import (QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
                             QMenu, QSystemTrayIcon, QApplication, QDialog,
                             QMessageBox, QSizeGrip, QFrame, QLayout)

from . import data as D
from . import theme as T
from . import lunar as L
from . import store as S
from .caltable import CalTable
from .todo import (TodoEditDialog, TodoListDialog, REMIND_LEAD, remind_lead)
from .settings import SettingsDialog
from .updatedlg import UpdateFlow
from . import x11fix as X11

from . import APP_NAME, APPID, __version__ as APP_VER


class AboutDialog(QDialog):
    """关于窗口：作者、项目主页、版本与简介。

    底色固定用与选项设置一致的浅色卡片（#F2F6FC），不跟随日历主题，
    免得用户把主题调深之后这里跟着变黑、看不清。
    """

    W, H = 420, 396

    def __init__(self, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(u'关于 %s' % APP_NAME)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(self.W, self.H)
        try:
            from . import update as U
            page = U.PAGE
        except Exception:
            page = ''
        gh = 'https://github.com/JiangZY5959/desktop-calendar'

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 16)
        lay.setSpacing(0)

        top = QHBoxLayout()
        ttl = QLabel(u'关于 %s' % APP_NAME)
        ttl.setStyleSheet('color:#202020;font-size:16px;font-weight:bold;')
        top.addWidget(ttl)
        top.addStretch(1)
        bx = QPushButton(u'✕')
        bx.setFixedSize(26, 26)
        bx.setCursor(Qt.PointingHandCursor)
        bx.setStyleSheet(
            'QPushButton{background:transparent;border:none;'
            'color:#8A8F99;font-size:15px;}'
            'QPushButton:hover{background:#E8EDF5;border-radius:4px;'
            'color:#202020;}')
        bx.clicked.connect(self.accept)
        top.addWidget(bx)
        lay.addLayout(top)
        lay.addSpacing(10)
        lay.addWidget(self._sep())
        lay.addSpacing(14)

        lay.addLayout(self._row(u'版本', QLabel(u'v%s' % APP_VER)))
        lay.addSpacing(8)
        lay.addLayout(self._row(u'作者', QLabel(u'JiangZY')))
        lay.addSpacing(8)
        # 项目主页：只留两个站点图标，点图标直达对应仓库。
        # 不再写"GitCode（国内）/GitHub"文字——哪个图标是哪个站，
        # 悬停一下就有说明；没取到图标时自动跳过，不摆一个空按钮。
        pages = QHBoxLayout()
        pages.setSpacing(6)
        for icon_name, url, tip in (
                ('site_gitcode.png', page, u'GitCode 项目主页'),
                ('site_github.png', gh, u'GitHub 项目主页')):
            if not url:
                continue
            pm = T.pix(D.res('icons', icon_name))
            if pm.isNull():
                continue
            pages.addWidget(self._icon_link(pm, url, tip))
        pages.addStretch(1)
        lay.addLayout(self._row(u'项目主页', pages))
        lay.addSpacing(14)
        lay.addWidget(self._sep())
        lay.addSpacing(14)

        intro = QLabel(
            u'一款为 UOS / 飞腾（aarch64）打造的桌面日历小工具。\n\n'
            u'· 月视图 / 周视图，农历、节气、节日、法定节假日与调休\n'
            u'· 待办记事与定时提醒\n'
            u'· 主题、颜色与透明度自由定制\n\n'
            u'本地应用：无账号、无会员、无需登录，\n'
            u'所有数据仅保存在本机 ~/.local/share/desktop-calendar/。')
        intro.setWordWrap(True)
        intro.setStyleSheet('color:#5A6069;font-size:13px;line-height:150%;')
        lay.addWidget(intro)
        lay.addStretch(1)

        bot = QHBoxLayout()
        bot.addStretch(1)
        bok = QPushButton(u'确定')
        bok.setFixedSize(88, 32)
        bok.setCursor(Qt.PointingHandCursor)
        bok.setStyleSheet(
            'QPushButton{background:#FFFFFF;color:#202020;'
            'border:1px solid #DCE0E6;border-radius:5px;font-size:13px;}'
            'QPushButton:hover{background:#F5F8FF;border-color:#A9CDF7;}')
        bok.clicked.connect(self.accept)
        bot.addWidget(bok)
        lay.addLayout(bot)

    @staticmethod
    def _sep():
        f = QFrame()
        f.setFrameShape(QFrame.HLine)
        f.setFixedHeight(1)
        f.setStyleSheet('background:#E6E7E8;border:none;')
        return f

    @staticmethod
    def _row(label, widget):
        h = QHBoxLayout()
        h.setSpacing(10)
        lb = QLabel(label)
        lb.setFixedWidth(62)
        lb.setStyleSheet('color:#8A8F99;font-size:13px;')
        h.addWidget(lb)
        if isinstance(widget, QLayout):
            h.addLayout(widget, 1)
        else:
            widget.setStyleSheet('color:#202020;font-size:13px;')
            h.addWidget(widget)
        h.addStretch(1)
        return h

    @staticmethod
    def _icon_link(pm, url, tip):
        """带站点图标的跳转按钮：细边框小卡片，点一下开浏览器。"""
        b = QPushButton()
        b.setFixedSize(36, 36)
        b.setIcon(QIcon(pm))
        b.setIconSize(QSize(24, 24))
        b.setFlat(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        b.setToolTip(tip)
        b.setStyleSheet(
            'QPushButton{background:#FFFFFF;border:1px solid #DCE0E6;'
            'border-radius:6px;padding:2px;}'
            'QPushButton:hover{background:#F5F8FF;border-color:#A9CDF7;}')
        b.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        return b

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        T.paint_round(p, r, 10, '#F2F6FC')
        p.setPen(QPen(QColor('#DCE0E6')))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 10, 10)
        p.end()


class RemindPopup(QDialog):
    """待办提醒弹窗。

    外观完全跟随主窗口：同一套主题配色、同样的圆角 + 细描边，
    底层先铺一层"不透明底色"再叠主题背景（主题背景透明度可能很低），
    这样无论用户把透明度调到多少，弹窗始终看得清、也和主界面一个风格。
    """

    def __init__(self, todo, theme=None, parent=None):
        QDialog.__init__(self, parent)
        self.setWindowTitle(u'待办提醒')
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                            | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(360, 196)
        self._todo = todo

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(0)

        # 标题行：小时钟 + 标题 + 关闭
        head = QHBoxLayout()
        head.setSpacing(6)
        self._logo = QLabel()
        self._logo.setFixedSize(18, 18)
        head.addWidget(self._logo, 0, Qt.AlignVCenter)
        title = QLabel(u'待办提醒')
        title.setObjectName('popTitle')
        head.addWidget(title, 0, Qt.AlignVCenter)
        head.addStretch(1)
        self._close = QPushButton()
        self._close.setFixedSize(20, 20)
        self._close.setFlat(True)
        self._close.setFocusPolicy(Qt.NoFocus)
        self._close.setCursor(Qt.PointingHandCursor)
        self._close.setToolTip(u'关闭')
        self._close.clicked.connect(self.reject)
        head.addWidget(self._close, 0, Qt.AlignVCenter)
        lay.addLayout(head)
        lay.addSpacing(8)

        # 内容
        body = QVBoxLayout()
        body.setSpacing(4)
        self._content = QLabel(todo.get('content', ''))
        self._content.setWordWrap(True)
        self._content.setObjectName('popContent')
        when = u'%s  %s' % (todo.get('date', ''), todo.get('remind_time', ''))
        lead = todo.get('lead') or 0
        if lead:
            when += u'（%d 天后到期）' % lead
        info = QLabel(when)
        info.setObjectName('popInfo')
        body.addWidget(self._content)
        body.addWidget(info)
        body.addStretch(1)
        lay.addLayout(body, 1)

        lay.addSpacing(6)
        btns = QHBoxLayout()
        btns.addStretch(1)
        self._ok = QPushButton(u'知道了')
        self._ok.setFixedSize(92, 30)
        self._ok.setFocusPolicy(Qt.NoFocus)
        self._ok.setCursor(Qt.PointingHandCursor)
        self._ok.setObjectName('popOk')
        self._ok.clicked.connect(self.accept)
        btns.addWidget(self._ok, 0, Qt.AlignRight)
        lay.addLayout(btns)
        self.set_theme(theme)      # 控件都建好后再上色

    # ------------------------------------------------ 主题
    def set_theme(self, theme):
        cfg = dict(theme or {})
        self._theme = cfg
        txt = T.qcolor(cfg.get('txtclr', '#FFFFFF'))
        light = 0.299 * txt.red() + 0.587 * txt.green() + 0.114 * txt.blue() > 140
        self._text_light = light
        self._txt = txt.name()
        hover = 'rgba(255,255,255,45)' if light else 'rgba(0,0,0,35)'
        cline = QColor(txt)
        cline.setAlpha(70)
        dim = QColor(txt)
        dim.setAlpha(160)
        pm = T.pix(D.res('icons', 'clock.png'))
        self._logo.setPixmap(T.tint(pm, txt.name()))
        self._close.setIcon(QIcon(T.tint(T.pix(D.res('icons', 'tool_close.png')),
                                         txt.name())))
        self.setStyleSheet(
            'QLabel#popTitle{color:%s;font-size:14px;font-weight:bold;}'
            'QLabel#popContent{color:%s;font-size:16px;font-weight:bold;}'
            'QLabel#popInfo{color:%s;font-size:13px;}'
            'QPushButton#popOk{background:transparent;color:%s;font-size:14px;'
            'border:1px solid %s;border-radius:5px;}'
            'QPushButton#popOk:hover{background:%s;}'
            'QPushButton:hover{background:%s;border-radius:4px;}'
            % (self._txt, self._txt, dim.name(), self._txt, cline.name(),
               hover, hover))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        # 先把主题背景的透明度做封顶，再叠到不透明底色上：
        # 某些主题的背景是不透明度较高的浅色，直接整块叠上去会出现
        # "白字压浅底"的低对比情况；封顶后仍保留主题色调，同时保证
        # "深底配浅字 / 浅底配深字"始终成立。
        base = '#1E222A' if self._text_light else '#FFFFFF'
        bg = T.qcolor(self._theme.get('mainbgndclr', '#B4101216'))
        bg.setAlpha(min(bg.alpha(), 112))
        T.paint_round(p, r, 10, base)
        T.paint_round(p, r, 10, bg)
        p.setPen(QPen(T.qcolor(self._theme.get('borderoutclr', '#3CFFFFFF'))))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 10, 10)
        p.end()


class MainWindow(QWidget):
    def __init__(self, store, ctx):
        QWidget.__init__(self, None, Qt.FramelessWindowHint)
        self._store = store
        self._ctx = ctx
        self._drag = None
        self._locked = False
        self._pops = []                 # 提醒弹窗引用列表（防止被 GC 掉）
        self._tb_off = False            # 是否已向窗口管理器声明脱离任务栏
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(T.app_icon())

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 12, 12)
        root.setSpacing(2)

        # ---- 顶部单行：左侧月份导航 + 今日，右侧三个工具按钮（同一行）
        top = QHBoxLayout()
        top.setSpacing(4)

        self._b_prev = self._tool_btn(u'上个月', 20, icon='nav_prev')
        self._b_next = self._tool_btn(u'下个月', 20, icon='nav_next')
        self._b_today = self._tool_btn(u'回到今天', 20, icon='nav_today')
        self._lb_month = QLabel('')
        self._lb_month.setStyleSheet('color:white;font-size:17px;font-weight:bold;')
        self._b_prev.clicked.connect(lambda: self._shift_month(-1))
        self._b_next.clicked.connect(lambda: self._shift_month(1))
        self._b_today.clicked.connect(self._go_today)
        top.addWidget(self._b_prev)
        top.addWidget(self._lb_month)
        top.addWidget(self._b_next)
        top.addSpacing(6)
        top.addWidget(self._b_today)
        top.addStretch(1)

        self._btn_view = self._tool_btn(u'月视图 / 周视图', icon='view')
        self._btn_lock = self._tool_btn(u'锁定 / 解锁窗口', icon='lock')
        self._btn_menu = self._tool_btn(u'菜单（选项设置等）', icon='gear')
        self._btn_close = self._tool_btn(u'隐藏日历（托盘图标可找回）', icon='close')
        self._btn_view.clicked.connect(self._on_view)
        self._btn_lock.clicked.connect(self._on_lock)
        self._btn_menu.clicked.connect(lambda: self._menu().exec_(QCursor.pos()))
        self._btn_close.clicked.connect(self.hide)
        for b in (self._btn_view, self._btn_lock, self._btn_menu, self._btn_close):
            top.addWidget(b)
            top.addSpacing(2)
        root.addLayout(top)

        # ---- 日历
        self._cal = CalTable()
        self._cal.daySelected.connect(self._on_select)
        self._cal.dayActivated.connect(self._on_activate)
        self._cal.monthChanged.connect(self._on_month_changed)
        root.addWidget(self._cal, 1)

        # 右下角缩放手柄（无边框窗口需要手动提供）
        self._grip = QSizeGrip(self)
        self._grip.setFixedSize(16, 16)
        self._grip.setStyleSheet('QSizeGrip{background:transparent;}')

        self._apply_theme()
        st = self._store.settings()
        self._cal.set_options(
            weekend=str(st.value('cal/showweekend', '1')) == '1',
            lunnar=str(st.value('cal/showlunnar', '1')) == '1',
            jieri=str(st.value('cal/showjieri', '1')) == '1',
            line=str(st.value('cal/showline', '1')) == '1',
            ban=str(st.value('cal/showban', '1')) == '1',
            firstday=int(st.value('cal/firstday') or 0),
            week=str(st.value('cal/showweek', '0')) == '1',
            tips=str(st.value('cal/showtips', '1')) == '1',
            weekstart=str(st.value('cal/weekstart') or 'jan1'),
            qscale=int(st.value('cal/qscale') or 11))
        self._cal.set_scale(float(st.value('cal/scale') or 10) / 10.0)
        self._cal.set_month(datetime.date.today())
        self._on_select(datetime.date.today())
        w, h = self._default_size()
        self.resize(w, h)

        # 计时器：跨天 + 待办提醒
        self._last_day = datetime.date.today()
        self._t = QTimer(self)
        self._t.timeout.connect(self._tick)
        self._t.start(15000)
        self._tick()

        # 检查更新：启动几秒后先判断一次是否到期，之后每小时复核，
        # 长时间开着软件也能到点自动检查（默认每天一次，可在设置里改）。
        self._updater = UpdateFlow(store, self)
        self._upd_t = QTimer(self)
        self._upd_t.timeout.connect(self._auto_update)
        self._upd_t.start(3600 * 1000)
        QTimer.singleShot(5000, self._auto_update)

        # 安装时没能弹窗问过的话，首次启动补问一次开机自启
        QTimer.singleShot(900, self._ask_autostart_once)

    # ------------------------------------------------ 首次启动补问
    # 只有真正装到 /opt/apps 下才提示：源码目录里跑时不打扰，也不会在
    # 自动化验证里冒出个模态窗把测试卡住。
    def _installed(self):
        return os.path.isdir(os.path.join(
            '/opt/apps', APPID, 'files', 'brl'))

    def _ask_autostart_once(self):
        if not self._installed():
            return
        try:
            from . import askinstall as AI
            if AI.asked_before():
                return
            ans = AI.ask(ask_run=False, parent=self)
            if ans is None:
                return
            auto, _run = ans
            from . import appctx as AX
            st = self._store.settings()
            st.setValue('app/autostart', '1' if auto else '0')
            st.sync()
            AX.apply_autostart(self._store)
            AI.mark_asked()
        except Exception:
            pass

    # ------------------------------------------------ 尺寸 / 位置
    def _screen(self):
        return QApplication.desktop().availableGeometry()

    # 出厂观感基准：1920x1040 可用区下「窗口 1004x805 落在 (716,147)」。
    # 换到别的分辨率/屏幕时，按同一套比例等比换算，保证内容观感一致。
    REF_SCREEN = (1920, 1040)
    REF_RECT = (716, 147, 1004, 805)
    MIN_SIZE = (560, 420)

    def _adaptive_rect(self):
        """按当前屏幕可用区等比算出「出厂默认」窗口位置与大小。"""
        g = self._screen()
        rw, rh = self.REF_SCREEN
        rx, ry, r0w, r0h = self.REF_RECT
        gw, gh, minw, minh = g.width(), g.height(), self.MIN_SIZE[0], self.MIN_SIZE[1]
        # 等比缩放：取较小的一边，保持窗口长宽比不变（内容比例才不会变形）
        f = min(gw / float(rw), gh / float(rh))
        f = max(f, max(minw / float(r0w), minh / float(r0h)))
        w = int(round(r0w * f))
        h = int(round(r0h * f))
        w = max(minw, min(w, max(minw, gw - 20)))
        h = max(minh, min(h, max(minh, gh - 20)))
        x = g.left() + int(round(gw * rx / float(rw)))
        y = g.top() + int(round(gh * ry / float(rh)))
        x = max(g.left(), min(x, g.right() - w))
        y = max(g.top(), min(y, g.bottom() - h))
        return x, y, w, h

    def _default_size(self):
        return self._adaptive_rect()[2], self._adaptive_rect()[3]

    def _screen_sig(self):
        g = self._screen()
        return '%dx%d' % (g.width(), g.height())

    def sizeHint(self):
        return QSize(*self._default_size())

    def _clamp_pos(self):
        """确保窗口完整落在屏幕内"""
        g = self._screen()
        x = max(g.left(), min(self.x(), g.right() - self.width()))
        y = max(g.top(), min(self.y(), g.bottom() - self.height()))
        self.move(x, y)

    def _save_geo(self):
        st = self._store.settings()
        st.setValue('ui/pos', '%d,%d' % (self.x(), self.y()))
        st.setValue('ui/size', '%d,%d' % (self.width(), self.height()))
        st.setValue('ui/screensize', self._screen_sig())
        st.sync()

    def restore_pos(self):
        """恢复上次的位置尺寸。

        * 有存档：沿用存档。
          若存档是在**别的分辨率**下保存的（换机器 / 换显示器 / 调整分辨率），
          则按新屏幕等比换算，保证观感一致；比例来自于这份存档本身。
          用户自己拖动、拉伸后的结果因此不会被覆盖，只是随屏幕同步缩放。
        * 无存档（首次安装打开）：直接用出厂默认比例（见 _adaptive_rect）。
        """
        st = self._store.settings()
        g = self._screen()
        cur = self._screen_sig()
        size_v = str(st.value('ui/size') or '')
        pos_v = str(st.value('ui/pos') or '')
        sig = str(st.value('ui/screensize') or '')
        moved = sized = False
        if size_v:
            try:
                w, h = size_v.split(',')
                w, h = int(w), int(h)
                if sig and sig != cur:
                    try:
                        sw, sh = sig.split('x')
                        kw = g.width() / float(sw)
                        kh = g.height() / float(sh)
                        k = min(kw, kh)          # 等比，保持长宽比
                        w, h = int(round(w * k)), int(round(h * k))
                        if pos_v:
                            px, py = pos_v.split(',')
                            self.move(g.left() + int(round((int(px) - g.left()) * kw)),
                                      g.top() + int(round((int(py) - g.top()) * kh)))
                            moved = True
                    except Exception:
                        pass
                self.resize(max(self.MIN_SIZE[0], min(w, g.width())),
                            max(self.MIN_SIZE[1], min(h, g.height())))
                sized = True
            except Exception:
                pass
        if not moved:
            if pos_v:
                try:
                    x, y = pos_v.split(',')
                    self.move(int(x), int(y))
                except Exception:
                    pass
            else:
                self.move(self._adaptive_rect()[0], self._adaptive_rect()[1])
        if not sized:
            _x, _y, aw, ah = self._adaptive_rect()
            self.resize(aw, ah)
        self._clamp_pos()
        # 只有"推算出新几何"时才落盘（首次打开 / 换了分辨率）；
        # 单纯沿用已有存档时不写，免得覆盖用户精心摆好的位置和尺寸。
        if (not size_v or not pos_v) or (sig and sig != cur):
            self._save_geo()

    def resizeEvent(self, ev):
        if hasattr(self, '_grip'):
            self._grip.move(self.width() - 18, self.height() - 18)
        QWidget.resizeEvent(self, ev)

    def hideEvent(self, ev):
        self._save_geo()
        QWidget.hideEvent(self, ev)

    def closeEvent(self, ev):
        self._save_geo()
        QWidget.closeEvent(self, ev)

    # ------------------------------------------------ UI 工具
    # 内置图标键 -> 资源文件名（统一扁平白色风格，避免精灵图裁切）
    ICON_FILES = {'view': 'tool_view.png', 'lock': 'tool_lock.png',
                  'unlock': 'tool_unlock.png', 'gear': 'tool_gear.png',
                  'close': 'tool_close.png',
                  'nav_prev': 'nav_prev.png', 'nav_next': 'nav_next.png'}

    def _icon_pix(self, key):
        """图标键 -> QPixmap（注意图标在 resources/icons/，不在 img/ 下）。
        主题背景为浅色时自动把图标染成深色，保证可见。
        nav_today 特殊：绘制带"今"字的图标（用户指定）。"""
        dark = getattr(self, '_icon_dark', False)
        color = QColor('#3A3A3A') if dark else QColor('#FFFFFF')
        if key == 'nav_today':
            pm = QPixmap(24, 24)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            p.setRenderHint(QPainter.TextAntialiasing)
            p.setPen(color)
            f = QFont()
            f.setBold(True)
            f.setPixelSize(19)
            p.setFont(f)
            p.drawText(QRect(0, 0, 24, 24), Qt.AlignCenter, u'今')
            p.end()
            return pm
        pm = T.pix(D.res('icons', self.ICON_FILES[key]))
        if pm.isNull():
            return pm
        out = QPixmap(pm.size())
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.drawPixmap(0, 0, pm)
        p.setCompositionMode(QPainter.CompositionMode_SourceIn)
        p.fillRect(out.rect(), color)
        p.end()
        return out

    def _chrome_for_theme(self):
        """根据主题背景明暗返回（图标取深色?, 悬停底色, 标题色）"""
        bg = T.qcolor(self._theme.get('mainbgndclr', '#B4101216'))
        lum = 0.299 * bg.red() + 0.587 * bg.green() + 0.114 * bg.blue()
        if lum > 150:   # 浅色背景
            return True, 'rgba(0,0,0,30)', '#303030'
        return False, 'rgba(255,255,255,40)', '#FFFFFF'

    def _refresh_chrome(self):
        """主题切换后刷新按钮图标 / 悬停底色 / 月份文字颜色"""
        dark, hover, txt = self._chrome_for_theme()
        self._icon_dark = dark
        ss = ('QPushButton{background:transparent;border:none;}'
              'QPushButton:hover{background:%s;border-radius:4px;}' % hover)
        for b in (self._b_prev, self._b_next, self._b_today,
                  self._btn_view, self._btn_lock, self._btn_menu, self._btn_close):
            b.setStyleSheet(ss)
        self._b_prev.setIcon(QIcon(self._icon_pix('nav_prev')))
        self._b_next.setIcon(QIcon(self._icon_pix('nav_next')))
        self._b_today.setIcon(QIcon(self._icon_pix('nav_today')))
        self._btn_view.setIcon(QIcon(self._icon_pix('view')))
        # 图标表示「当前状态」：未锁定=可移动(开锁图)，已锁定=不可动(上锁图)
        self._btn_lock.setIcon(QIcon(self._icon_pix(
            'lock' if self._locked else 'unlock')))
        self._btn_menu.setIcon(QIcon(self._icon_pix('gear')))
        self._btn_close.setIcon(QIcon(self._icon_pix('close')))
        self._lb_month.setStyleSheet('color:%s;font-size:17px;font-weight:bold;' % txt)

    def _tool_btn(self, tips, size=24, icon=None):
        """工具按钮。图标一律取自自制扁平图标集 resources/icons。"""
        b = QPushButton()
        b.setProperty('iconKey', icon or '')
        if icon:
            try:
                pm = self._icon_pix(icon)
            except KeyError:
                pm = QPixmap()
            if not pm.isNull():
                b.setIcon(QIcon(pm))
                b.setIconSize(QSize(size, size))
        b.setFixedSize(size + 8, size + 8)
        b.setFlat(True)
        b.setFocusPolicy(Qt.NoFocus)   # 桌面小部件不需要焦点圈（UOS 会画蓝色圆角框）
        b.setToolTip(tips)
        b.setCursor(Qt.PointingHandCursor)
        b.setStyleSheet('QPushButton{background:transparent;border:none;}'
                        'QPushButton:hover{background:rgba(255,255,255,40);border-radius:4px;}')
        return b

    def _color_overrides(self):
        """读取用户颜色覆盖（color/* 键），返回映射到主题字段名的 dict"""
        st = self._store.settings()
        m = {'txtclr': 'txtclr', 'weekclr': 'weekclr', 'jiericlr': 'jiericlr',
             'todayclr': 'todayclr', 'mainbg': 'mainbgndclr',
             'gridbg': 'gridbgndclr', 'weekgridbg': 'weekgridbgndclr',
             'borderout': 'borderoutclr', 'borderin': 'borderinclr'}
        out = {}
        for k, tk in m.items():
            v = st.value('color/' + k)
            if not v:
                continue
            v = str(v).strip()
            h = v[1:] if v.startswith('#') else ''
            # 必须是合法的 #RRGGBB / #AARRGGBB；残缺串（如被写坏的
            # #001AEAE8）一律忽略，回退到主题色，绝不让主界面变一大块白
            if len(h) not in (6, 8):
                continue
            try:
                int(h, 16)
            except ValueError:
                continue
            out[tk] = v
        return out

    def _apply_theme(self):
        idx = int(self._store.settings().value('ui/theme') or 0)
        cfg = dict(T.ALL_THEMES[idx % len(T.ALL_THEMES)])
        cfg.update(self._color_overrides())
        self._theme = cfg
        self._cal.set_theme(cfg)
        self._refresh_chrome()
        self.update()

    # ------------------------------------------------ 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # 简洁细边框：圆角填充主题背景 + 单线描边（不使用渐变）
        r = QRectF(self.rect()).adjusted(0, 0, -1, -1)
        T.paint_round(p, r, 10, self._theme.get('mainbgndclr', '#B4101216'))
        p.setPen(QPen(T.qcolor(self._theme.get('borderoutclr', '#3CFFFFFF'))))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 10, 10)

    # ------------------------------------------------ 交互
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton and not self._locked:
            self._drag = ev.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.LeftButton and not self._locked:
            self.move(ev.globalPos() - self._drag)

    def mouseReleaseEvent(self, ev):
        if self._drag is not None:
            self._drag = None
            self._clamp_pos()
            self._save_geo()

    def mouseDoubleClickEvent(self, ev):
        self._on_activate(self._cal.selected())

    def _shift_month(self, step):
        d = self._cal.month() or datetime.date.today()
        y, m = d.year, d.month + step
        if m < 1:
            y, m = y - 1, 12
        elif m > 12:
            y, m = y + 1, 1
        self._cal.set_month(datetime.date(y, m, 1))

    def _go_today(self):
        self._cal.set_month(datetime.date.today())
        self._cal.set_selected(datetime.date.today())

    def _on_select(self, d):
        self._lb_month.setText('%d年%d月' % (d.year, d.month))
        self._reload_todos()

    def _on_month_changed(self, d):
        self._lb_month.setText('%d年%d月' % (d.year, d.month))

    def _on_activate(self, d):
        dlg = TodoListDialog(self._store, d, self)
        if dlg.exec_() == QDialog.Accepted:
            self._reload_todos()

    def _reload_todos(self):
        d = self._cal.selected() or datetime.date.today()
        d0 = d - datetime.timedelta(days=180)
        d1 = d + datetime.timedelta(days=180)
        todos = {}
        for dd in [d0 + datetime.timedelta(days=i) for i in range((d1 - d0).days + 1)]:
            rows = self._store.for_date(dd)
            if rows:
                todos[dd.isoformat()] = rows
        self._cal.set_todos(todos)

    def _tick(self):
        today = datetime.date.today()
        if today != self._last_day:
            self._last_day = today
            self._cal.refresh_today()
            self._go_today()
        self._check_remind()

    # ------------------------------------------------ 提醒
    def _forget_pop(self, pop):
        try:
            self._pops.remove(pop)
        except ValueError:
            pass

    def _log_remind(self, msg):
        """提醒触发情况写入 remind.log，便于排查"没提醒"类问题。"""
        try:
            d = D.data_dir()
            if not os.path.isdir(d):
                os.makedirs(d)
            with open(os.path.join(d, 'remind.log'), 'a') as f:
                f.write('%s  %s\n' % (datetime.datetime.now().strftime('%F %T'), msg))
        except Exception:
            pass

    def _check_remind(self):
        now = datetime.datetime.now()
        hhmm = now.strftime('%H:%M')
        today = now.date()
        # 每种提醒方式对应"提前多少天"：当天=0、前一天=1、前三天=3、
        # 前一周=7……到期日 = 今天 + 提前天数，正好轮到那天的才该弹。
        # 之前只有两种方式时写成 ((2, today), (1, today+1))，方向别搞反：
        # "前一天提醒"查的是明天到期、今天提前一天弹。
        leads = sorted(set(v for v in REMIND_LEAD.values() if v is not None))
        by_lead = {}
        for lead in leads:
            day = today + datetime.timedelta(days=lead)
            try:
                by_lead[lead] = self._store.for_date(day)
            except Exception:
                by_lead[lead] = []
        for lead in leads:
            day = today + datetime.timedelta(days=lead)
            for t in by_lead[lead]:
                if t.get('done'):
                    continue
                if remind_lead(t.get('remind')) != lead:
                    continue
                want = (t.get('remind_time') or '')[:5]
                if not want or want > hhmm:
                    continue
                key = 'remind/%s/%s' % (t['id'], day.isoformat())
                st = self._store.settings()
                if str(st.value(key, '0')) == '1':
                    continue
                st.setValue(key, '1')
                st.sync()
                row = dict(t)
                row['date'] = day.isoformat()
                row['lead'] = lead
                self._log_remind(u'触发 #%s %s %s %s' % (
                    t['id'], day.isoformat(), want, row.get('content', '')))
                # 必须长期持有引用：否则弹窗创建后立刻被 Python 垃圾回收，
                # 表现为"添加了提醒却一条都不弹"。
                try:
                    pop = RemindPopup(row, getattr(self, '_theme', None))
                    self._pops.append(pop)
                    pop.destroyed.connect(lambda _o=None, p=pop: self._forget_pop(p))
                    pop.show()
                    pop.raise_()
                    pop.activateWindow()
                except Exception:
                    # 退兜：自绘弹窗万一失败，用标准对话框顶上，绝不静默吞掉提醒
                    QMessageBox.information(
                        None, u'待办提醒',
                        u'%s %s\n%s' % (row.get('date', ''), row.get('remind_time', ''),
                                        row.get('content', '')))

    # ------------------------------------------------ 视图 / 菜单
    def _on_view(self):
        m = QMenu(self)
        for i, name in enumerate((u'月视图', u'周视图')):
            a = m.addAction(name)
            a.setCheckable(True)
            a.setChecked(self._cal.view() == ('month' if i == 0 else 'week'))
            a.triggered.connect(lambda checked=False, i=i: self._set_view(i))
        m.addSeparator()
        a = m.addAction(u'待办清单')
        a.triggered.connect(self._on_activate)
        m.exec_(QCursor.pos())

    def _set_view(self, i):
        self._cal.set_view('month' if i == 0 else 'week')

    def _on_lock(self):
        self._locked = not self._locked
        self._apply_lock_flags()
        self._refresh_chrome()
        self._btn_lock.setToolTip(u'解锁窗口' if self._locked else u'锁定窗口')

    def _apply_lock_flags(self):
        """锁定=紧贴桌面（永远垫在其他软件之下）；解锁=无层级限制。

        直接改 X11 的 _NET_WM_STATE_BELOW，不重建窗口：
        setWindowFlags() 会销毁并重建原生窗口，点锁定时界面会闪一下。
        仅在 xcb 平台走 X11；离屏测试等环境回退 Qt 原生方案。
        """
        from PyQt5.QtGui import QGuiApplication
        if QGuiApplication.platformName() == 'xcb':
            self._apply_skip_taskbar(_force=True)
            if X11.set_below(self._win_id(), self._locked):
                if self._locked:
                    self.lower()
                self._reassert_wm_state(0)
                self._reassert_wm_state(200)
                self._reassert_wm_state(700)
                return True
        # 非 X 环境（offscreen 测试等）回退到 Qt 原生方案（会有一次重建）
        pos = self.pos()
        flags = Qt.FramelessWindowHint
        if self._locked:
            flags |= Qt.WindowStaysOnBottomHint
        self.setWindowFlags(flags)
        self.move(pos)
        self.show()
        if self._locked:
            self.lower()
        self._apply_skip_taskbar(_force=True)
        return False

    def _reassert_wm_state(self, delay=0):
        """稍后再确认一次窗口状态。

        窗口管理器在窗口映射之后会按自己的状态表回写 _NET_WM_STATE，
        刚写进去的 BELOW 有概率被抹掉；这里延迟补一次，让它自愈。
        """
        def _do():
            from PyQt5.QtGui import QGuiApplication
            if QGuiApplication.platformName() != 'xcb':
                return
            wid = self._win_id()
            if not wid:
                return
            want = ['SKIP_TASKBAR', 'SKIP_PAGER']
            if self._locked:
                want.append('BELOW')
            X11.assert_state(wid, want)
        if delay:
            QTimer.singleShot(delay, _do)
        else:
            _do()

    def _win_id(self):
        try:
            return int(self.winId())
        except Exception:
            return 0

    def _apply_skip_taskbar(self, _force=False, _try=0):
        """让窗口不出现在任务栏/分页器。

        窗口映射后部分窗口管理器才处理该属性，故在 show 之后再补一次。
        """
        from PyQt5.QtGui import QGuiApplication
        if QGuiApplication.platformName() != 'xcb':
            return
        if self._tb_off and not _force:
            return
        wid = self._win_id()
        if not wid:
            return
        if X11.skip_taskbar(wid):
            self._tb_off = True
        elif _try < 2:
            # 首次可能还没拿到原生窗口句柄，稍后重试
            QTimer.singleShot(300, lambda: self._apply_skip_taskbar(
                True, _try + 1))

    def showEvent(self, ev):
        QWidget.showEvent(self, ev)
        self._apply_skip_taskbar(_force=True)

    def _menu(self):
        m = QMenu(self)
        m.setStyleSheet(T.menu_style())
        m.addAction(u'检查更新', lambda: self.check_updates(False))
        m.addAction(u'选项设置', self.open_settings)
        m.addAction(u'关于', self._about)
        m.addSeparator()
        m.addAction(u'退出软件', lambda: self._ctx.quit())
        return m

    # ------------------------------------------------ 检查更新
    def _auto_update(self):
        """到点才真的去查（周期由 update/mode 决定，manual 永不自动查）。"""
        from . import update as U
        st = self._store.settings()
        mode = str(st.value('update/mode') or U.MODE_DEFAULT)
        try:
            last = int(st.value('update/last') or 0)
        except (TypeError, ValueError):
            last = 0
        if U.due(mode, last):
            self._updater.check(silent=True)

    def check_updates(self, silent=False, parent=None):
        """手动 / 自动检查更新。silent=True 时只在发现新版时提示。"""
        return self._updater.check(silent=silent,
                                   parent=parent or self)

    def open_settings(self):
        dlg = SettingsDialog(self._store, self)
        dlg.settingChanged.connect(self._on_setting)
        # 设置页里的「立即检查」交给同一条流程处理；parent 传对话框本身，
        # 否则模态对话框会挡住随之弹出的更新提示窗。
        dlg.checkRequested.connect(lambda: self.check_updates(False, dlg))
        dlg.exec_()
        self._apply_theme()

    def _on_setting(self, key, val):
        if key == 'app/autostart':
            try:
                self._ctx.apply_autostart()
            except Exception:
                pass
        elif key == 'ui/theme':
            self._apply_theme()
        elif key == 'color/reset':
            self._apply_theme()
        elif key.startswith('color/'):
            self._apply_theme()
        elif key == 'cal/showweek':
            self._cal.set_options(week=bool(val))
        elif key == 'cal/showtips':
            self._cal.set_options(tips=bool(val))
        elif key == 'cal/weekstart':
            self._cal.set_options(weekstart=str(val))
        elif key == 'cal/qscale':
            self._cal.set_options(qscale=int(val))
        elif key == 'cal/firstday':
            self._cal.set_options(firstday=int(val))
        elif key == 'cal/scale':
            self._cal.set_scale(float(val) / 10.0)
        elif key.startswith('cal/'):
            st = self._store.settings()
            self._cal.set_options(
                weekend=str(st.value('cal/showweekend', '1')) == '1',
                lunnar=str(st.value('cal/showlunnar', '1')) == '1',
                jieri=str(st.value('cal/showjieri', '1')) == '1',
                line=str(st.value('cal/showline', '1')) == '1',
                ban=str(st.value('cal/showban', '1')) == '1')

    def _about(self):
        dlg = AboutDialog(self)
        dlg.exec_()
