# -*- coding: utf-8 -*-
u"""X11 属性微调（ctypes 直连 libX11，无第三方依赖）。

用途
----
1. 切换「贴到桌面(_NET_WM_STATE_BELOW)」时不重建窗口：
   Qt 的 setWindowFlags() 会销毁并重建原生窗口，表现为点锁定时界面闪一下；
   直接改 X11 的 _NET_WM_STATE 属性即可平滑切换。
2. 让窗口不出现在任务栏/分页器：
   _NET_WM_STATE_SKIP_TASKBAR + _NET_WM_STATE_SKIP_PAGER。

拿不到 X11（非 X 环境）时所有函数静默返回 False，调用方回退到 Qt 原生方案。

读窗口属性时会先确认窗口句柄有效：Xlib 的默认错误处理器遇到 BadWindow 会
直接打印错误并 **exit(1)**，进程就这么没了；这里装一个自己的处理器把它吞掉。
"""
import ctypes

_XA_ATOM = 4          # XA_ATOM
_XA_WINDOW = 33       # XA_WINDOW
_PROP_MODE_REPLACE = 0
_CLIENT_MESSAGE = 33  # XClientMessageEvent 的事件类型号
_SUBSTRUCT_REDIRECT = 0x00100000 | 0x00080000   # StructureNotify|SubstructureRedirect
_NET_WM_STATE_ADD = 1
_NET_WM_STATE_REMOVE = 0

_STATE = '_NET_WM_STATE'
_NAMES = {
    'BELOW': '_NET_WM_STATE_BELOW',
    'ABOVE': '_NET_WM_STATE_ABOVE',
    'SKIP_TASKBAR': '_NET_WM_STATE_SKIP_TASKBAR',
    'SKIP_PAGER': '_NET_WM_STATE_SKIP_PAGER',
}


class _ClientMsgData(ctypes.Union):
    _fields_ = [('b', ctypes.c_char * 20),
                ('s', ctypes.c_short * 10),
                ('l', ctypes.c_long * 5)]


class _ClientMsg(ctypes.Structure):
    """XClientMessageEvent（64 位下 96 字节）。"""
    _fields_ = [('type', ctypes.c_int),
                ('serial', ctypes.c_ulong),
                ('send_event', ctypes.c_int),
                ('display', ctypes.c_void_p),
                ('window', ctypes.c_ulong),
                ('message_type', ctypes.c_ulong),
                ('format', ctypes.c_int),
                ('data', _ClientMsgData)]


class _Event(ctypes.Union):
    """XEvent：最大成员是 24 个 long，共 192 字节。"""
    _fields_ = [('xclient', _ClientMsg),
                ('pad', ctypes.c_long * 24)]


def _load():
    """载入 libX11；失败返回 None。"""
    try:
        lib = ctypes.CDLL('libX11.so.6')
    except Exception:
        return None
    try:
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        lib.XInternAtom.restype = ctypes.c_ulong
        lib.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                    ctypes.c_int]
        lib.XGetWindowProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_long, ctypes.c_long, ctypes.c_int, ctypes.c_ulong,
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_ulong), ctypes.POINTER(ctypes.c_ulong),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_ubyte))]
        lib.XGetWindowProperty.restype = ctypes.c_int
        lib.XChangeProperty.argtypes = [
            ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong,
            ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        lib.XFree.argtypes = [ctypes.c_void_p]
        lib.XFlush.argtypes = [ctypes.c_void_p]
        lib.XCloseDisplay.argtypes = [ctypes.c_void_p]
        lib.XDefaultRootWindow.restype = ctypes.c_ulong
        lib.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
        lib.XSendEvent.restype = ctypes.c_int
        lib.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                   ctypes.c_long, ctypes.c_void_p]
    except Exception:
        return None
    return lib


_LIB = _load()

# Xlib 的错误处理器是进程级的回调：不接管的话，BadWindow 这类异步错误会让
# Xlib 打印 "X Error of failed request" 并直接 exit(1)。我们只关心"改成功了
# 没有"，错误交给返回值判断，所以这里装一个返回 0 的空处理器。
_ERR_CB = None


def _quieten(lib):
    global _ERR_CB
    if lib is None or _ERR_CB is not None:
        return
    try:
        proto = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
        lib.XSetErrorHandler.restype = ctypes.c_void_p
        lib.XSetErrorHandler.argtypes = [ctypes.c_void_p]
        _ERR_CB = proto(lambda dpy, ev: 0)      # 必须留引用，否则被回收
        lib.XSetErrorHandler(_ERR_CB)
    except Exception:
        _ERR_CB = None


