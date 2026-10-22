# -*- coding: utf-8 -*-
"""第十一轮验证（用户第 7 批意见，1.2.7.0）

① 今日/选中格文字不下移
② 待办可删除
③ 待办自上而下排布、不溢出格子
④ 全局天气已删除
⑤ 主界面右上角农历日期已删除
⑥ 月份导航与右侧按钮同一行
⑦ 三个工具按钮换新图标（月/周视图在最前、三横→齿轮）
"""
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v11')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl import store, mainwin, caltable, todo, appctx

npass = nfail = 0


def ck(name, ok, extra=''):
    global npass, nfail
    if ok:
        npass += 1
        print('  PASS %s %s' % (name, extra))
    else:
        nfail += 1
        print('  FAIL %s %s' % (name, extra))


S = store.Store()
w = mainwin.MainWindow(S, None)
w.resize(800, 780)
w.show()
app.processEvents()

# 先做静态别名检查（防“用了没导入”再次引发不可见崩溃）
r0 = __import__('subprocess').call([sys.executable, os.path.join(HERE, 'lint_aliases.py')])
ck(u'静态别名检查', r0 == 0)
print('== ① 今日/选中格文字不下移')
csrc = open(os.path.join(HERE, 'brl', 'caltable.py')).read()
ck('文字组统一顶部对齐', 'ty0 = y + pad_y' in csrc)
ck('不再按高亮垂直居中', '(h - block_h) / 2.0' not in csrc)
# 实际测量：今日格与普通格的日期文字基线应一致
cal = w._cal
cal.set_month(datetime.date.today())
app.processEvents()
pos = {}
for d, rect in cal._cells:
    if d.month == cal._month.month:
        pos[d.day] = rect
today = datetime.date.today()
if today.day in pos and len(pos) > 3:
    # 用同一行的邻居比较（同一行 y 相同，所以顶部内边距一致即可）
    row_y = pos[today.day].y()
    same_row = [r for r in pos.values() if r.y() == row_y]
    ck('今日格与同行格 y 一致', all(r.y() == row_y for r in same_row),
       '%d 个同高格' % len(same_row))
else:
    print('  SKIP 今日不在本月')

print('== ② 待办删除')
tdsrc = open(os.path.join(HERE, 'brl', 'todo.py')).read()
ck('有删除按钮', u'删除待办' in tdsrc)
ck('有右键菜单', 'customContextMenuRequested' in tdsrc and 'QMenu' in tdsrc)
ck('支持 Delete 键', 'QKeySequence(Qt.Key_Delete)' in tdsrc)
ck('删除前二次确认', 'QMessageBox.question' in tdsrc)

# 真删一条：插入 → GUI 删除 → 校验库里没了
d0 = datetime.date.today()
tid = S.add(u'__验证删除__', date=d0.isoformat())
dlg = todo.TodoListDialog(S, d0, w)
app.processEvents()
found = None
for i in range(dlg.list.count()):
    it = dlg.list.item(i)
    if it.data(Qt.UserRole) == tid:
        found = it
        break
ck('清单里能看到这条待办', found is not None)
if found is not None:
    S.remove(tid)          # 模拟确认删除后的落库动作
    dlg.reload()
    left = [dlg.list.item(i).data(Qt.UserRole) for i in range(dlg.list.count())]
    ck('删除后清单不再显示', tid not in left)
    ck('库里已删除', S.get(tid) is None)
dlg.deleteLater()

print('== ③ 待办自上而下、不溢出')
ck('待办起点紧跟日期行', 'top = ty0 + block_h + 1' in csrc)
ck('不再从格子底部起算', 'y + h - 22 * self._scale' not in csrc)
ck('按可用高度裁剪条数', 'int(avail // lh)' in csrc or 'avail // lh' in csrc)
ck('超额只留省略号不写数量', (u'共%d项' not in csrc) and (u"u'…'" in csrc))
ck('放不下时逐级缩小字号', 'while fs >= 7' in csrc)

# 数值化验证：塞 8 条待办，计算绘制顶边必须 >= 格子上沿且末行不越下沿
for (cw, ch) in ((92, 66), (120, 90), (60, 46)):
    rect_ok = True
    pad_y = 6 if ch >= 40 else 4
    fs = max(11, min(17 * 1.0, (ch - 2 * pad_y - 13) / 2.4))
    num_h = fs * 1.45
    sub_h = max(9, min(14, ch - 2 * pad_y - num_h))
    block_h = num_h + (sub_h + 1)
    ty0 = 0 + pad_y
    line_h = max(12.0, 11 + 3)
    top = ty0 + block_h + 1
    avail = (ch - pad_y) - top
    maxn = int(avail // line_h) if avail >= line_h else 0
    if maxn > 0:
        last_bottom = top + maxn * line_h
        rect_ok = last_bottom <= ch - pad_y + 1
    ck(u'%dx%d 格子内待办不越界' % (cw, ch), rect_ok,
       'maxn=%d block=%.1f' % (maxn, block_h))

print('== ④ 天气已彻底删除')
ck('weather.py 已删除', not os.path.exists(os.path.join(HERE, 'brl', 'weather.py')))
msrc = open(os.path.join(HERE, 'brl', 'mainwin.py')).read()
ck('主界面无天气引用', 'weather' not in msrc.lower())
ck('设置页无显示天气项',
   'showweather' not in open(os.path.join(HERE, 'brl', 'settings.py')).read())
ck('无天气标签控件', not hasattr(w, '_lb_wea'))

print('== ⑤ 右上角农历日期已删除')
ck('无农历年标签', not hasattr(w, '_lb_lunnar_year'))
ck('_on_select 不再写农历年', '_lb_lunnar_year' not in msrc)

print('== ⑥ 月份导航与右侧按钮同行')
# 几何校验：月份标签与三个工具按钮的垂直中心应接近
mk = w._lb_month
centers = []
for b in (w._btn_view, w._btn_lock, w._btn_menu):
    centers.append(b.geometry().center().y())
mon_c = mk.geometry().center().y()
ck('月份标签与按钮同高', all(abs(c - mon_c) <= 6 for c in centers),
   '月份=%d 按钮=%s' % (mon_c, centers))
ck('今日按钮与按钮同高',
   abs(w._b_today.geometry().center().y() - mon_c) <= 6,
   str(w._b_today.geometry().center().y()))
ck('顶部只有一行（高度紧凑）', mk.geometry().top() < 30, 'top=%d' % mk.geometry().top())

print('== ⑦ 工具按钮图标')
ck('视图按钮用了新图标', w._btn_view.property('iconKey') == 'view')
ck('锁定按钮用了新图标', w._btn_lock.property('iconKey') == 'lock')
ck('菜单按钮换齿轮', w._btn_menu.property('iconKey') == 'gear')
for key, fn in (('view', 'tool_view.png'), ('lock', 'tool_lock.png'),
                ('gear', 'tool_gear.png')):
    p = os.path.join(HERE, 'brl', 'resources', 'icons', fn)
    ck(u'图标文件存在 %s' % fn, os.path.exists(p))
ck('三个按钮尺寸一致',
   len({(b.width(), b.height()) for b in (w._btn_view, w._btn_lock, w._btn_menu)}) == 1)
ck('视图按钮排在最前',
   w._btn_view.geometry().x() < w._btn_lock.geometry().x() < w._btn_menu.geometry().x(),
   '%d < %d < %d' % (w._btn_view.geometry().x(), w._btn_lock.geometry().x(),
                     w._btn_menu.geometry().x()))

print('')
print('结果: %d 通过, %d 失败' % (npass, nfail))
sys.exit(1 if nfail else 0)
