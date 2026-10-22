# -*- coding: utf-8 -*-
"""测试隔离：把 XDG 配置/数据目录重定向到临时目录。

血的教训：selftest / verify 脚本以前直接用用户的 ~/.config 和
~/.local/share 跑，结果把用户辛苦调好的颜色透明度、窗口位置和尺寸
都覆盖掉了（例如 _reset_colors 会把所有 color/* 写成空串）。
现在所有测试脚本一律先 isolate()，import brl 之前调用。
"""
import os
import sys
import tempfile

ROOT = None


def isolate(name='brl'):
    global ROOT
    ROOT = tempfile.mkdtemp(prefix='%s-test-' % name)
    cfg = os.path.join(ROOT, 'config')
    dat = os.path.join(ROOT, 'data')
    os.environ['XDG_CONFIG_HOME'] = cfg
    os.environ['XDG_DATA_HOME'] = dat
    os.makedirs(cfg)
    os.makedirs(dat)
    return ROOT


def ini_path():
    """当前隔离目录下的 calendar.ini"""
    return os.path.join(os.environ['XDG_CONFIG_HOME'], 'desktop-calendar',
                        'calendar.ini')


def cleanup():
    if ROOT and os.path.isdir(ROOT):
        import shutil
        shutil.rmtree(ROOT, ignore_errors=True)
