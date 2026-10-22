#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包 aarch64 deb（UOS / 飞腾 D3000）。

布局采用 UOS 应用规范 /opt/apps/<appid>/，同时写入 /usr/share/applications
与 /usr/share/icons 以保证最大兼容。
"""
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(ROOT, 'brl')
APPID = 'com.desktop.calendar'
PKG = 'desktop-calendar'
VER = '1.4.0.2'
OUT = os.path.join(ROOT, 'dist')
APP_NAME = u'桌面悬浮日历'

DESKTOP = u'''[Desktop Entry]
Type=Application
Name=桌面悬浮日历
Name[zh_CN]=桌面悬浮日历
GenericName=桌面日历
Comment=桌面悬浮日历 / 农历 / 待办提醒（本地版，无任何账号功能）
Exec=desktop-calendar
Icon=%s
Categories=Utility;
Keywords=calendar;lunar;日历;农历;待办;
Terminal=false
StartupNotify=false
''' % APPID

LAUNCHER = '''#!/bin/sh
# 桌面日历 启动器
# 按候选顺序探测一个真正装有 PyQt5 的解释器，避免被 PATH 中的
# pyenv/conda/其他私有 python 抢占导致误判“未安装 PyQt5”。
APP_FILES=/opt/apps/%s/files

PY=""
for cand in /usr/bin/python3 /usr/bin/python3.7 /usr/bin/python3.8 \\
           /usr/bin/python3.9 /usr/bin/python3.10 /usr/bin/python3.11 \\
           /usr/local/bin/python3 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        if "$cand" -c "import PyQt5" >/dev/null 2>&1; then
            PY="$cand"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    msg="未找到装有 PyQt5 的 python3，请先安装：\\n  sudo apt install python3-pyqt5"
    if command -v zenity >/dev/null 2>&1; then
        zenity --error --text="$msg" 2>/dev/null || true
    else
        echo "$msg" >&2
    fi
    exit 1
fi

export PYTHONPATH="$APP_FILES${PYTHONPATH:+:$PYTHONPATH}"
exec "$PY" -m brl "$@"
''' % APPID

INFO = u'''{
  "appid": "%s",
  "name": "%s",
  "version": "%s",
  "arch": ["arm64"],
  "info": "桌面悬浮日历：月/周视图、农历与节气、节日、法定节假日与调休、待办提醒、天气、主题与颜色定制。本地版，无任何账号/会员/登录功能，数据全部保存在本机。",
  "permissions": {
    "autostart": true,
    "notification": true
  }
}
''' % (APPID, APP_NAME, VER)

CONTROL = '''Package: %(pkg)s
Version: %(ver)s
Section: utils
Priority: optional
Architecture: arm64
Installed-Size: %(size)d
Maintainer: DesktopCalendar UOS Rebuild <local@localhost>
Depends: python3 (>= 3.5), python3-pyqt5
Suggests: dde-control-center
Description: %(name)s（UOS / 飞腾 aarch64 原生重制版）
 桌面悬浮日历：月/周视图、农历与节气、节日、
 法定节假日与调休、待办与提醒、天气、主题与颜色定制。
 本地版：无任何会员、登录与云端同步功能，
 所有数据保存在本机 ~/.local/share/desktop-calendar/。
''' % dict(pkg=PKG, ver=VER, size=0, name=APP_NAME)

POSTINST = '''#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -fq /usr/share/icons/hicolor 2>/dev/null || true
fi
if command -v dtk-store-update >/dev/null 2>&1; then
    dtk-store-update >/dev/null 2>&1 || true
fi

# ================= 安装后收尾：桌面图标 + 询问运行/自启 =================
# 注意：本段开了 set -e，所有「条件不成立」的分支必须写成 if 语句，
# 不能用 [ x ] && cmd 的写法（条件为假时返回非 0 会直接中断安装）。
APPID=com.desktop.calendar
DSRC=/usr/share/applications/$APPID.desktop
LOG=/tmp/desktop-calendar-install.log
: > "$LOG" 2>/dev/null || true

# --- 真实安装用户：sudo/apt 安装时 SUDO_USER 才是桌面用户 ---
U="$SUDO_USER"
if [ -z "$U" ]; then
    U="$(logname 2>/dev/null || true)"
fi
if [ -z "$U" ] || [ "$U" = "root" ]; then
    U="$(ls /home 2>/dev/null | head -n 1)"
fi
UHOME=""
if [ -n "$U" ]; then
    UHOME="$(getent passwd "$U" 2>/dev/null | cut -d: -f6)"
fi
if [ -z "$UHOME" ]; then
    UHOME="/home/$U"
fi
UXAUTH="$UHOME/.Xauthority"
# X 显示：UOS 走 abstract socket（/tmp/.X11-unix 是空的），有 socket 文件就照
# 它取，没有就按 :0 来；到底连不连得上，由软件自己 XOpenDisplay 试过才知道。
UDISP=""
if [ -d /tmp/.X11-unix ]; then
    for _s in /tmp/.X11-unix/X*; do
        if [ -S "$_s" ]; then
            UDISP=":${_s#/tmp/.X11-unix/X}"
            break
        fi
    done
fi
if [ -z "$UDISP" ]; then
    UDISP=":0"
fi

as_user() {
    if [ -n "$U" ] && command -v runuser >/dev/null 2>&1; then
        runuser -u "$U" -- env DISPLAY="$UDISP" XAUTHORITY="$UXAUTH" sh -c "$1"
    else
        sh -c "$1"
    fi
}

# ---------- 1) 桌面快捷方式 ----------
DESK=""
if [ -f "$UHOME/.config/user-dirs.dirs" ]; then
    DESK="$(sed -n 's/^XDG_DESKTOP_DIR=//p' "$UHOME/.config/user-dirs.dirs" 2>/dev/null | head -n 1 | tr -d '"' || true)"
    case "$DESK" in
        '$HOME'*) DESK="$UHOME${DESK#\\$HOME}" ;;
    esac
fi
if [ -z "$DESK" ] && [ -d "$UHOME/桌面" ]; then
    DESK="$UHOME/桌面"
fi
if [ -z "$DESK" ] && [ -d "$UHOME/Desktop" ]; then
    DESK="$UHOME/Desktop"
fi
if [ -n "$DESK" ] && [ -d "$DESK" ] && [ -f "$DSRC" ]; then
    cp -f "$DSRC" "$DESK/$APPID.desktop" 2>>"$LOG" || true
    chmod 755 "$DESK/$APPID.desktop" 2>>"$LOG" || true
    if [ -n "$U" ]; then
        chown "$U" "$DESK/$APPID.desktop" 2>>"$LOG" || true
    fi
    echo "desktop icon: $DESK/$APPID.desktop" >>"$LOG" 2>/dev/null || true
else
    echo "desktop icon: skipped (dir='$DESK')" >>"$LOG" 2>/dev/null || true
fi

# ---------- 2) 询问：开机自启 / 立即运行 ----------
# 三种手段依次尝试，哪个能用用哪个：
#   ① 软件自带对话框（首选）：UOS 上常常没装 zenity/kdialog/yad，依赖它们
#      等于"装完什么都不弹"；软件自己带 PyQt5，一个窗口问完两件事。
#   ② zenity（有 X 有 zenity 时才用）
#   ③ 终端提问（有 tty 时）
# 手段 ① 弹不出来时会以退出码 3 退出，这里据此往下走 ②/③。
AUTO=0
RUNNOW=0
ASKED=0
NEED_MARK=0
if [ -n "$2" ]; then
    echo "upgrade: skip prompts" >>"$LOG" 2>/dev/null || true
    ASKED=1
fi

if [ "$ASKED" = "0" ]; then
    # set -e 下，命令替换失败会直接中断安装，用 || rc=$? 接住
    rc=0
    OUT="$(as_user "timeout 75 /usr/bin/desktop-calendar --ask-install" 2>>"$LOG")" || rc=$?
    if [ "$rc" = "0" ]; then
        ASKED=1
        if echo "$OUT" | grep -q '^autostart=1$'; then
            AUTO=1
        fi
        if echo "$OUT" | grep -q '^run=1$'; then
            RUNNOW=1
        fi
    elif [ "$rc" = "2" ]; then
        echo "already asked: skip" >>"$LOG" 2>/dev/null || true
        ASKED=1
    else
        echo "own dialog failed (rc=$rc), fallback" >>"$LOG" 2>/dev/null || true
    fi
fi

if [ "$ASKED" = "0" ] && command -v zenity >/dev/null 2>&1; then
    if as_user 'zenity --question --title="桌面悬浮日历" --text="是否将桌面悬浮日历设为开机自动启动？" --timeout=60'; then
        AUTO=1
    fi
    if as_user 'zenity --question --title="桌面悬浮日历" --text="是否现在运行桌面悬浮日历？" --timeout=60'; then
        RUNNOW=1
    fi
    ASKED=1
    NEED_MARK=1
    echo "asked via zenity" >>"$LOG" 2>/dev/null || true
fi

if [ "$ASKED" = "0" ] && [ -t 0 ]; then
    printf '桌面悬浮日历：设为开机自动启动？[Y/n] '
    read -r a1 || a1=""
    case "$a1" in ''|[Yy]*) AUTO=1 ;; esac
    printf '桌面悬浮日历：现在启动？[Y/n] '
    read -r a2 || a2=""
    case "$a2" in ''|[Yy]*) RUNNOW=1 ;; esac
    ASKED=1
    NEED_MARK=1
    echo "asked via tty" >>"$LOG" 2>/dev/null || true
fi

if [ "$ASKED" = "0" ]; then
    # 装的时候实在问不了（无人值守安装等）：留给首次启动时补问
    echo "no way to ask: leave it to first run" >>"$LOG" 2>/dev/null || true
fi

if [ "$AUTO" = "1" ]; then
    as_user '/usr/bin/desktop-calendar --set-autostart on' >>"$LOG" 2>&1 || true
    echo "autostart: on" >>"$LOG" 2>/dev/null || true
fi
if [ "$RUNNOW" = "1" ]; then
    as_user 'setsid nohup /usr/bin/desktop-calendar >/dev/null 2>&1 &' || true
    echo "launched" >>"$LOG" 2>/dev/null || true
fi
# 走 zenity / 终端问的，自己报个"已问过"，免得首次启动时又被问一遍
if [ "$NEED_MARK" = "1" ]; then
    as_user '/usr/bin/desktop-calendar --mark-asked' >>"$LOG" 2>&1 || true
fi
#DEBHELPER#
exit 0
'''

PRERM = '''#!/bin/sh
set -e
#DEBHELPER#
exit 0
'''


def build():
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    stage = os.path.join(OUT, 'stage')
    files = os.path.join(stage, 'opt/apps/%s/files' % APPID)
    entries = os.path.join(stage, 'opt/apps/%s/entries' % APPID)
    os.makedirs(files)
    os.makedirs(os.path.join(entries, 'applications'))
    os.makedirs(os.path.join(entries, 'icons/hicolor/scalable/apps'))
    os.makedirs(os.path.join(stage, 'usr/share/applications'))
    for sz in ('16x16', '24x24', '32x32', '48x48', '128x128', '256x256'):
        os.makedirs(os.path.join(stage, 'usr/share/icons/hicolor/%s/apps' % sz))
    os.makedirs(os.path.join(stage, 'usr/bin'))

    # 1. 应用本体
    shutil.copytree(SRC, os.path.join(files, 'brl'),
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))

    # 2. 图标（新扁平化图标，多尺寸入 hicolor）
    icdir = os.path.join(SRC, 'resources/icons')
    ic = os.path.join(icdir, 'calendar.png')
    shutil.copy2(ic, os.path.join(entries, 'icons/hicolor/scalable/apps/%s.png' % APPID))
    shutil.copy2(ic, os.path.join(stage, 'usr/share/icons/hicolor/256x256/apps/%s.png' % APPID))
    for sz, name in ((16, '16x16'), (24, '24x24'), (32, '32x32'),
                     (48, '48x48'), (128, '128x128')):
        shutil.copy2(os.path.join(icdir, 'calendar_%d.png' % sz),
                     os.path.join(stage, 'usr/share/icons/hicolor/%s/apps/%s.png'
                                  % (name, APPID)))

    # 3. desktop
    dpath = os.path.join(entries, 'applications/%s.desktop' % APPID)
    with open(dpath, 'w', encoding='utf-8') as f:
        f.write(DESKTOP)
    shutil.copy2(dpath, os.path.join(stage, 'usr/share/applications/%s.desktop' % APPID))

    # 4. 启动器
    lp = os.path.join(stage, 'usr/bin', PKG)
    with open(lp, 'w') as f:
        f.write(LAUNCHER)
    os.chmod(lp, 0o755)

    # 5. UOS info
    with open(os.path.join(stage, 'opt/apps/%s/info' % APPID), 'w', encoding='utf-8') as f:
        f.write(INFO)

    # 6. DEBIAN
    deb = os.path.join(stage, 'DEBIAN')
    os.makedirs(deb)
    size = subprocess.check_output(['du', '-sk', files]).split()[0].decode()
    with open(os.path.join(deb, 'control'), 'w') as f:
        f.write(CONTROL.replace('Installed-Size: 0', 'Installed-Size: %s' % size))
    for name, body in (('postinst', POSTINST), ('prerm', PRERM)):
        p = os.path.join(deb, name)
        with open(p, 'w') as f:
            f.write(body)
        os.chmod(p, 0o755)

    # 7. dpkg-deb
    debout = os.path.join(OUT, '%s_%s_arm64.deb' % (PKG, VER))
    subprocess.check_call(['fakeroot', 'dpkg-deb', '--build', stage, debout])
    print('built:', debout, os.path.getsize(debout), 'bytes')
    return debout


if __name__ == '__main__':
    build()
