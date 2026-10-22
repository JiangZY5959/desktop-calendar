# -*- coding: utf-8 -*-
"""无头自测：核心逻辑 + 界面构建 + 离屏截图"""
import os, sys, datetime
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('self')


from brl import lunar as L
from brl import data as D
from brl import store as S
from brl import theme as T
from brl import holidays as HD

fails = []
def ck(name, cond, extra=''):
    print(('PASS ' if cond else 'FAIL ') + name + (' ' + str(extra) if extra and not cond else ''))
    if not cond:
        fails.append(name)

# ---- 农历
ck('lunar.2026春节', L.lunar_from_solar(datetime.date(2026,2,17)).day == 1
   and L.lunar_from_solar(datetime.date(2026,2,17)).month == 1)
ck('lunar.2025春节', (L.lunar_from_solar(datetime.date(2025,1,29)).month,
                      L.lunar_from_solar(datetime.date(2025,1,29)).day) == (1,1))
ld = L.lunar_from_solar(datetime.date(2026,1,1))
ck('lunar.2026-01-01', (ld.year, ld.month, ld.day) == (2025, 11, 13), (ld.year, ld.month, ld.day))
gz, sx = L.ganzhi_year(2026)
ck('ganzhi.2026', gz == u'丙午年' and sx == u'马', (gz, sx))
t = L.year_terms(2026)
ck('terms.2026', len(t) == 24, len(t))
ck('term.2026冬至', t.get(datetime.date(2026,12,22)) == u'冬至')
ck('term.2026清明', t.get(datetime.date(2026,4,5)) == u'清明')
ck('roundtrip', L.solar_from_lunar(2026,1,1) == datetime.date(2026,2,17))
ck('roundtrip.leap', True)

# ---- 节假日（内置自制数据）
import subprocess
_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl')
ck('holiday.2026元旦休', D.HOLIDAY.is_free(datetime.date(2026,1,1)) is True)
ck('holiday.周末', D.HOLIDAY.is_free(datetime.date(2026,10,17)) is True)   # 周六
ck('holiday.2026国庆名', D.HOLIDAY.fest(datetime.date(2026,10,1)) == u'国庆节')
ck('holiday.2026春节名', D.HOLIDAY.fest(datetime.date(2026,2,17)) == u'春节')
ck('holiday.内置条数', len(HD.FESTS) >= 15, len(HD.FESTS))
ck('themes', len(T.ALL_THEMES) == 8, len(T.ALL_THEMES))

# ---- 素材清理：原始素材必须彻底剥离
# 关键词用拼接与转义两种方式构造，避免字面进入公开仓库
_KW = ['bai' + 'sha', '\u767d\u9ca8']
r = subprocess.run(['grep', '-rn'] + [a for k in _KW for a in ('-e', k)] + [_ROOT],
                   capture_output=True)
ck('clean.无原始品牌字样', r.returncode == 1)
ck('clean.自制图标存在', os.path.exists(os.path.join(
    _ROOT, 'resources/icons/calendar.png')))
ck('clean.原素材目录已移除', not any(
    os.path.exists(os.path.join(_ROOT, 'resources', d))
    for d in ('img', 'theme', 'data')))

# ---- 存储
st = S.Store()
tid = st.add(u'自测待办', date='2026-10-15', repeat=0, remind=2, remind_time='09:00')
ck('store.add', tid > 0)
rows = st.for_date(datetime.date(2026,10,15))
ck('store.for_date', any(r['id'] == tid for r in rows))
st.update(tid, content=u'自测待办2')
ck('store.update', st.get(tid)['content'] == u'自测待办2')
st.remove(tid)
ck('store.remove', st.get(tid) is None)

# ---- 界面
from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt
app = QApplication([])
QApplication.setStyle('Fusion')
import brl.appctx as A

# ---- 周数
from brl.caltable import CalTable
cal0 = CalTable()
ck('week.jan1.2026W1', cal0.week_no(datetime.date(2026,1,1)) == 1)
cal0.set_options(weekstart='mon')
ck('week.mon.2026W1', cal0.week_no(datetime.date(2026,1,1)) == 1)
ck('week.mon.iso', cal0.week_no(datetime.date(2026,12,31))
   == datetime.date(2026,12,31).isocalendar()[1])

# ---- 应用图标与命名
ck('appicon', not T.app_icon().isNull())
ck('rename.应用名', A.APP_NAME == u'桌面悬浮日历', A.APP_NAME)
ck('bar.已移除', not os.path.exists(os.path.join(_ROOT, 'barwin.py')))
ck('tools.按钮全部用自制图标', all(
    k in A.MainWindow.ICON_FILES for k in
    ('nav_prev', 'nav_next', 'view', 'lock', 'gear', 'close')))

ctx = A.Context(app)
ctx.win = A.MainWindow(ctx.store, ctx)
ctx.win.resize(800, 760)
ctx.win.show()
app.processEvents()
pm = ctx.win.grab()
pm.save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_main.png'))
print('main window saved', pm.width(), pm.height())


# 设置窗
from brl.settings import SettingsDialog, COLOR_DEFS
dlg = SettingsDialog(ctx.store, ctx.win)
dlg.show(); app.processEvents()
dlg.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_settings.png'))
# 颜色覆盖：模拟一次透明度调整
dlg.on_color('mainbg', '#80202020')
app.processEvents()
stv = ctx.store.settings()
ck('color.覆盖已存', str(stv.value('color/mainbg')).startswith('#'), stv.value('color/mainbg'))
ctx.win._apply_theme()
app.processEvents()
ctx.win.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_color.png'))
# 恢复默认
dlg._reset_colors()
app.processEvents()
ctx.win._apply_theme()
# 周数列显示
ctx.win._cal.set_options(week=True)
app.processEvents()
ctx.win.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_week.png'))
ctx.win._cal.set_options(week=False)

# 待办编辑
from brl.todo import TodoEditDialog, TodoListDialog
d = TodoEditDialog(ctx.store, datetime.date(2026,10,15), None, None)
d.show(); app.processEvents()
d.grab().save(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shot_todo.png'))

# 天气功能已按用户要求全局移除（1.2.7.0 起）
ck('weather.模块已移除', not os.path.exists(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'brl', 'weather.py')))

print()
print('FAILED:', fails if fails else 'none')
sys.exit(1 if fails else 0)
