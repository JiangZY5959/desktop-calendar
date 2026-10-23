# -*- coding: utf-8 -*-
"""出厂默认设置。

来源：直接读取用户当前正在使用的 ~/.config/desktop-calendar/calendar.ini，
把里面的值固化为「新装 / 无配置」时的默认值。
只有在用户从未设置过某个键时才写入，已有值一律不覆盖。

注意：
* 不含 ui/pos、ui/size —— 窗口位置和尺寸改为按屏幕可用区域等比自适应
  （见 MainWindow.restore_pos / _adaptive_rect）。
* txtclr / weekclr / jiericlr 在原配置里是空串（沿用所选主题的值），
  因此不写入，切换主题时这几个颜色仍会跟着主题变。
"""

# 键 -> 默认值
DEFAULTS = {
    'ui/theme': 0,                # 玄夜
    'ui/show': 1,                 # 默认显示主窗口

    # 注意：不要在这里写开机自启的默认值。老版本把它写进 [%General]（Qt
    # 的转义写法，跨进程读不回来），现在统一用 app/autostart；没记过时
    # 按"用户没表态"处理，既不建也不删（见 appctx.apply_autostart）。

    # 显示项
    'cal/showline': 1,            # 显示网格线

    # 检查更新：daily / weekly / monthly / manual
    # （新装的软件默认每天自动检查一次；用户可在选项设置里改）
    'update/mode': 'daily',

    # 颜色 / 透明度（#AARRGGBB 或 #RRGGBBAA，与主界面求解顺序一致）
    'color/mainbg': '#05000000',        # 背景
    'color/gridbg': '#05000000',        # 日期格底色
    'color/weekgridbg': '#19000000',    # 星期头条底色
    'color/todayclr': '#361AEAE8',      # 今天格底色
    'color/borderout': '#00FFFFFF',     # 外边框（全透明）
    'color/borderin': '#27FFFFFF',      # 内边框

    # 标记：记录已写入过的默认集版本，便于以后追加新键
    'defaults/version': 1,
}
