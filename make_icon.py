# -*- coding: utf-8 -*-
"""生成扁平日历图标（基于 Bootstrap Icons, MIT）。"""
import os
import subprocess

SRC = os.path.dirname(os.path.abspath(__file__))
DST = os.path.join(SRC, 'brl', 'resources', 'icons')


def build(name, bg1='#37B6FF', bg2='#1F7BFF', glyph='#FFFFFF'):
    svg = open(os.path.join(SRC, 'icon_src', name + '.svg')).read()
    svg = svg.replace('currentColor', glyph)
    # 取 <svg ...> 到 </svg> 之间的内容（跳过文件头注释）
    i = svg.index('<svg')
    j = svg.index('>', i)
    k = svg.index('</svg>')
    inner = svg[j + 1:k]
    wrapped = ('<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" '
               'viewBox="0 0 256 256">'
               '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">'
               '<stop offset="0" stop-color="%s"/><stop offset="1" stop-color="%s"/>'
               '</linearGradient></defs>'
               '<rect width="256" height="256" rx="56" fill="url(#g)"/>'
               '<g transform="translate(48,48) scale(10)" fill="%s">%s</g></svg>'
               % (bg1, bg2, glyph, inner))
    tmp = os.path.join(SRC, 'icon_src', 'c_%s.svg' % name)
    open(tmp, 'w').write(wrapped)
    out = os.path.join(SRC, 'icon_src', 'c_%s.png' % name)
    subprocess.check_call(['rsvg-convert', '-w', '256', '-h', '256', tmp, '-o', out])
    return out


if __name__ == '__main__':
    src = build('calendar-event-fill')
    from PIL import Image
    im = Image.open(src).convert('RGBA')
    os.makedirs(DST, exist_ok=True)
    im.save(os.path.join(DST, 'calendar.png'))
    for s in (16, 24, 32, 48, 64, 128):
        im.resize((s, s), Image.LANCZOS).save(os.path.join(DST, 'calendar_%d.png' % s))
    print('app icon written:', os.path.join(DST, 'calendar.png'))
