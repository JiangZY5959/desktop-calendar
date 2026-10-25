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
VER = '1.4.3.0'
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
 法定节假日与调休、待办与提醒、主题与颜色定制。
 本地版：无任何会员、登录与云端同步功能，
 所有数据保存在本机 ~/.local/share/desktop-calendar/。
 升级时保留待办与设置，并自动换成新版本。
''' % dict(pkg=PKG, ver=VER, size=0, name=APP_NAME)

PREINST = '''#!/bin/sh
set -e
LOG=/tmp/desktop-calendar-install.log
# 升级前先把用户的待办库与设置另存一份。
# 覆盖安装本身不会动 ~/.config 与 ~/.local/share，可一旦装到一半被打断，
# 或者包管理器走了"先删再装"的路子，这份备份就是退路。
if [ "$1" = "upgrade" ]; then
    /usr/bin/desktop-calendar-upgrade prepare "" "" "" "$LOG" 2>>"$LOG" || true
fi
#DEBHELPER#
exit 0
'''

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
    # 升级同样要记"已经问过"：老版本装的时候还没这个标记，
    # 补上之后首次启动就不会再拿开机自启来打扰用户。
    NEED_MARK=1
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

# ---------- 3) 升级收尾：关掉旧版本，保住数据，再把新版本打开 ----------
# 只有升级（$2 = 旧版本号）才走这里。顺序不能反：
#   旧版本还开着 → 请它保存退出（等它真走了为止）→ 数据缺失才补
#   → 才允许新版本接手。
# 少了这一步，新旧两个进程会同时读写同一份配置和待办库，
# 互相覆盖，表现出来就是"升级完待办和设置都没了"。
if [ -n "$2" ]; then
    /usr/bin/desktop-calendar-upgrade finish "$U" "$UHOME" "$UDISP" "$LOG" 2>>"$LOG" || true
fi
#DEBHELPER#
exit 0
'''

