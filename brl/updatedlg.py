# -*- coding: utf-8 -*-
"""检查更新的界面部分：提示窗、下载进度窗、检查中的等待窗，以及编排流程。

界面规则与主界面一致：
* 无边框圆角面板，底下一层不透明底色再叠主题背景（主题背景可能很透明），
  保证「深底浅字 / 浅底深字」始终看得清；
* 进度条自绘（UOS 风格引擎不渲染 QSS 的 chunk / sub-page）；
* 不用任何动画：出现即出现，消失即消失。
"""
import datetime
import os
import subprocess
import time

from PyQt5.QtCore import Qt, QThread, QObject, pyqtSignal, QRectF, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QIcon
from PyQt5.QtWidgets import (QDialog, QWidget, QLabel, QPushButton, QVBoxLayout,
                             QHBoxLayout, QTextBrowser, QApplication, QMessageBox)

from . import theme as T
from . import data as D
from . import update as U
from . import APP_NAME, __version__ as APP_VER


# ---------------------------------------------------------------- 公共外观
class _Panel(QDialog):
    """主题化无边框面板（与待办提醒弹窗同一套规则）。"""

    def __init__(self, theme, parent, w, h, title):
        QDialog.__init__(self, parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(w, h)
        self._theme = dict(theme or {})
        # 与「选项设置」同一套浅色卡片：这里刻意不跟随日历主题的深浅。
        # 之前为了在深色主题上也看得清，主体用的是深色底，结果在白色系
        # 桌面上显得又黑又突兀——三个窗口统一成浅底深字才是一个软件。
        self._light = False
        self._txt = '#202020'
        self._dim = '#5A6069'
        self._line = '#DCE0E6'
        self._hover = '#F5F8FF'

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        T.paint_round(p, r, 10, '#F2F6FC')
        p.setPen(QPen(QColor('#DCE0E6')))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(r, 10, 10)
        p.end()

    def _close_btn(self):
        b = QPushButton()
        b.setFixedSize(20, 20)
        b.setFlat(True)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        b.setIcon(QIcon(T.tint(T.pix(D.res('icons', 'tool_close.png')), self._dim)))
        b.setStyleSheet('QPushButton{background:transparent;border:none;}'
                        'QPushButton:hover{background:%s;border-radius:4px;}'
                        % self._hover)
        b.clicked.connect(self.reject)
        return b

    def _btn(self, text, primary=False, w=96, h=30):
        b = QPushButton(text)
        b.setFixedSize(w, h)
        b.setFocusPolicy(Qt.NoFocus)
        b.setCursor(Qt.PointingHandCursor)
        if primary:
            b.setStyleSheet(
                'QPushButton{background:#2F7BFF;color:#FFFFFF;border:none;'
                'border-radius:5px;font-size:13px;}'
                'QPushButton:hover{background:#4A8CFF;}')
        else:
            # 与设置页里那排按钮一个模子：白底、细边框、悬停淡蓝
            b.setStyleSheet(
                'QPushButton{background:#FFFFFF;color:%s;font-size:13px;'
                'border:1px solid %s;border-radius:5px;}'
                'QPushButton:hover{background:%s;border-color:#A9CDF7;}'
                % (self._txt, self._line, self._hover))
        return b

    def _label(self, text, size=13, bold=False, dim=False):
        lb = QLabel(text)
        lb.setStyleSheet('color:%s;font-size:%dpx;%s'
                         % (self._dim if dim else self._txt, size,
                            'font-weight:bold;' if bold else ''))
        return lb


class _Bar(QWidget):
    """自绘进度条（UOS 上 QSS 的 chunk 不渲染）。fraction<0 表示不确定进度。"""

    def __init__(self, dark_bg=True, parent=None):
        QWidget.__init__(self, parent)
        self._f = -1.0
        self._dark = dark_bg
        self.setFixedHeight(8)

    def set_fraction(self, f):
        self._f = max(0.0, min(1.0, float(f)))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40) if self._dark
                  else QColor(0, 0, 0, 28))
        p.drawRoundedRect(QRectF(0, 0, w, h), h / 2.0, h / 2.0)
        if self._f > 0:
            p.setBrush(QColor('#2F7BFF'))
            p.drawRoundedRect(QRectF(0, 0, max(h, w * self._f), h), h / 2.0, h / 2.0)
        p.end()


