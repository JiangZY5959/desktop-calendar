# -*- coding: utf-8 -*-
"""在真实桌面 :0 上启动主窗口并截图，用于肉眼核查布局。"""
import os
import sys
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QTimer

from brl import store as S
from brl import data as D
from brl.mainwin import MainWindow


class Ctx(object):
    def quit_app(self):
        pass


def main():
    app = QApplication(sys.argv)
    st = S.Store()
    st.settings().setValue('ui/size', ','.join(map(str, list(SIZE))))
    st.settings().setValue('ui/pos', '60,60')
    st.settings().sync()
    w = MainWindow(st, Ctx())
    w.move(60, 60)
    w.resize(*SIZE)
    w.show()
    QApplication.processEvents()

    def shoot():
        pm = w.grab()
        pm.save(OUT)
        print('saved', OUT, pm.width(), pm.height())
        # 顺便导出关键控件几何，便于判断裁切
        for name, wd in (('b_view', w._btn_view), ('b_lock', w._btn_lock),
                         ('b_menu', w._btn_menu),
                         ('lb_month', w._lb_month),
                         ('b_prev', w._b_prev), ('b_next', w._b_next),
                         ('b_today', w._b_today),
                         ('cal', w._cal), ('grip', w._grip)):
            g = wd.geometry()
            print('  %-14s x=%4d y=%4d w=%4d h=%4d  visible=%s'
                  % (name, g.x(), g.y(), g.width(), g.height(), wd.isVisible()))
        print('  window w=%d h=%d  sizeHint=%s' % (w.width(), w.height(), w.sizeHint()))
        app.quit()

    QTimer.singleShot(1200, shoot)
    app.exec_()


if __name__ == '__main__':
    OUT = sys.argv[1] if len(sys.argv) > 1 else '/tmp/main.png'
    SIZE = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 3 else (560, 620)
    main()
