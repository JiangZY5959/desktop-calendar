# -*- coding: utf-8 -*-
"""为主题生成预览图（mini 日历示意，PIL 绘制）。不依赖 PyQt5。"""
import io
import os
import re

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_themes():
    src = io.open(os.path.join(ROOT, 'brl', 'theme.py'), encoding='utf-8').read()
    m = re.search(r'THEMES = (\[.*?\n\])', src, re.S)
    ns = {}
    exec('def u(s): return s\nTHEMES = ' + m.group(1), ns)
    return ns['THEMES']


def argb(hexc):
    s = hexc.lstrip('#')
    a = int(s[0:2], 16)
    r, g, b = int(s[2:4], 16), int(s[4:6], 16), int(s[6:8], 16)
    return (r, g, b, a)


def over(base, top):
    """base/top: (r,g,b,a) -> composited rgb tuple"""
    if top[3] >= 255:
        return top[:3]
    a = top[3] / 255.0
    return tuple(int(round(top[i] * a + base[i] * (1 - a))) for i in range(3))


W, H = 278, 148


def rrect(d, box, radius, **kw):
    """兼容旧版 Pillow 的圆角矩形"""
    if hasattr(d, 'rounded_rectangle'):
        d.rounded_rectangle(box, radius, **kw)
        return
    x0, y0, x1, y1 = box
    fill = kw.get('fill')
    outline = kw.get('outline')
    d.rectangle([x0 + radius, y0, x1 - radius, y1], fill=fill)
    d.rectangle([x0, y0 + radius, x1, y1 - radius], fill=fill)
    for cx, cy, start in ((x0 + radius, y0 + radius, 180), (x1 - radius, y0 + radius, 270),
                          (x1 - radius, y1 - radius, 0), (x0 + radius, y1 - radius, 90)):
        d.pieslice([cx - radius, cy - radius, cx + radius, cy + radius], start,
                   start + 90, fill=fill)
    if outline:
        d.arc([x0, y0, x0 + 2 * radius, y0 + 2 * radius], 180, 270, fill=outline)
        d.arc([x1 - 2 * radius, y0, x1, y0 + 2 * radius], 270, 360, fill=outline)
        d.arc([x1 - 2 * radius, y1 - 2 * radius, x1, y1], 0, 90, fill=outline)
        d.arc([x0, y1 - 2 * radius, x0 + 2 * radius, y1], 90, 180, fill=outline)


def render(cfg, path):
    im = Image.new('RGBA', (W, H), (90, 100, 110, 255))   # 模拟桌面
    d = ImageDraw.Draw(im)
    # 窗口底色
    base = over((90, 100, 110, 255), argb(cfg['mainbgndclr']))
    rrect(d, [0, 0, W - 1, H - 1], 10, fill=base)
    # 表头
    d.rectangle([8, 8, W - 9, 24], fill=over(base, argb(cfg['weekgridbgndclr'])))
    # 表头文字条
    for i in range(7):
        x = 8 + i * (W - 16) / 7.0
        d.rectangle([x + 14, 13, x + 30, 20], fill=over(base, argb(cfg['weekclr'])))
    # 30 个格子
    rows, cols = 5, 7
    gw = (W - 16) / 7.0
    gh = (H - 40) / 5.0
    for r in range(rows):
        for c in range(cols):
            x0 = 8 + c * gw
            y0 = 28 + r * gh
            cellbg = cfg['weekgridbgndclr'] if c in (0, 6) else cfg['gridbgndclr']
            d.rectangle([x0, y0, x0 + gw - 1, y0 + gh - 1],
                        fill=over(base, argb(cellbg)))
            if cfg.get('gridline'):
                lc = over(base, argb(cfg['borderinclr']))
                d.line([x0, y0, x0 + gw - 1, y0], fill=lc)
                d.line([x0, y0, x0, y0 + gh - 1], fill=lc)
            if r == 1 and c == 2:   # 今日
                rrect(d, [x0 + 3, y0 + 3, x0 + gw - 4, y0 + gh - 4],
                      5, fill=over(base, argb(cfg['todayclr'])))
            # 日数字条
            tc = cfg['jiericlr'] if c in (0, 6) else cfg['txtclr']
            d.rectangle([x0 + 5, y0 + 5, x0 + 16, y0 + 13],
                        fill=over(base, argb(tc)))
            # 农历条
            d.rectangle([x0 + 5, y0 + 19, x0 + 22, y0 + 26],
                        fill=over(base, argb(tc)))
    # 外边框
    rrect(d, [0, 0, W - 1, H - 1], 10, outline=over(base, argb(cfg['borderoutclr'])))
    im.convert('RGB').save(path)


if __name__ == '__main__':
    outdir = os.path.join(ROOT, 'brl', 'resources', 'img', 'theme')
    os.makedirs(outdir, exist_ok=True)
    # 删除旧预览
    for f in os.listdir(outdir):
        os.remove(os.path.join(outdir, f))
    for i, cfg in enumerate(load_themes()):
        render(cfg, os.path.join(outdir, 'theme%d.png' % (i + 1)))
    print('previews:', i + 1, '->', outdir)