# 升级前后的收尾工具。单独成一个脚本，方便脱离 deb 单独调试：
#   desktop-calendar-upgrade prepare <用户> <家目录> <显示> <日志>
#   desktop-calendar-upgrade finish  <用户> <家目录> <显示> <日志>
#   desktop-calendar-upgrade stop    <用户> <家目录> <显示> <日志>
UPGRADER = r'''#!/bin/sh
# 桌面悬浮日历 —— 升级前后的收尾。
#
# 刻意不开 set -e：这只是个"尽力而为"的辅助脚本，
# 任何一步出问题都不能把安装本身带崩。
ACT="$1"; U="$2"; UHOME="$3"; UDISP="$4"; LOG="$5"

# 没指定用户就自己找：sudo 装时 SUDO_USER 才是桌面用户，pkexec 装时是 PKEXEC_UID
if [ -z "$U" ]; then
    if [ -n "$SUDO_USER" ]; then
        U="$SUDO_USER"
    elif [ -n "$PKEXEC_UID" ]; then
        U="$(getent passwd "$PKEXEC_UID" 2>/dev/null | cut -d: -f1)"
    else
        U="$(logname 2>/dev/null || true)"
    fi
    if [ -z "$U" ] || [ "$U" = "root" ]; then
        U="$(ls /home 2>/dev/null | head -n 1)"
    fi
fi
[ -z "$UHOME" ] && UHOME="/home/$U"
[ -z "$UDISP" ] && UDISP=":0"
[ -z "$LOG" ] && LOG="/dev/null"
CFG="$UHOME/.config/desktop-calendar"
DAT="$UHOME/.local/share/desktop-calendar"
INI="calendar.ini"
DB="calendar.db"
# 真正要拉起来的程序（测试时可以换成别的，方便脱离真机验证）
LAUNCH="${DC_LAUNCHER:-/usr/bin/desktop-calendar}"

say() {
    echo "[$(date +%H:%M:%S)] $1" >>"$LOG" 2>/dev/null || true
}

as_user() {
    # 三个条件缺一不可：知道是谁、真的是 root、runuser 存在、用户真的存在。
    # 少了最后一条，runuser 会直接报错退出，命令根本没跑，
    # 表现就是"装完了却没人把新版本打开"。
    if [ -n "$U" ] && [ "$(id -u)" = "0" ] \
            && command -v runuser >/dev/null 2>&1 \
            && getent passwd "$U" >/dev/null 2>&1; then
        runuser -u "$U" -- env HOME="$UHOME" DISPLAY="$UDISP" \
            XAUTHORITY="$UHOME/.Xauthority" sh -c "$1"
    else
        env HOME="$UHOME" DISPLAY="$UDISP" XAUTHORITY="$UHOME/.Xauthority" sh -c "$1"
    fi
}

# 备份根目录：root 时用 /var/backups，否则回落到家目录。
# 刻意不放在 ~/.local/share/desktop-calendar 里面——数据目录万一被清空，
# 备份得留在外面才救得回来。
backup_root() {
    # DC_BACKUP_ROOT 供测试隔离用（正常安装不设，行为不变）；
    # 光看是不是 root 不够：有些环境（沙箱、MAC 限制）连 root 都写不了
    # /var/backups，那就老老实实回落到家目录。
    if [ -n "$DC_BACKUP_ROOT" ] && [ -d "$DC_BACKUP_ROOT" ] && [ -w "$DC_BACKUP_ROOT" ]; then
        echo "$DC_BACKUP_ROOT"
    elif [ -d /var/backups ] && [ -w /var/backups ]; then
        echo "/var/backups/desktop-calendar"
    else
        echo "$UHOME/.desktop-calendar-backup"
    fi
}

# /proc/<pid> 还在，不等于进程还活着：父进程没来收尸的话，
# 僵尸会一直赖在那儿，害得我们以为旧版本死赖着不走。
p_alive() {
    if [ ! -d "/proc/$1" ]; then return 1; fi
    st=$(cat "/proc/$1/stat" 2>/dev/null)
    if [ -z "$st" ]; then return 0; fi
    s=${st##*') '}
    if [ -z "$s" ]; then return 0; fi
    case "$s" in
        Z*) return 1 ;;
    esac
    return 0
}

# 找出正在跑的日历进程（不含 dpkg / 安装器 / 本脚本自己）
dc_pids() {
    out=""
    for d in /proc/[0-9]*; do
        p="${d#/proc/}"
        if [ "$p" = "$$" ]; then continue; fi
        if [ "$p" = "1" ]; then continue; fi
        if [ ! -d "$d" ]; then continue; fi
        if ! p_alive "$p"; then continue; fi
        # 进程名必须是解释器本身。只拿命令行文本做判断会把
        # "在终端里敲过 dpkg -i desktop-calendar_xxx.deb 的 shell"
        # 也当成日历本体，杀掉它等于把正在进行的安装打断。
        comm=$(cat "$d/comm" 2>/dev/null)
        case "$comm" in
            python*|brl)
                cmd=$(tr '\000' ' ' <"$d/cmdline" 2>/dev/null)
                case "$cmd" in
                    *"-m brl"*) out="$out $p" ;;
                esac
                ;;
            desktop-calendar*) out="$out $p" ;;
        esac
    done
    echo "$out"
}

do_prepare() {
    BK=$(backup_root)
    D="$BK/upgrade-$(date +%Y%m%d-%H%M%S)"
    if ! mkdir -p "$D" 2>>"$LOG"; then
        say "backup: cannot create $D"
        return 0
    fi
    n=0
    for pair in "$INI:$CFG" "$DB:$DAT"; do
        f="${pair%%:*}"; d="${pair#*:}"
        if [ -s "$d/$f" ]; then
            if cp -f "$d/$f" "$D/$f" 2>>"$LOG"; then n=$((n + 1)); fi
        fi
    done
    if [ "$n" = "0" ]; then
        rmdir "$D" 2>/dev/null || true
        say "backup: nothing to save"
        return 0
    fi
    if [ -n "$U" ] && [ "$(id -u)" = "0" ] && getent passwd "$U" >/dev/null 2>&1; then
        chown -R "$U" "$D" 2>>"$LOG" || true
    fi
    i=0
    for o in $(ls -1r "$BK" 2>/dev/null); do
        i=$((i + 1))
        if [ "$i" -gt 5 ]; then rm -rf "$BK/$o" 2>/dev/null || true; fi
    done
    say "backup: $D ($n file)"
}

# 目标文件缺失或为空时才补，已经有内容的绝不覆盖
do_restore() {
    for pair in "$INI:$CFG" "$DB:$DAT"; do
        f="${pair%%:*}"; d="${pair#*:}"
        if [ -s "$d/$f" ]; then continue; fi
        for BK in "$DC_BACKUP_ROOT" /var/backups/desktop-calendar \
                  "$UHOME/.desktop-calendar-backup"; do
            if [ ! -d "$BK" ]; then continue; fi
            for sub in $(ls -1r "$BK" 2>/dev/null); do
                src="$BK/$sub/$f"
                if [ ! -s "$src" ]; then continue; fi
                mkdir -p "$d" 2>>"$LOG" || break
                cp -f "$src" "$d/$f" 2>>"$LOG" || break
                if [ -n "$U" ] && [ "$(id -u)" = "0" ] \
                        && getent passwd "$U" >/dev/null 2>&1; then
                    chown "$U" "$d/$f" 2>>"$LOG" || true
                fi
                say "restored: $f <- $src"
                break 2
            done
        done
    done
}

do_stop() {
    PIDS=$(dc_pids)
    if [ -z "$PIDS" ]; then
        say "stop: no running instance"
        return 0
    fi
    for p in $PIDS; do kill -TERM "$p" 2>/dev/null || true; done
    sleep 1
    for p in $PIDS; do
        if p_alive "$p"; then kill -KILL "$p" 2>/dev/null || true; fi
    done
    say "stop: $PIDS"
}

do_finish() {
    PIDS=$(dc_pids)
    if [ -z "$PIDS" ]; then
        say "finish: no old instance, keep it closed"
        do_restore
        return 0
    fi
    say "finish: old instance(s)$PIDS, asking to quit"
    # 有的系统的 sleep 不认小数，先探一下，免得空转。
    # 只等 2.4 秒：新版本收到 SIGTERM 会马上保存退出；
    # 老版本没有这个处理器，等再久也没用，索性早点强杀。
    if sleep 0.1 2>/dev/null; then TICK=0.2; N=12; else TICK=1; N=3; fi
    for p in $PIDS; do kill -TERM "$p" 2>/dev/null || true; done
    i=0
    while [ "$i" -lt "$N" ]; do
        left=""
        for p in $PIDS; do
            if p_alive "$p"; then left="$left $p"; fi
        done
        # 都走了就把列表清空，否则下面会误以为还有赖着不走的
        if [ -z "$left" ]; then PIDS=""; break; fi
        PIDS="$left"
        i=$((i + 1))
        sleep "$TICK"
    done
    if [ -n "$PIDS" ]; then
        for p in $PIDS; do kill -KILL "$p" 2>/dev/null || true; done
        sleep 0.3
        say "finish: force killed $PIDS"
    else
        say "finish: old instance(s) saved and quit"
    fi
    # 数据必须在旧进程彻底走掉之后再补，否则它一保存又把旧的盖回来
    do_restore
    if [ -z "$U" ]; then
        say "finish: no target user, skip relaunch"
        return 0
    fi
    as_user "setsid nohup $LAUNCH >/dev/null 2>&1 &"
    say "finish: relaunched as $U"
}

case "$ACT" in
    prepare) do_prepare ;;
    finish)  do_finish ;;
    stop)    do_stop ;;
    restore) do_restore ;;
    pids)    dc_pids ;;
    *)
        echo "usage: $0 prepare|finish|stop|restore|pids [user home display log]" >&2
        exit 2
        ;;
esac
exit 0
'''