class BusyDialog(_Panel):
    """「正在检查更新…」/「正在安装更新…」的轻量等待窗。"""

    def __init__(self, theme, parent, text=u'正在检查更新…', cancellable=True):
        _Panel.__init__(self, theme, parent, 300, 116, APP_NAME)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(8)
        self._lb = self._label(text, 14, bold=True)
        self._lb.setWordWrap(True)
        self._sub = self._label(u'', 12, dim=True)
        self._sub.setWordWrap(True)
        lay.addWidget(self._lb)
        lay.addWidget(self._sub)
        lay.addStretch(1)
        if cancellable:
            row = QHBoxLayout()
            row.addStretch(1)
            b = self._btn(u'取消', w=76, h=26)
            b.clicked.connect(self.reject)
            row.addWidget(b)
            lay.addLayout(row)

    def set_sub(self, text):
        self._sub.setText(text)


class PromptDialog(_Panel):
    """发现新版本提示。choice ∈ {'update', 'later', 'skip'}"""

    def __init__(self, manifest, theme, parent=None):
        _Panel.__init__(self, theme, parent, 500, 400, u'检查更新')
        self.manifest = dict(manifest or {})
        self.choice = 'later'
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        ic = QLabel()
        ic.setFixedSize(20, 20)
        pm = T.pix(D.res('icons', 'calendar.png'))
        ic.setPixmap(pm.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        head.addWidget(ic, 0, Qt.AlignVCenter)
        head.addWidget(self._label(u'发现新版本', 15, bold=True), 0, Qt.AlignVCenter)
        head.addStretch(1)
        head.addWidget(self._close_btn(), 0, Qt.AlignVCenter)
        lay.addLayout(head)

        info = u'新版本 v%s　　当前 v%s' % (manifest.get('version', ''), APP_VER)
        lay.addWidget(self._label(info, 12, dim=True))

        self._notes = QTextBrowser()
        self._notes.setFrameShape(QTextBrowser.NoFrame)
        self._notes.setOpenExternalLinks(True)
        self._notes.setStyleSheet(
            'QTextBrowser{background:#FFFFFF;border:1px solid %s;'
            'border-radius:6px;color:%s;font-size:13px;padding:6px;}'
            'QScrollBar:vertical{background:transparent;width:8px;margin:0;}'
            'QScrollBar::handle:vertical{background:#C8D0DA;border-radius:4px;'
            'min-height:20px;}'
            'QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}'
            % (self._line, self._txt))
        body = manifest.get('notes') or u'（该版本没有附带更新说明）'
        self._notes.setPlainText(body)
        lay.addWidget(self._notes, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        b_skip = self._btn(u'跳过此版本', w=100)
        b_skip.clicked.connect(self._on_skip)
        b_later = self._btn(u'稍后再说', w=88)
        b_later.clicked.connect(self._on_later)
        b_go = self._btn(u'立即更新', primary=True, w=96)
        b_go.clicked.connect(self._on_update)
        row.addWidget(b_skip)
        row.addStretch(1)
        row.addWidget(b_later)
        row.addWidget(b_go)
        lay.addLayout(row)

    def _on_skip(self):
        self.choice = 'skip'
        self.accept()

    def _on_later(self):
        self.choice = 'later'
        self.accept()

    def _on_update(self):
        self.choice = 'update'
        self.accept()


class DownloadDialog(_Panel):
    """下载进度窗。cancel() 由外部触发，用户按取消时把 _cancelled 置位。"""

    def __init__(self, manifest, theme, parent=None):
        _Panel.__init__(self, theme, parent, 440, 200, u'下载更新')
        self._cancelled = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 14)
        lay.setSpacing(8)

        head = QHBoxLayout()
        head.addWidget(self._label(u'正在下载更新', 15, bold=True))
        head.addStretch(1)
        head.addWidget(self._close_btn())
        lay.addLayout(head)

        self._ver = self._label(u'v%s' % manifest.get('version', ''), 12, dim=True)
        lay.addWidget(self._ver)
        self._bar = _Bar(dark_bg=self._light)
        lay.addWidget(self._bar)
        self._detail = self._label(u'准备中…', 12, dim=True)
        lay.addWidget(self._detail)
        lay.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self._cancel = self._btn(u'取消', w=80, h=28)
        self._cancel.clicked.connect(self._on_cancel)
        row.addWidget(self._cancel)
        lay.addLayout(row)

    def _on_cancel(self):
        self._cancelled = True
        self._cancel.setEnabled(False)
        self._cancel.setText(u'正在取消…')

    def cancelled(self):
        return self._cancelled

    def set_progress(self, read, total):
        if total:
            self._bar.set_fraction(read / float(total))
            self._detail.setText(u'%.1f MB / %.1f MB（%d%%）'
                                 % (read / 1048576.0, total / 1048576.0,
                                    int(read * 100 / total)))
        else:
            self._bar.set_fraction(-1)
            self._detail.setText(u'已下载 %.1f MB' % (read / 1048576.0,))

    def set_status(self, text):
        self._detail.setText(text)


# ---------------------------------------------------------------- 线程
class _CheckThread(QThread):
    ok = pyqtSignal(object)
    fail = pyqtSignal(str)

    def run(self):
        try:
            self.ok.emit(U.fetch_manifest())
        except Exception as e:
            self.fail.emit(str(e))


class _DownloadThread(QThread):
    progress = pyqtSignal(int, int)
    ok = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self, url, dest, size=0, dlg=None, parent=None):
        QThread.__init__(self, parent)
        self._url = url
        self._dest = dest
        self._size = size
        self._dlg = dlg

    def run(self):
        try:
            U.download(self._url, self._dest, total_hint=self._size,
                       on_progress=lambda r, t: self.progress.emit(r, t),
                       cancelled=lambda: bool(self._dlg and self._dlg.cancelled()))
            self.ok.emit(self._dest)
        except U.Cancelled:
            self.fail.emit(u'已取消')
        except Exception as e:
            self.fail.emit(str(e))


