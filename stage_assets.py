#!/usr/bin/env python3
"""把逆向得到的原始资源整理为 UOS 应用可用的资源目录（剔除会员/VIP 素材）。"""
import os, shutil, glob, sys

SRC = '/home/uos/WorkBuddy/2026-10-15-14-49-19/analysis'
DST = '/home/uos/WorkBuddy/2026-10-15-14-49-19/build/brl/resources'

BANNED = ('vip', 'portrait', 'openvip', 'btn_open1', 'btn_open2')

imgdst = os.path.join(DST, 'img')
os.makedirs(imgdst, exist_ok=True)

# 1. 主程序图片资源（递归复制，剔除 vip）
n = 0
for root, dirs, files in os.walk(os.path.join(SRC, 'app_res/img')):
    for f in files:
        rel = os.path.relpath(os.path.join(root, f), os.path.join(SRC, 'app_res/img'))
        low = rel.lower().replace('\\', '/')
        if any(b in low for b in BANNED):
            continue
        dst = os.path.join(imgdst, rel.replace('\\', '/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(os.path.join(root, f), dst)
        n += 1
print("img:", n)

# 2. 天气图标 -> img/wth
wth = os.path.join(imgdst, 'wth')
os.makedirs(wth, exist_ok=True)
w = 0
for f in glob.glob(os.path.join(SRC, 'wea/*.png')):
    shutil.copy2(f, os.path.join(wth, os.path.basename(f)))
    w += 1
print("wth:", w)

# 3. 悬浮条皮肤
sk = os.path.join(DST, 'skins')
if os.path.exists(sk):
    shutil.rmtree(sk)
os.makedirs(sk)
for d in sorted(glob.glob(os.path.join(SRC, 'skins_x/*'))):
    name = os.path.basename(d)
    shutil.copytree(d, os.path.join(sk, name))
print("skins:", len(os.listdir(sk)))

# 4. 主题配色
th = os.path.join(DST, 'theme')
os.makedirs(th, exist_ok=True)
for f in glob.glob(os.path.join(SRC, 'app/theme/theme*.xml')):
    shutil.copy2(f, th)
print("theme xml:", len(os.listdir(th)))

# 5. 数据
dt = os.path.join(DST, 'data')
os.makedirs(dt, exist_ok=True)
for f in ('holiday.xml', 'yj.db', 'city.xml'):
    shutil.copy2(os.path.join(SRC, 'app', f), os.path.join(dt, f))
print("data:", os.listdir(dt))

# 6. 图标（exe 里 20 个 ICON 资源：PNG 直接存，BMP/ICO 结构解析取最大帧）
icodir = os.path.join(DST, 'icons')
os.makedirs(icodir, exist_ok=True)
from PIL import Image
import struct


def ico_frames(data):
    """返回 [(w,h,bytes)]，支持 PNG 帧 与 BMP 帧"""
    out = []
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        im = Image.open(__import__('io').BytesIO(data))
        out.append((im.width, im.height, data))
        return out
    if len(data) < 6:
        return out
    _, typ, cnt = struct.unpack_from('<HHH', data, 0)
    if typ != 1:
        return out
    for i in range(cnt):
        o = 6 + i * 16
        if o + 16 > len(data):
            break
        w, h, _, _, _, bc, sz, off = struct.unpack_from('<BBBBHHII', data, o)
        payload = data[off:off + sz]
        if payload[:8] == b'\x89PNG\r\n\x1a\n':
            im = Image.open(__import__('io').BytesIO(payload))
            out.append((im.width, im.height, payload))
            continue
        # BMP: BITMAPINFOHEADER，高度为 2 倍（XOR+AND 掩码）
        if len(payload) >= 40:
            bw, bh = struct.unpack_from('<ii', payload, 4)
            w = bw or w
            h = bh // 2 or h
            bpp = bc * 8 if bc else 32
            planes, bitcnt = struct.unpack_from('<HH', payload, 12)
            bpp = bitcnt or bpp
            im = Image.frombytes('RGBA', (w, h), b'\x00\x00\x00\x00' * w * h)
            try:
                if bpp == 32:
                    row = w * 4
                    px = payload[40:40 + row * h]
                    for y in range(h):
                        line = px[y * row:(y + 1) * row]
                        for x in range(w):
                            b, g, r, a = line[x * 4:x * 4 + 4]
                            if a == 0 and (r or g or b):
                                a = 255
                            im.putpixel((x, h - 1 - y), (r, g, b, a))
                    out.append((w, h, None))
                    out[-1] = (w, h, im)
            except Exception:
                pass
    return out


best = None
for i, p in enumerate(sorted(glob.glob(os.path.join(SRC, 'out_app/*_3__*.bin')))):
    data = open(p, 'rb').read()
    for w, h, val in ico_frames(data):
        if val is None:
            continue
        if isinstance(val, Image.Image):
            im = val
        else:
            im = Image.open(__import__('io').BytesIO(val)).convert('RGBA')
        if best is None or im.width > best.width:
            best = im
        if im.width >= 128:
            im.save(os.path.join(icodir, 'extracted_%d.png' % im.width))
if best is not None:
    best.save(os.path.join(icodir, 'extracted.png'))
    print("icon best:", best.size)
print("total img files:", sum(len(fs) for _, _, fs in os.walk(DST)))
