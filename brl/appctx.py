# -*- coding: utf-8 -*-
"""应用级上下文：主窗口 / 托盘 的协调与设置联动。"""
import os
import sys

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon, QMenu

from . import theme as T
from . import store as S
from . import data as D
from .mainwin import MainWindow, APP_NAME

_ctx = None


def autostart_path():
    base = os.environ.get('XDG_CONFIG_HOME') or os.path.expanduser('~/.config')
    return os.path.join(base, 'autostart', 'desktop-calendar.desktop')


def autostart_exe():
    """优先使用绝对路径，便于桌面环境直接拉起"""
    for c in ('/usr/bin/desktop-calendar',
              '/opt/apps/com.desktop.calendar/files/bin/desktop-calendar'):
        if os.path.exists(c):
            return c
    return 'desktop-calendar'


APPID = 'com.desktop.calendar'


def desktop_dir():
    """用户桌面目录。优先读 XDG_DESKTOP_DIR，其次 ~/桌面、~/Desktop。"""
    home = os.path.expanduser('~')
    try:
        f = os.path.join(home, '.config', 'user-dirs.dirs')
        if os.path.exists(f):
            with open(f, 'r', encoding='utf-8', errors='ignore') as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith('XDG_DESKTOP_DIR='):
                        v = line.split('=', 1)[1].strip().strip('"')
                        v = os.path.expandvars(v)
                        if os.path.isdir(v):
                            return v
    except Exception:
        pass
    for name in (u'桌面', 'Desktop'):
        p = os.path.join(home, name)
        if os.path.isdir(p):
            return p
    return ''


def make_desktop_icon(src=None):
    """在用户桌面放置快捷方式；成功返回 True。

    src 仅用于测试注入，正常安装时留空（取系统 applications 目录）。
    """
    d = desktop_dir()
    src = src or '/usr/share/applications/%s.desktop' % APPID
    if not d or not os.path.exists(src):
        return False
    dst = os.path.join(d, '%s.desktop' % APPID)
    try:
        with open(src, 'r', encoding='utf-8') as f:
            txt = f.read()
        with open(dst, 'w', encoding='utf-8') as f:
            f.write(txt)
        os.chmod(dst, 0o755)
        return True
    except OSError:
        return False


def apply_autostart(store, want=None):
    """写入或移除开机自启项；返回是否处于自启动状态。"""
    if want is None:
        want = str(store.settings().value('general/autostart', '0')) == '1'
    path = autostart_path()
    try:
        if not want:
            if os.path.exists(path):
                os.remove(path)
            return False
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
        txt = (u'[Desktop Entry]\n'
               u'Type=Application\n'
               u'Version=1.0\n'
               u'Name=%s\n'
               u'Comment=桌面悬浮日历\n'
               u'Exec=%s\n'
               u'Icon=desktop-calendar\n'
               u'Terminal=false\n'
               u'Categories=Utility;Calendar;\n'
               u'StartupNotify=false\n'
               u'NoDisplay=false\n'
               u'X-GNOME-Autostart-enabled=true\n'
               u'X-Deepin-Vendor=user\n' % (APP_NAME, autostart_exe()))
        with open(path, 'w') as f:
            f.write(txt)
        os.chmod(path, 0o755)
        return True
    except OSError:
        return False


def normalize_ini(path):
    """整理 ini 中的重复段。

    QSettings 增量写入会让同一个段（如 [%General]）在文件里出现多次，
    导致「写入命中前面那份、读取取到后面那份」，表现为勾选开机自启后
    读回来的值仍是旧值。这里把重复段归并后重写一次文件。
    返回是否真的重写过。
    """
    try:
        if not os.path.exists(path):
            return False
        with open(path, 'r') as f:
            txt = f.read()
    except IOError:
        return False

    sections = []
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            sections.append(s[1:-1])
    dup = [s for s in set(sections) if sections.count(s) > 1]
    if not dup:
        return False

    # 按段归并，后出现的条目覆盖先出现的（与 QSettings 读取语义一致）
    order, body, cur = [], {}, None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            cur = s[1:-1]
            if cur not in body:
                order.append(cur)
                body[cur] = []
            continue
        if cur is None:
            continue
        if '=' in s:
            k = s.split('=', 1)[0]
            body[cur] = [r for r in body[cur] if r.split('=', 1)[0] != k]
            body[cur].append(s)

    out = []
    for sec in order:
        out.append('[%s]' % sec)
        out.extend(body[sec])
        out.append('')
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w') as f:
            f.write('\n'.join(out))
        os.replace(tmp, path)
        return True
    except (IOError, OSError):
        return False


