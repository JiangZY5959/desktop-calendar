# -*- coding: utf-8 -*-
"""本轮截图：字体颜色带透明度滑杆 + 半透明字体在日历上的实际效果。

用真桌面 X11 渲染（离屏的 CJK 字体度量偏宽，宽度类结论不可信）。
"""
import datetime
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TD = tempfile.mkdtemp(prefix='shot27-')
os.environ['XDG_DATA_HOME'] = os.path.join(TD, 'data')
os.environ['XDG_CONFIG_HOME'] = os.path.join(TD, 'cfg')
for d in (os.environ['XDG_DATA_HOME'], os.environ['XDG_CONFIG_HOME']):
    os.makedirs(os.path.join(d, 'desktop-calendar'))

from PyQt5.QtWidgets import QApplication          # noqa: E402

app = QApplication(sys.argv)

from brl import store                             # noqa: E402
from brl.settings import SettingsDialog            # noqa: E402
from brl.caltable import CalTable                  # noqa: E402

st = store.STORE.settings()
# 字体色设成半透明，便于肉眼看出变化
st.setValue('color/txtclr', '#B3000000')
st.setValue('color/weekclr', '#66CC0000')
st.setValue('color/jiericlr', '#FFD50000')
st.sync()

dlg = SettingsDialog(store.STORE, None)
dlg.show()
app.processEvents()
dlg.grab().save(os.path.join(HERE, 'v27_settings_alpha.png'))
print('settings saved')

# 主界面：日历格子里写字，看半透明字色是否生效
cal = CalTable()
cal.resize(760, 520)
cal.set_month(datetime.date.today())
cfg = {
    'txtclr': '#B3000000', 'weekclr': '#66CC0000', 'jiericlr': '#FFD50000',
    'todayclr': '#FFE8F3FF', 'mainbgndclr': '#FFFFFFFF',
    'gridbgndclr': '#FFFAFAFA', 'weekgridbgndclr': '#FFF0F4F8',
    'borderoutclr': '#FFD0D6DD', 'borderinclr': '#FFE6E9ED',
}
cal.set_theme(cfg)
cal.show()
app.processEvents()
cal.grab()
cal.grab().save(os.path.join(HERE, 'v27_cal_alpha.png'))
print('calendar saved')