_quieten(_LIB)


def available():
    return _LIB is not None


class _Dpy(object):
    """XOpenDisplay 上下文，保证异常时也能关闭。"""

    def __init__(self):
        self.lib = _LIB
        self.dpy = None
        self._cache = {}

    def __enter__(self):
        if not self.lib:
            return None
        self.dpy = ctypes.c_void_p(self.lib.XOpenDisplay(None))
        if not self.dpy:
            return None
        return self

    def __exit__(self, *a):
        if self.lib and self.dpy:
            try:
                self.lib.XFlush(self.dpy)
                self.lib.XCloseDisplay(self.dpy)
            except Exception:
                pass
        self.dpy = None
        return False

    def atom(self, name):
        if name not in self._cache:
            self._cache[name] = ctypes.c_ulong(
                self.lib.XInternAtom(self.dpy, name.encode('ascii'), 0)).value
        return self._cache[name]

    def get_state(self, wid):
        """读取窗口 _NET_WM_STATE，返回 (窗口是否有效, atom 集合)。

        XGetWindowProperty 对无效窗口会同步返回 BadWindow，可据此判断句柄
        还活着没有——离屏 / 窗口已销毁时不要再去写属性。
        """
        if not self.dpy or not wid or int(wid) <= 0:
            return False, set()
        actual_type = ctypes.c_ulong(0)
        fmt = ctypes.c_int(0)
        nitems = ctypes.c_ulong(0)
        after = ctypes.c_ulong(0)
        prop = ctypes.POINTER(ctypes.c_ubyte)()
        try:
            ret = self.lib.XGetWindowProperty(
                self.dpy, ctypes.c_ulong(wid), self.atom(_STATE),
                0, 1024, 0, _XA_ATOM,
                ctypes.byref(actual_type), ctypes.byref(fmt),
                ctypes.byref(nitems), ctypes.byref(after),
                ctypes.byref(prop))
        except Exception:
            return False, set()
        out = set()
        try:
            if prop and nitems.value and fmt.value == 32:
                arr = ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))
                for i in range(int(nitems.value)):
                    out.add(int(arr[i]))
        except Exception:
            pass
        try:
            if prop:
                self.lib.XFree(prop)
        except Exception:
            pass
        return ret == 0, out

    def get_window_prop(self, wid, name):
        """读一个 32 位属性（返回第一个值，读不到返回 0）。"""
        if not self.dpy or not wid:
            return 0
        actual_type = ctypes.c_ulong(0)
        fmt = ctypes.c_int(0)
        nitems = ctypes.c_ulong(0)
        after = ctypes.c_ulong(0)
        prop = ctypes.POINTER(ctypes.c_ubyte)()
        try:
            ret = self.lib.XGetWindowProperty(
                self.dpy, ctypes.c_ulong(wid), self.atom(name),
                0, 1, 0, 0,      # AnyPropertyType
                ctypes.byref(actual_type), ctypes.byref(fmt),
                ctypes.byref(nitems), ctypes.byref(after),
                ctypes.byref(prop))
        except Exception:
            return 0
        val = 0
        try:
            if ret == 0 and prop and nitems.value and fmt.value == 32:
                val = int(ctypes.cast(prop, ctypes.POINTER(ctypes.c_ulong))[0])
        except Exception:
            val = 0
        try:
            if prop:
                self.lib.XFree(prop)
        except Exception:
            pass
        return val

    def has_wm(self):
        """根窗口上有没有 _NET_SUPPORTING_WM_CHECK（即有没有 EWMH 窗口管理器）。"""
        try:
            root = self.lib.XDefaultRootWindow(self.dpy)
            return bool(self.get_window_prop(root, '_NET_SUPPORTING_WM_CHECK'))
        except Exception:
            return False

    def send_state(self, wid, add=(), remove=()):
        """按 EWMH 规范给根窗口发 _NET_WM_STATE ClientMessage。

        为什么必须走这条路：直接 XChangeProperty 改 _NET_WM_STATE 时，窗口管理器
        并不知道"是应用改的"，它在映射完成后会按自己的状态表把整个属性**回写**
        一遍，直接写入的 BELOW 就被抹掉了（实测约 1/3 概率）。发 ClientMessage
        等于请 WM 自己改，它的内部状态表会跟着更新，之后不会再被回写掉。
        """
        if not self.dpy:
            return False
        try:
            root = self.lib.XDefaultRootWindow(self.dpy)
        except Exception:
            return False
        mt = self.atom(_STATE)
        ok = True
        pairs = [(_NET_WM_STATE_ADD, n) for n in add] + \
                [(_NET_WM_STATE_REMOVE, n) for n in remove]
        # 一条消息最多带两个 atom，多的分批
        for i in range(0, len(pairs), 2):
            batch = pairs[i:i + 2]
            ev = _Event()
            ev.xclient.type = _CLIENT_MESSAGE
            ev.xclient.serial = 0
            ev.xclient.send_event = 1
            ev.xclient.display = self.dpy
            ev.xclient.window = wid
            ev.xclient.message_type = mt
            ev.xclient.format = 32
            ev.xclient.data.l[0] = batch[0][0]
            ev.xclient.data.l[1] = self.atom(_NAMES[batch[0][1]])
            ev.xclient.data.l[2] = self.atom(_NAMES[batch[1][1]]) if len(batch) > 1 else 0
            ev.xclient.data.l[3] = 1        # source indication: 普通应用
            ev.xclient.data.l[4] = 0
            try:
                self.lib.XSendEvent(self.dpy, ctypes.c_ulong(root), 0,
                                    _SUBSTRUCT_REDIRECT, ctypes.byref(ev))
            except Exception:
                ok = False
        try:
            self.lib.XFlush(self.dpy)
        except Exception:
            ok = False
        return ok

    def set_atoms(self, wid, atoms):
        """整体替换 _NET_WM_STATE。"""
        if not self.dpy:
            return False
        n = len(atoms)
        buf = (ctypes.c_ulong * max(1, n))(*([int(a) for a in atoms] or [0]))
        cnt = n if n else 0
        self.lib.XChangeProperty(
            self.dpy, ctypes.c_ulong(wid), self.atom(_STATE),
            ctypes.c_ulong(_XA_ATOM), 32, _PROP_MODE_REPLACE, buf, cnt)
        self.lib.XFlush(self.dpy)
        return True