def install_zh_translator(app):
    """加载 Qt 简体中文翻译（用于颜色选择等 Qt 自带对话框）"""
    try:
        from PyQt5.QtCore import QTranslator, QLibraryInfo
        tr = QTranslator(app)
        dirs = ['/usr/share/qt5/translations', '/usr/share/qt/translations']
        try:
            dirs.insert(0, QLibraryInfo.location(QLibraryInfo.TranslationsPath))
        except Exception:
            pass
        for d in dirs:
            if d and tr.load('qt_zh_CN', d):
                app.installTranslator(tr)
                return True
    except Exception:
        pass
    return False


class Context(object):
    def __init__(self, app):
        self.app = app
        self.store = S.STORE
        self.win = None
        self.tray = None
        self._quit = False

    # ------------------------------------------------ 启动
    def start(self):
        # 先规整配置文件（消除历史遗留的重复段），再读取设置
        normalize_ini(os.path.join(D.config_dir(), 'calendar.ini'))
        st = self.store.settings()
        self.win = MainWindow(self.store, self)
        self.win.restore_pos()
        self._make_tray()
        show = str(st.value('ui/show', '1')) == '1'
        if show:
            self.win.show()
        self.apply_autostart()

    def _make_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = T.app_icon()
        self.tray = QSystemTrayIcon(icon, self.app)
        self.tray.setToolTip(APP_NAME)
        m = QMenu()
        m.addAction(u'显示日历', self.show_main)
        m.addSeparator()
        m.addAction(u'选项设置', lambda: self.win.open_settings())
        m.addSeparator()
        m.addAction(u'退出', self.quit)
        self.tray.setContextMenu(m)
        # 单击托盘图标只负责把主界面唤出来，绝不再把它藏回去
        self.tray.activated.connect(
            lambda r: self.show_main() if r == QSystemTrayIcon.Trigger else None)
        self.tray.show()

    # ------------------------------------------------ 交互
    def show_main(self):
        """显示主界面（不切换隐藏状态，也没有任何过渡动画）。"""
        self.win.show()
        self.win.raise_()
        self.win.activateWindow()
        self.store.settings().setValue('ui/show', '1')
        self.store.settings().sync()

    def toggle_main(self):
        """兼容旧调用：显示优先，且不再带渐变动画。"""
        self.show_main()

    def hide_main(self):
        """隐藏主界面（直接隐藏，无动画）。"""
        self.win.hide()
        self.store.settings().setValue('ui/show', '0')
        self.store.settings().sync()

    def open_settings(self):
        self.win.open_settings()

    def quit(self):
        self._quit = True
        try:
            if self.tray:
                self.tray.hide()
            self.win.close()
        except Exception:
            pass
        self.app.quit()

    # ------------------------------------------------ 开机自启
    def apply_autostart(self):
        """按当前设置立即写入/移除自启动文件（勾选后马上生效）"""
        return apply_autostart(self.store)


def _install_excepthook():
    """全局兜底：未捕获异常只记日志，不让 PyQt5 调 qFatal 杀掉进程。

    PyQt5 5.5+ 中槽内未处理的 Python 异常默认触发 abort()——
    天气 NameError 崩溃就是这样把整个日历带崩的。替换
    sys.excepthook 后 PyQt5 会改为调用它，进程得以存活。
    """
    import traceback

    def hook(t, v, tb):
        try:
            import io
            buf = io.StringIO()
            traceback.print_exception(t, v, tb, file=buf)
            msg = buf.getvalue()
            print(msg, file=sys.stderr)
            try:
                from . import data as _D
                logp = os.path.join(_D.data_dir(), 'error.log')
                with open(logp, 'a') as f:
                    import datetime
                    f.write('=== %s ===\n%s\n' % (datetime.datetime.now(), msg))
            except Exception:
                pass
        except Exception:
            pass

    sys.excepthook = hook


def main():
    global _ctx
    _install_excepthook()
    app = QApplication(sys.argv)
    install_zh_translator(app)
    app.setApplicationName('desktop-calendar')
    app.setOrganizationName('desktop-calendar')
    app.setWindowIcon(T.app_icon())
    app.setQuitOnLastWindowClosed(False)
    _ctx = Context(app)
    _ctx.start()
    return app.exec_(), _ctx