PRERM = '''#!/bin/sh
set -e
# 卸载时把还开着的日历请出去：程序文件马上要被删，
# 留着它会在退出时把旧状态写回去。升级（upgrade）交给 postinst 处理——
# 那时它还得好好的，postinst 才知道"之前在跑"，装完要重新打开。
if [ "$1" != "upgrade" ]; then
    /usr/bin/desktop-calendar-upgrade stop "" "" "" /tmp/desktop-calendar-install.log 2>/dev/null || true
fi
#DEBHELPER#
exit 0
'''

POSTRM = '''#!/bin/sh
set -e
# 卸载、甚至彻底清除，都保留用户的待办与设置。
# 它们在本机 ~/.local/share/desktop-calendar 与 ~/.config/desktop-calendar，
# 与包本身无关，重装/升级回来还能接着用。
if [ "$1" = "purge" ]; then
    rm -rf /var/backups/desktop-calendar 2>/dev/null || true
fi
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

    # 4. 启动器 + 升级收尾工具
    lp = os.path.join(stage, 'usr/bin', PKG)
    with open(lp, 'w') as f:
        f.write(LAUNCHER)
    os.chmod(lp, 0o755)

    up = os.path.join(stage, 'usr/bin', PKG + '-upgrade')
    with open(up, 'w') as f:
        f.write(UPGRADER)
    os.chmod(up, 0o755)

    # 5. UOS info
    with open(os.path.join(stage, 'opt/apps/%s/info' % APPID), 'w', encoding='utf-8') as f:
        f.write(INFO)

    # 6. DEBIAN
    deb = os.path.join(stage, 'DEBIAN')
    os.makedirs(deb)
    size = subprocess.check_output(['du', '-sk', files]).split()[0].decode()
    with open(os.path.join(deb, 'control'), 'w') as f:
        f.write(CONTROL.replace('Installed-Size: 0', 'Installed-Size: %s' % size))
    for name, body in (('preinst', PREINST), ('postinst', POSTINST),
                       ('prerm', PRERM), ('postrm', POSTRM)):
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
