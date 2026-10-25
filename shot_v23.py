# -*- coding: utf-8 -*-
"""本轮改动的离屏截图 + 圆角断言：周一打头的月历、齿轮菜单、设置页页签。"""
import datetime
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from PyQt5.QtWidgets import QApplication

app = QApplication(sys.argv)

from brl import theme as T
from brl.caltable import CalTable
from brl.settings import SettingsDialog
from brl import store

# ---- ① 月历：周一打头
cal = CalTable()
cal.resize(700, 520)
cal.set_month(datetime.date.today())
cal.show()
app.processEvents()
cal.grab()                      # 先画一遍，_cells 才有内容
days = [d for d, _r in cal._cells]
head = [d.isoformat() for d in days[:7]]
print('首行七天:', head)
print('首列星期:', [d.strftime('%a') for d in days[:7]])
print('首行第一天是周一?', days[0].weekday() == 0)
print('第 7 列是周日?', days[6].weekday() == 6)
cal.grab().save(os.path.join(HERE, 'v23_cal.png'))

# 周视图：选中某天，起始应为该周周一
cal.set_view('week')
cal.set_selected(datetime.date.today())
cal.grab()
wdays = [d for d, _r in cal._cells]
print('周视图首天:', wdays[0].isoformat(), '星期', wdays[0].strftime('%a'))
print('周视图首天是周一?', wdays[0].weekday() == 0)
cal.grab().save(os.path.join(HERE, 'v23_cal_week.png'))
cal.set_view('month')

# ---- ② 齿轮菜单（圆角）
m = T.CardMenu()
m.addAction(u'检查更新')
m.addAction(u'选项设置')
m.addAction(u'关于')
m.addSeparator()
m.addAction(u'退出软件')
m.show()
app.processEvents()
img = m.grab().toImage()
corner = img.pixelColor(0, 0)
center = img.pixelColor(img.width() // 2, img.height() // 2)
print('菜单左上角 alpha:', corner.alpha(), ' 中心:', center.name())
print('圆角生效?', corner.alpha() == 0)
m.grab().save(os.path.join(HERE, 'v23_menu.png'))

# ---- ③ 设置页左侧页签
s = store.Store()
dlg = SettingsDialog(s)
dlg.show()
app.processEvents()
print('页签按钮样式:', dlg._tabs[1].styleSheet()[:60], '...')
dlg.grab().save(os.path.join(HERE, 'v23_settings.png'))
print('saved v23_cal / v23_cal_week / v23_menu / v23_settings')
