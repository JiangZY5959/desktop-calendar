# -*- coding: utf-8 -*-
"""应用级上下文：主窗口 / 托盘 的协调与设置联动。"""
import os
import sys

from PyQt5.QtWidgets import QApplication, QSystemTrayIcon

from . import theme as T
from . import store as S
from . import data as D
from . import appdata as AD
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


def migrate_ini_group(path):
    """把老版本写进 [%General] 的设置搬到 [app] 段。

    QSettings 写 'general/xxx' 时，ini 里落的却是 [%General]（Qt 的转义
    写法）；下次启动再按 'general/xxx' 去读又是空的——这正是「每次打开
    都弹一遍开机自启」的根因。键已改为 app/*，这里把老数据搬过去，
    免得用户之前勾过的开机自启丢掉。
    返回是否真的改动过文件。
    """
    OLD = ('%General', 'General')
    try:
        if not os.path.exists(path):
            return False
        with open(path, 'r') as f:
            txt = f.read()
    except IOError:
        return False
    if not any('[%s]' % g in txt for g in OLD):
        return False

    order, body, cur = [], {}, None
    for line in txt.splitlines():
        s = line.strip()
        if s.startswith('[') and s.endswith(']'):
            cur = s[1:-1]
            if cur not in body:
                order.append(cur)
                body[cur] = []
            continue
        if cur is None or '=' not in s:
            continue
        k = s.split('=', 1)[0]
        body[cur] = [r for r in body[cur] if r.split('=', 1)[0] != k]
        body[cur].append(s)

    moved = []
    for g in OLD:
        if g not in body:
            continue
        for row in body.pop(g):
            k = row.split('=', 1)[0]
            if k not in ('autostart', 'autostart_asked'):
                continue
            body.setdefault('app', [])
            if not any(r.split('=', 1)[0] == k for r in body['app']):
                body['app'].append(row)
                moved.append(k)
        order = [s for s in order if s != g]
    if 'app' not in order:
        order.insert(0, 'app')
    if not moved:
        return False

    out = []
    for sec in order:
        rows = body.get(sec)
        if not rows:
            continue
        out.append('[%s]' % sec)
        out.extend(rows)
        out.append('')
    try:
        with open(path, 'w') as f:
            f.write('\n'.join(out).rstrip('\n') + '\n')
    except IOError:
        return False
    return True


def apply_autostart(store, want=None):
    """写入或移除开机自启项；返回是否处于自启动状态。

    want 为 None（启动时同步）且配置里没记过这个选项时，保持现状不动：
    宁可漏建，也不能把用户自己建好的自启动项删掉。
    """
    if want is None:
        v = store.settings().value('app/autostart', None)
        if v is None:
            return os.path.exists(autostart_path())
        want = str(v) == '1'
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
        # 先规整配置文件（消除历史遗留的重复段、搬走老组），再读取设置
        _ini = os.path.join(D.config_dir(), 'calendar.ini')
        normalize_ini(_ini)
        migrate_ini_group(_ini)
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
        m = T.CardMenu()       # 与齿轮菜单、设置页同一套圆角浅色卡片
        m.addAction(u'显示日历', self.show_main)
        m.addSeparator()
        m.addAction(u'选项设置', lambda: self.win.open_settings())
        m.addAction(u'检查更新', lambda: self.win.check_updates(False))
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
        if self._quit:
            return
        self._quit = True
        # 顺序很关键：
        #   ① 先把缺失的数据补回来——QSettings 的 sync 以磁盘文件为准做
        #      合并，文件要是已经被外部清掉（升级、误删），这里不补的话，
        #      下面保存窗口位置的一次 sync 会把其余设置全部带走；
        #   ② 再关窗口（触发保存位置尺寸）；
        #   ③ 最后落盘设置、注销实例。升级时旧实例就是这样被"请"出去的，
        #     直接 SIGKILL 会把刚改过的设置丢在内存里。
        try:
            AD.ensure_data()
        except Exception:
            pass
        try:
            self.win.close()
        except Exception:
            pass
        try:
            st = self.store.settings()
            st.sync()
        except Exception:
            pass
        # 兜底：只要用户真的用过一次（不管安装时有没有问成），
        # 就记下"开机自启已经问过"，免得下次启动又弹一次。
        # 用户要的是只有首次安装问一次，升级、退出重开都不该再问。
        try:
            from . import askinstall as AI
            AI.mark_asked()
        except Exception:
            pass
        try:
            AD.clear_pid(only_self=True)
        except Exception:
            pass
        try:
            if self.tray:
                self.tray.hide()
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


def _install_signal_handlers(app, ctx):
    """让 SIGTERM/SIGINT 变成"保存后正常退出"，而不是被系统直接杀掉。

    升级时安装脚本就是发 SIGTERM 请旧版本让位的：旧版本若不保存就死，
    用户刚改的设置会跟着内存一起没了。
    """
    import signal
    from PyQt5.QtCore import QTimer

    def _on_signal(signum, frame):
        # singleShot 把真正的退出动作排进事件循环，避免在信号上下文里
        # 直接动 Qt 对象（那不是线程/信号安全的做法）。
        try:
            QTimer.singleShot(0, ctx.quit)
        except Exception:
            try:
                app.quit()
            except Exception:
                pass

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            signal.signal(sig, _on_signal)
        except (ValueError, OSError, AttributeError):
            pass

    # 心跳定时器：事件循环得周期性醒来，Python 才有机会执行上面那个处理器
    try:
        tick = QTimer(app)
        tick.setInterval(400)
        tick.timeout.connect(lambda: None)
        tick.start()
        return tick
    except Exception:
        return None


def main():
    global _ctx
    _install_excepthook()
    # 先请旧实例保存退出。少了这一步，升级后新旧两个进程会同时写同一份
    # 配置和待办库，互相覆盖——就是"升级完待办没了"的真正来源。
    AD.take_over(timeout=4.0)
    app = QApplication(sys.argv)
    install_zh_translator(app)
    app.setApplicationName('desktop-calendar')
    app.setOrganizationName('desktop-calendar')
    app.setWindowIcon(T.app_icon())
    app.setQuitOnLastWindowClosed(False)
    _ctx = Context(app)
    _ctx.start()
    _install_signal_handlers(app, _ctx)
    try:
        from . import __version__ as _ver
    except Exception:
        _ver = ''
    AD.write_pid(_ver)
    try:
        code = app.exec_()
    finally:
        try:
            AD.clear_pid(only_self=True)
        except Exception:
            pass
    return code, _ctx