def state_names(wid):
    """回读窗口当前的 _NET_WM_STATE，返回命中的短名集合（如 {'BELOW'}）。"""
    if not _LIB or not wid:
        return set()
    try:
        with _Dpy() as d:
            if not d:
                return set()
            ok, have = d.get_state(wid)
            if not ok:
                return set()
            out = set()
            for short, full in _NAMES.items():
                if d.atom(full) in have:
                    out.add(short)
            return out
    except Exception:
        return set()


def set_state(wid, add=(), remove=()):
    """在 _NET_WM_STATE 上增删标准状态；成功返回 True。"""
    if not _LIB or not wid:
        return False
    try:
        with _Dpy() as d:
            if not d:
                return False
            ok, cur = d.get_state(wid)
            if not ok:
                return False        # 窗口不存在 / 不在 X 显示上
            # 有窗口管理器时先按规范请它改（否则它回写状态表会把 BELOW 抹掉），
            # 同时自己写一次属性，保证没有 WM 或 WM 反应慢时也立刻生效。
            if add or remove:
                d.send_state(wid, add, remove)
            for name in remove:
                cur.discard(d.atom(_NAMES[name]))
            for name in add:
                cur.add(d.atom(_NAMES[name]))
            return d.set_atoms(wid, sorted(cur))
    except Exception:
        return False


def assert_state(wid, want=()):
    """确保 want 里的状态都存在（只补不删）；已满足返回 True。

    窗口管理器的状态回写、以及映射初期的时序问题，都可能让刚写进去的状态
    丢掉；调用方可以在稍后用这个函数补一次，做成自愈。
    """
    if not _LIB or not wid:
        return False
    try:
        with _Dpy() as d:
            if not d:
                return False
            ok, cur = d.get_state(wid)
            if not ok:
                return False
            lack = [n for n in want if d.atom(_NAMES[n]) not in cur]
            if not lack:
                return True
            if d.has_wm():
                d.send_state(wid, lack, ())
            for n in lack:
                cur.add(d.atom(_NAMES[n]))
            return d.set_atoms(wid, sorted(cur))
    except Exception:
        return False


def set_below(wid, below):
    """True=垫在所有窗口之下（贴桌面），False=恢复正常层级。"""
    if below:
        return set_state(wid, add=('BELOW',), remove=('ABOVE',))
    return set_state(wid, remove=('BELOW', 'ABOVE'))


def skip_taskbar(wid, skip=True):
    """任务栏/分页器里隐藏该窗口。"""
    if skip:
        return set_state(wid, add=('SKIP_TASKBAR', 'SKIP_PAGER'))
    return set_state(wid, remove=('SKIP_TASKBAR', 'SKIP_PAGER'))