class _InstallThread(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, argv, parent=None):
        QThread.__init__(self, parent)
        self._argv = list(argv)

    def run(self):
        try:
            p = subprocess.Popen(self._argv, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, env=U.install_env())
            out, _e = p.communicate()
            msg = (out or b'').decode('utf-8', 'replace').strip()
            self.done.emit(p.returncode == 0, msg[-600:])
        except Exception as e:
            self.done.emit(False, str(e))


# ---------------------------------------------------------------- 流程编排
class UpdateFlow(QObject):
    """把「检查 -> 提示 -> 下载 -> 安装」串起来。

    自动检查（silent=True）不弹任何"正在检查"窗口，出错也不打扰用户，
    只写日志；手动检查（silent=False）会给出明确的成功 / 失败反馈。
    """

    def __init__(self, store, host):
        QObject.__init__(self, host)
        self._store = store
        self._host = host
        self._parent = None
        self._check_th = None
        self._dl_th = None
        self._inst_th = None
        self._busy = None
        self._dlg = None

    # ---------------- 状态 / 日志
    def _st(self):
        return self._store.settings()

    def _log(self, msg):
        try:
            with open(os.path.join(D.data_dir(), 'update.log'), 'a') as f:
                f.write('%s  %s\n' % (datetime.datetime.now().strftime('%F %T'), msg))
        except Exception:
            pass

    def _theme(self):
        return getattr(self._host, '_theme', None)

    def busy(self):
        return self._check_th is not None or self._inst_th is not None

    # ---------------- 检查
    def check(self, silent=True, parent=None):
        if self._check_th is not None or self._dl_th is not None \
                or self._dlg is not None:
            return False
        self._parent = parent or self._host
        if not silent:
            self._busy = BusyDialog(self._theme(), self._parent)
            self._busy.show()
        th = _CheckThread(self)
        th.ok.connect(lambda m: self._on_checked(m, silent))
        th.fail.connect(lambda e: self._on_failed(e, silent))
        th.finished.connect(self._on_check_done)
        self._check_th = th
        th.start()
        return True

    def _close_busy(self):
        if self._busy is not None:
            try:
                self._busy.reject()
            except Exception:
                pass
            self._busy = None

    def _on_check_done(self):
        self._check_th = None

    def _on_failed(self, err, silent):
        self._close_busy()
        self._log(u'检查失败：%s' % err)
        if not silent:
            QMessageBox.warning(self._parent, APP_NAME,
                                u'检查更新失败：\n%s\n\n可以稍后再试，或直接到\n%s\n手动下载。'
                                % (err, U.PAGE))

    def _on_checked(self, m, silent):
        self._close_busy()
        st = self._st()
        try:
            st.setValue('update/last', int(time.time()))
            st.setValue('update/lastver', str(m.get('version') or ''))
            st.sync()
        except Exception:
            pass
        remote = str(m.get('version') or '')
        newer = U.is_newer(remote, APP_VER)
        self._log(u'检查完成：远端 v%s，本地 v%s，%s' %
                  (remote, APP_VER, u'有新版本' if newer else u'已是最新'))
        if not newer:
            if not silent:
                QMessageBox.information(
                    self._parent, APP_NAME,
                    u'当前已是最新版本 v%s。' % APP_VER)
            return
        skip = str(st.value('update/skip') or '')
        if skip and skip == remote:
            if not silent:
                # 手动检查时忽略"跳过此版本"，用户主动问就该给答复
                pass
            else:
                self._log(u'v%s 已被用户跳过，静默忽略' % remote)
                return
        self._prompt(m)

    # ---------------- 提示
    def _prompt(self, m):
        dlg = PromptDialog(m, self._theme(), self._parent)
        self._dlg = dlg
        try:
            dlg.exec_()
        finally:
            self._dlg = None
        if dlg.choice == 'skip':
            st = self._st()
            st.setValue('update/skip', str(m.get('version') or ''))
            st.sync()
            self._log(u'用户跳过 v%s' % m.get('version'))
            return
        if dlg.choice == 'update':
            self._download(m)

    # ---------------- 下载
    def _download(self, m):
        try:
            url = U.resolve_url(m)
        except Exception as e:
            QMessageBox.warning(self._parent, APP_NAME, u'%s' % e)
            return
        name = str(m.get('file') or (U.DEB_TMPL % m.get('version')))
        dest = os.path.join(U.updates_dir(), name)
        if os.path.exists(dest):
            ok, _why = U.verify_deb(dest, m.get('size') or 0, m.get('sha256') or '')
            if ok:
                # 上次已经下好并校验过，直接进安装，不重复走流量
                self._log(u'安装包已存在，跳过下载：%s' % dest)
                self._install(dest)
                return
            U._safe_remove(dest)
        dlg = DownloadDialog(m, self._theme(), self._parent)
        self._dlg = dlg
        th = _DownloadThread(url, dest, m.get('size') or 0, dlg, self)
        th.progress.connect(dlg.set_progress)
        th.ok.connect(lambda p: self._on_downloaded(p, m, dlg))
        th.fail.connect(lambda e: self._on_dl_failed(e, dlg))
        th.finished.connect(self._on_dl_thread_done)
        self._dl_th = th
        th.start()
        dlg.exec_()
        if dlg.cancelled():
            th.wait(3000)

    def _on_dl_thread_done(self):
        self._dl_th = None

    def _on_dl_failed(self, err, dlg):
        self._dlg = None
        try:
            dlg.reject()
        except Exception:
            pass
        if err and err != u'已取消':
            QMessageBox.warning(self._parent, APP_NAME, u'下载更新失败：\n%s' % err)

    def _on_downloaded(self, path, m, dlg):
        ok, why = U.verify_deb(path, m.get('size') or 0, m.get('sha256') or '')
        if not ok:
            self._dlg = None
            try:
                dlg.reject()
            except Exception:
                pass
            U._safe_remove(path)
            QMessageBox.warning(self._parent, APP_NAME,
                                u'安装包校验失败：%s\n请稍后重试。' % why)
            return
        dlg.set_status(u'下载完成，正在启动安装…')
        try:
            dlg.accept()
        except Exception:
            pass
        self._install(path)

    # ---------------- 安装
    def _backup(self):
        """动安装器之前，先把待办与设置另存一份兜底。"""
        try:
            from . import appdata as AD
            d, kinds = AD.make_backup()
            if d:
                self._log(u'升级前备份：%s（%s）' % (d, ','.join(kinds)))
            else:
                self._log(u'升级前备份：无数据文件，跳过')
        except Exception as e:
            self._log(u'升级前备份失败：%s' % e)

    def _install(self, path):
        self._backup()
        plan = U.installer_plan(path)
        if not plan:
            QMessageBox.information(
                self._parent, APP_NAME,
                u'安装包已下载到：\n%s\n\n没有找到可用的安装程序，请手动双击安装。' % path)
            return
        self._try_install(path, plan, 0)

    def _try_install(self, path, plan, idx):
        if idx >= len(plan):
            QMessageBox.warning(
                self._parent, APP_NAME,
                u'自动安装失败，请手动安装：\n%s' % path)
            return
        kind, argv, label = plan[idx]
        if kind == 'gui':
            try:
                subprocess.Popen(argv, env=U.install_env())
            except Exception as e:
                self._log(u'%s 启动失败：%s' % (label, e))
                self._try_install(path, plan, idx + 1)
                return
            self._log(u'已交给 %s 安装' % label)
            QMessageBox.information(
                self._parent, APP_NAME,
                u'已启动%s。\n请在打开的窗口里确认安装，装好后日历会自动换成新版本。'
                % label)
            return
        busy = BusyDialog(self._theme(), self._parent,
                          u'正在安装更新…', cancellable=False)
        busy.set_sub(u'%s 正在安装，请稍候' % label)
        busy.show()
        th = _InstallThread(argv, self)

        def _done(ok, msg):
            self._inst_th = None
            try:
                busy.reject()
            except Exception:
                pass
            if ok:
                self._log(u'%s 安装成功' % label)
                self._finish(path)
            else:
                self._log(u'%s 安装失败：%s' % (label, msg))
                self._try_install(path, plan, idx + 1)

        th.done.connect(_done)
        th.finished.connect(self._on_inst_thread_done)
        self._inst_th = th
        th.start()

    def _on_inst_thread_done(self):
        self._inst_th = None

    # ---------------- 收尾：关掉旧版本，打开新版本
    def _flush(self):
        """把还在内存里的设置落盘，别等被信号打断时才想起没存。"""
        try:
            self._st().sync()
        except Exception:
            pass

    def _finish(self, path):
        """安装完成。

        正常情况下安装脚本（postinst）会负责"关旧的、开新的"，这里只管
        保存好数据然后等着被请出去；万一装的是那种不跑我们脚本的安装器，
        2.5 秒后自己把新版本拉起来再退，绝不让新旧两个版本同时写数据。
        """
        U._safe_remove(path)
        self._flush()
        try:
            from . import appdata as AD
            got = AD.ensure_data()
            if got:
                self._log(u'已从备份恢复：%s' % ','.join(got))
        except Exception:
            pass
        self._log(u'安装完成，等待新版本启动')
        QTimer.singleShot(2500, self._relaunch_if_needed)

    def _relaunch_if_needed(self):
        ok, info = U.relaunch(delay=1.0)
        if not ok:
            self._log(u'重启失败：%s' % info)
            return
        self._log(u'自行拉起新版本：%s' % info)
        QTimer.singleShot(250, self._quit_self)

    def _quit_self(self):
        # 走 Context.quit() 才会保存窗口位置与设置，直接 app.quit() 会丢东西
        ctx = getattr(self._host, '_ctx', None)
        if ctx is not None and hasattr(ctx, 'quit'):
            try:
                ctx.quit()
                return
            except Exception:
                pass
        try:
            QApplication.instance().quit()
        except Exception:
            pass
