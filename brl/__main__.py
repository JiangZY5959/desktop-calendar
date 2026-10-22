# -*- coding: utf-8 -*-
"""程序入口。

支持少量安装器/维护用的命令行参数（见 _dispatch），其余情况正常启动界面。
"""
import sys

from . import appctx


def _dispatch(argv):
    """处理维护参数。返回 (handled, exit_code)。"""
    if not argv:
        return False, 0

    if argv[0] == '--set-autostart':
        # 用法: desktop-calendar --set-autostart on|off
        # 由安装器（postinst）调用：同步写配置项与自启动文件，
        # 保证两者一致，避免界面启动时又把文件删掉。
        val = argv[1].lower() if len(argv) > 1 else 'on'
        want = val in ('on', '1', 'true', 'yes', u'是')
        from . import store as S
        st = S.Store()
        st.settings().setValue('general/autostart', '1' if want else '0')
        st.settings().sync()
        state = appctx.apply_autostart(st)
        sys.stdout.write('autostart: %s\n' % ('on' if state else 'off'))
        return True, 0

    if argv[0] == '--make-desktop-icon':
        # 用法: desktop-calendar --make-desktop-icon
        # 在用户桌面创建快捷方式（XDG_DESKTOP_DIR / ~/桌面 / ~/Desktop）
        from . import appctx as A
        made = A.make_desktop_icon()
        sys.stdout.write('desktop icon: %s\n' % ('ok' if made else 'fail'))
        return True, 0

    if argv[0] == '--check-update':
        # 用法: desktop-calendar --check-update
        # 命令行查一次版本（不下载、不弹窗），便于排查网络问题
        from . import update as U
        from . import __version__ as cur
        try:
            m = U.fetch_manifest()
        except Exception as e:
            sys.stdout.write(u'check failed: %s\n' % (e,))
            return True, 1
        newer = U.is_newer(m.get('version'), cur)
        sys.stdout.write(u'current: %s\nremote : %s\nnewer  : %s\nfile   : %s\n'
                         % (cur, m.get('version'), 'yes' if newer else 'no',
                            m.get('file')))
        return True, 0

    return False, 0


if __name__ == '__main__':
    handled, code = _dispatch(sys.argv[1:])
    if handled:
        sys.exit(code)
    code, _ctx = appctx.main()
    sys.exit(code)
