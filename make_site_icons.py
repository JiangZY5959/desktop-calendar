# -*- coding: utf-8 -*-
"""生成「关于」窗口里两个项目主页入口图标。

来源与授权（两个图标都只用作跳转到对应网站的入口）：
* site_github.png  —— Simple Icons 的 GitHub 图标，CC0-1.0 公有领域，
  填 GitHub 品牌深色 #24292F，渲染 96px；
* site_gitcode.png —— GitCode 官网 favicon.ico（48x48、自带透明通道），
  原样转 PNG，不做任何修改。
"""
import os
import subprocess

SRC = os.path.dirname(os.path.abspath(__file__))
ICON_SRC = os.path.join(SRC, 'icon_src')
DST = os.path.join(SRC, 'brl', 'resources', 'icons')
GH_SVG = 'https://cdn.jsdelivr.net/npm/simple-icons@13/icons/github.svg'
GC_ICO = 'https://gitcode.com/favicon.ico'


def fetch(url, path):
    if os.path.exists(path):
        return
    subprocess.check_call(['curl', '-sSL', '--max-time', '30', '-o', path, url])


def main():
    if not os.path.isdir(DST):
        os.makedirs(DST)
    gh_svg = os.path.join(ICON_SRC, 'github.svg')
    fetch(GH_SVG, gh_svg)
    svg = open(gh_svg).read()
    if 'fill=' not in svg.split('>', 1)[0]:
        svg = svg.replace('<svg ', '<svg fill="#24292F" ', 1)
        with open(gh_svg, 'w') as f:
            f.write(svg)
    out_gh = os.path.join(DST, 'site_github.png')
    subprocess.check_call(['rsvg-convert', '-w', '96', '-h', '96',
                           gh_svg, '-o', out_gh])
    print(out_gh)

    gc_ico = os.path.join(ICON_SRC, 'gitcode.ico')
    fetch(GC_ICO, gc_ico)
    out_gc = os.path.join(DST, 'site_gitcode.png')
    subprocess.check_call(['convert', gc_ico, out_gc])
    print(out_gc)


if __name__ == '__main__':
    main()
