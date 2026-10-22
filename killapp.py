# -*- coding: utf-8 -*-
"""按进程真实 cmdline 精确终止日历进程（避免 pkill -f 误伤执行它的 shell）。

用法: python3 killapp.py [target]
target 为模块名，默认 brl。只杀 argv 形如 "python* -m <target>" 的进程。
"""
import os
import sys
import time
import signal

TARGET = sys.argv[1] if len(sys.argv) > 1 else 'brl'


def cmdline(pid):
    try:
        with open('/proc/%s/cmdline' % pid, 'rb') as f:
            return f.read().decode('utf-8', 'ignore').split('\0')
    except IOError:
        return None


def matches(argv):
    if not argv or len(argv) < 3:
        return False
    prog = os.path.basename(argv[0] or '')
    if not prog.startswith('python'):
        return False
    # 形如: python3 -m brl
    return argv[1] == '-m' and argv[2] == TARGET


def main():
    me = os.getpid()
    killed = []
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        pid = int(name)
        if pid == me:
            continue
        argv = cmdline(pid)
        if argv and matches([a for a in argv if a]):
            try:
                os.kill(pid, signal.SIGTERM)
                killed.append(pid)
            except OSError:
                pass
    t0 = time.time()
    while time.time() - t0 < 3:
        alive = []
        for pid in killed:
            try:
                os.kill(pid, 0)
                alive.append(pid)
            except OSError:
                pass
        if not alive:
            break
        time.sleep(0.3)
    print('killed: %s' % (killed or 'none'))


if __name__ == '__main__':
    main()
