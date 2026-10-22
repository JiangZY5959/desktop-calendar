# -*- coding: utf-8 -*-
"""生成主界面右上角工具按钮图标（Bootstrap Icons, MIT）。

统一风格：24px 白色实心线性图标、透明背景，替代原版精灵图按钮，
彻底避免精灵多帧被压扁/裁切的问题。
"""
import os
import subprocess

SRC = os.path.dirname(os.path.abspath(__file__))
ICON_SRC = os.path.join(SRC, 'icon_src')
DST = os.path.join(SRC, 'brl', 'resources', 'icons')

# 名称 -> (bootstrap 图标名, 说明, 颜色)
TOOLS = [
    ('tool_view', 'calendar2-date-fill', u'月视图/周视图', '#FFFFFF'),
    ('tool_lock', 'lock-fill', u'锁定窗口', '#FFFFFF'),
    ('tool_unlock', 'unlock-fill', u'解锁窗口', '#FFFFFF'),
    ('tool_gear', 'gear-fill', u'菜单/设置', '#FFFFFF'),
    ('nav_prev', 'chevron-left', u'上个月', '#FFFFFF'),
    ('nav_next', 'chevron-right', u'下个月', '#FFFFFF'),
    ('nav_today', 'calendar-check-fill', u'回到今天', '#FFFFFF'),
    ('nav_down', 'chevron-down', u'下拉框箭头', '#8A93A0'),
    ('tool_close', 'x-lg', u'隐藏窗口', '#FFFFFF'),
    ('clock', 'clock', u'时间字段图标', '#5B6673'),
]

NEED = ['calendar2-date-fill', 'lock-fill', 'unlock-fill', 'gear-fill',
        'chevron-left', 'chevron-right', 'calendar-check-fill', 'chevron-down',
        'x-lg', 'clock']


def svg_inner(name, color='#FFFFFF'):
    """取出 <svg> 内部图形，并把 currentColor 换成指定颜色"""
    path = os.path.join(ICON_SRC, name + '.svg')
    svg = open(path).read()
    svg = svg.replace('currentColor', color)
    i = svg.index('<svg')
    j = svg.index('>', i)
    k = svg.index('</svg>')
    return svg[j + 1:k]


def build(out_name, src_name, size=24, color='#FFFFFF'):
    inner = svg_inner(src_name, color)
    wrapped = ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
               'viewBox="0 0 16 16">%s</svg>' % (size, size, inner))
    tmp = os.path.join(ICON_SRC, '_t_%s.svg' % out_name)
    with open(tmp, 'w') as f:
        f.write(wrapped)
    out = os.path.join(DST, out_name + '.png')
    subprocess.check_call(['rsvg-convert', '-w', str(size), '-h', str(size),
                           tmp, '-o', out])
    os.remove(tmp)
    return out


def main():
    if not os.path.isdir(DST):
        os.makedirs(DST)
    for n in NEED:
        p = os.path.join(ICON_SRC, n + '.svg')
        if not os.path.exists(p):
            subprocess.check_call(
                ['curl', '-sS', '--max-time', '20', '-o', p,
                 'https://raw.githubusercontent.com/twbs/icons/main/icons/%s.svg' % n])
    made = []
    for out_name, src_name, desc, color in TOOLS:
        try:
            made.append(u'%s  %s <- %s' % (build(out_name, src_name, color=color),
                                            desc, src_name))
        except Exception as e:
            print(u'跳过 %s: %s' % (out_name, e))
    for m in made:
        print(m)
    print('工具图标输出目录:', DST)


if __name__ == '__main__':
    main()
