#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成「检查更新」用的版本清单 releases/latest.json。

软件启动后按检查周期访问仓库里的这份清单：

    https://<api 主机>/repos/<owner>/<repo>/contents/releases/latest.json?ref=master

清单里带 deb 的仓库 blob 直链。blob sha 只由文件内容决定，可以本地算出来
（等价于 ``git hash-object``），所以客户端一次请求就能拿到下载地址，不需要
再查一遍接口。

用法：
    python3 make_manifest.py                  # 更新说明从 CHANGELOG 里取当前版本
    python3 make_manifest.py --notes "……"     # 手写更新说明
    python3 make_manifest.py --notes-file n.txt

发布顺序（务必照做，否则客户端看到的清单指向一个还不存在的 blob）：
    1. python3 makedeb.py
    2. cp dist/desktop-calendar_<ver>_arm64.deb releases/
    3. python3 make_manifest.py
    4. git add -A && git commit && git push
    5. 打 tag 并建一个同名 Release（v<ver>）
"""
import hashlib
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

OWNER = 'gcw_6ciOFeue'
REPO = 'desktop-calendar'
BRANCH = 'master'
DEB_TMPL = 'desktop-calendar_%s_arm64.deb'

from brl import __version__ as VER        # noqa: E402


def blob_sha(path):
    """git blob sha1（与 git hash-object 一致），只用标准库。"""
    h = hashlib.sha1()
    size = os.path.getsize(path)
    h.update(b'blob %d\0' % size)
    with open(path, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(1 << 20)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def notes_from_changelog(ver):
    p = os.path.join(ROOT, 'CHANGELOG.md')
    if not os.path.exists(p):
        return ''
    txt = open(p, encoding='utf-8').read()
    m = re.search(r'^##\s*v?%s\s*$(.*?)(?=^##\s|\Z)' % re.escape(ver),
                  txt, re.S | re.M)
    if not m:
        return ''
    body = m.group(1).strip()
    # 去掉 markdown 记号，弹窗里按纯文本显示
    body = re.sub(r'\*\*(.+?)\*\*', r'\1', body)
    body = re.sub(r'`(.+?)`', r'\1', body)
    body = body.replace('- ', '· ')
    return body.strip()


def main(argv):
    notes = ''
    if '--notes' in argv:
        notes = argv[argv.index('--notes') + 1]
    elif '--notes-file' in argv:
        notes = open(argv[argv.index('--notes-file') + 1], encoding='utf-8').read()
    if not notes:
        notes = notes_from_changelog(VER)
    if not notes:
        notes = u'版本 %s' % VER

    rel = os.path.join(ROOT, 'releases')
    if not os.path.isdir(rel):
        os.makedirs(rel)
    deb = os.path.join(rel, DEB_TMPL % VER)
    if not os.path.exists(deb):
        alt = os.path.join(ROOT, 'dist', DEB_TMPL % VER)
        if os.path.exists(alt):
            import shutil
            shutil.copy2(alt, deb)
        else:
            sys.stderr.write('找不到安装包：%s\n先跑 makedeb.py\n' % deb)
            return 2

    bs = blob_sha(deb)
    data = {
        'version': VER,
        'tag': 'v' + VER,
        'file': DEB_TMPL % VER,
        'size': os.path.getsize(deb),
        'sha256': sha256(deb),
        'url': 'https://raw.gitcode.com/%s/%s/blobs/%s/releases/%s'
               % (OWNER, REPO, bs, DEB_TMPL % VER),
        'released': __import__('datetime').date.today().isoformat(),
        'notes': notes,
    }
    out = os.path.join(rel, 'latest.json')
    with open(out, 'w', encoding='utf-8') as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=2) + '\n')
    print('written: %s' % out)
    for k in ('version', 'size', 'sha256', 'url'):
        print('  %-8s %s' % (k, data[k]))
    print('\n下一步：git add -A && git commit -m "release v%s" && git push，'
          '然后打 tag v%s 并建 Release。' % (VER, VER))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
