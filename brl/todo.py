# -*- coding: utf-8 -*-
"""待办/记事：编辑窗（还原 UIWnd 520x460）+ 列表（EditNoteList 400x360）。"""
import datetime

from PyQt5.QtCore import Qt, QDate, QTime, QPoint, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QFont, QPen, QKeySequence, QCursor
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QComboBox, QCheckBox,
                             QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QDateEdit, QTimeEdit, QDialog, QListWidget,
                             QListWidgetItem, QMessageBox, QFrame, QSizePolicy,
                             QShortcut, QMenu, QAbstractItemView, QApplication)

from . import data as D
from . import theme as T
from . import lunar as L
from .timepick import TimePick, TimePopup, TimeWheel, ACCENT
from . import APP_NAME

CATEGORIES = [u'生活', u'工作', u'家庭', u'亲友', u'自己']
REPEATS = [u'不重复', u'每年重复', u'每月重复', u'每周重复']
REMINDS = [u'不提醒', u'前一天提醒', u'当天提醒']
PALETTE = ['#FFFFFFFF', '#FFFF4D4D', '#FFFFA640', '#FFFFE14D', '#FF5CD65C',
           '#FF4DC4FF', '#FF7C8CFF', '#FFFF7CD6', '#FF9E9E9E', '#FF000000']


def combo_style(compact=False):
    """下拉框统一外观：细边框 + 自绘箭头，避免系统样式又粗又暗。"""
    p = D.res('icons', 'nav_down.png')
    pad = '6px 20px 6px 8px' if compact else '4px 26px 4px 9px'
    return (
        'QComboBox{background:#FFFFFF;border:1px solid #DEE3E8;border-radius:5px;'
        'padding:%s;color:#202020;font-size:14px;min-height:20px;}' % pad +
        'QComboBox:hover{border:1px solid #9FC5F5;}'
        'QComboBox:focus{border:1px solid #2F7BFF;}'
        'QComboBox:disabled{background:#F5F6F8;color:#A8AEB6;border-color:#E9ECEF;}'
        'QComboBox::drop-down{subcontrol-origin:padding;subcontrol-position:top right;'
        'width:24px;border-left:1px solid #F0F2F5;}'
        'QComboBox::down-arrow{image:url(%s);width:12px;height:12px;}'
        'QComboBox:disabled::down-arrow{opacity:0.4;}'
        'QComboBox QAbstractItemView{background:#FFFFFF;border:1px solid #DEE3E8;'
        'border-radius:6px;padding:4px 0;outline:0;}'
        'QComboBox QAbstractItemView::item{min-height:28px;padding:4px 12px;'
        'color:#202020;}'
        'QComboBox QAbstractItemView::item:hover{background:#EDF4FE;}'
        'QComboBox QAbstractItemView::item:selected{background:#DCEAFB;'
        'color:#202020;}' % p)


class ColorPicker(QPushButton):
    """文本颜色选择（还原 ClrButton）"""
    colorChanged = pyqtSignal(str)

    def __init__(self, color='#FFFFFFFF', parent=None):
        QPushButton.__init__(self, parent)
        self._c = color
        self.setFixedSize(140, 30)
        self.clicked.connect(self._pick)

    def color(self):
        return self._c

    def setColor(self, c):
        self._c = c
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        T.paint_round(p, self.rect().adjusted(0, 0, -1, -1), 4, '#3FFFFFFF',
                      border='#FFE6E7E8')
        T.paint_round(p, self.rect().adjusted(8, 6, -8, -6), 3, self._c)

    def _pick(self):
        dlg = T.zh_color_dialog(QColor(self._c), self, u'选择文本颜色')
        if dlg.exec_() == QDialog.Accepted:
            self._c = dlg.currentColor().name(QColor.HexArgb).upper()
            self.update()
            self.colorChanged.emit(self._c)


class TodoEditDialog(QDialog):
    """编辑待办（还原 520x460 编辑窗）"""

    def __init__(self, store, date=None, todo=None, parent=None):
        QDialog.__init__(self, parent)
        self._store = store
        self._todo = todo
        self.setWindowTitle(u'编辑待办')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(520, 460)
        self.setStyleSheet(
            'QDialog{background:#F2F6FC;border-radius:10px;}'
            'QLabel{color:#202020;font-size:14px;}'
            'QLineEdit,QComboBox,QDateEdit,QTimeEdit{background:#3FFFFFFF;'
            'border:1px solid #E6E7E8;border-radius:4px;padding:3px 6px;color:#202020;}'
            'QPushButton{font-size:14px;}'
            'QCheckBox{color:#202020;font-size:13px;}')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        box = QFrame()
        box.setStyleSheet('QFrame{background:#3FFFFFFF;border-radius:8px;}')
        bl = QGridLayout(box)
        bl.setContentsMargins(12, 12, 12, 12)
        bl.setVerticalSpacing(9)
        bl.setHorizontalSpacing(10)
        bl.setColumnStretch(1, 1)
        bl.setColumnStretch(3, 1)

        bl.addWidget(QLabel(u'待办内容:'), 0, 0)
        self.ed_content = QLineEdit()
        self.ed_content.setPlaceholderText(u'输入内容')
        bl.addWidget(self.ed_content, 0, 1, 1, 3)

        bl.addWidget(QLabel(u'待办分类:'), 1, 0)
        self.cb_type = QComboBox()
        self.cb_type.addItems(CATEGORIES)
        self.cb_type.setStyleSheet(combo_style())
        self.cb_type.setCursor(Qt.PointingHandCursor)
        bl.addWidget(self.cb_type, 1, 1)

        bl.addWidget(QLabel(u'文本颜色:'), 2, 0)
        self.clr = ColorPicker()
        bl.addWidget(self.clr, 2, 1)
        self.ck_italic = QCheckBox(u'斜体')
        bl.addWidget(self.ck_italic, 2, 2)
        self.ck_line = QCheckBox(u'横线')
        bl.addWidget(self.ck_line, 2, 3)

        bl.addWidget(QLabel(u'待办日期:'), 3, 0)
        self.dt = QDateEdit()
        self.dt.setCalendarPopup(True)
        self.dt.setDisplayFormat('yyyy-MM-dd')
        self.dt.setDate(QDate(date.year, date.month, date.day) if date else QDate.currentDate())
        bl.addWidget(self.dt, 3, 1)
        bl.addWidget(QLabel(u'待办重复:'), 3, 2)
        self.cb_repeat = QComboBox()
        self.cb_repeat.addItems(REPEATS)
        self.cb_repeat.setStyleSheet(combo_style())
        self.cb_repeat.setCursor(Qt.PointingHandCursor)
        bl.addWidget(self.cb_repeat, 3, 3)

        bl.addWidget(QLabel(u'待办提醒:'), 4, 0)
        self.cb_remind = QComboBox()
        self.cb_remind.addItems(REMINDS)
        self.cb_remind.setStyleSheet(combo_style())
        self.cb_remind.setMinimumWidth(150)
        self.cb_remind.setCursor(Qt.PointingHandCursor)
        bl.addWidget(self.cb_remind, 4, 1)
        bl.addWidget(QLabel(u'提醒时间:'), 4, 2)
        self.tm = TimePick()
        bl.addWidget(self.tm, 4, 3)
        self.cb_remind.currentIndexChanged.connect(self._sync_remind)
        lay.addWidget(box)
        lay.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel = QPushButton(u'取消')
        cancel.setFixedSize(120, 40)
        cancel.clicked.connect(self.reject)
        ok = QPushButton(u'确定')
        ok.setFixedSize(120, 40)
        ok.clicked.connect(self._ok)
        btns.addWidget(cancel)
        btns.addSpacing(20)
        btns.addWidget(ok)
        btns.addStretch(1)
        lay.addLayout(btns)

        self.tm.setTime(QTime(9, 0))
        self._sync_remind()

        if todo:
            self.ed_content.setText(todo['content'])
            if todo['category'] in CATEGORIES:
                self.cb_type.setCurrentText(todo['category'])
            self.clr.setColor(todo['color'])
            self.ck_italic.setChecked(bool(todo['italic']))
            self.ck_line.setChecked(bool(todo['underline']))
            if todo['date']:
                y, m, d = todo['date'][:10].split('-')
                self.dt.setDate(QDate(int(y), int(m), int(d)))
            self.cb_repeat.setCurrentIndex(todo['repeat'])
            self.cb_remind.setCurrentIndex(todo['remind'])
            if todo['remind_time']:
                hh, mm = todo['remind_time'].split(':')[:2]
                self.tm.setTime(QTime(int(hh), int(mm)))

    def _sync_remind(self, *args):
        """选"不提醒"时把时间选择置灰，选了提醒才可调时间"""
        self.tm.setEnabled(self.cb_remind.currentIndex() > 0)

    def _ok(self):
        if not self.ed_content.text().strip():
            QMessageBox.information(self, APP_NAME, u'请输入待办内容')
            return
        d = self.dt.date()
        remind = self.cb_remind.currentIndex()
        self.result_data = dict(
            content=self.ed_content.text().strip(),
            category=self.cb_type.currentText(),
            color=self.clr.color(),
            italic=1 if self.ck_italic.isChecked() else 0,
            underline=1 if self.ck_line.isChecked() else 0,
            date='%04d-%02d-%02d' % (d.year(), d.month(), d.day()),
            repeat=self.cb_repeat.currentIndex(),
            remind=remind,
            remind_time=self.tm.text(),
        )
        self.accept()


class TodoListDialog(QDialog):
    """当日待办列表（还原 EditNoteList 400x360）"""

    def __init__(self, store, date, parent=None):
        QDialog.__init__(self, parent)
        self._store = store
        self._date = date
        self.setWindowTitle(u'待办清单')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(400, 360)
        # 浅色配色：顶端与主体相近但有区别
        self.setStyleSheet('QDialog{background:#F2F6FC;border-radius:10px;}'
                           'QLabel{color:#202020;font-size:14px;}'
                           '#headStrip{background:#E8F1FB;'
                           'border-top-left-radius:10px;border-top-right-radius:10px;}'
                           'QListWidget{background:white;border:1px solid #E6E7E8;'
                           'color:#202020;font-size:14px;border-radius:6px;}'
                           'QListWidget::item{padding:4px 6px;}'
                           'QListWidget::item:selected{background:#DCEAFB;color:#202020;}'
                           'QPushButton{font-size:13px;}')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 10)
        head = QWidget()
        head.setObjectName('headStrip')
        hl = QHBoxLayout(head)
        hl.setContentsMargins(12, 8, 12, 8)
        self._lb_head = QLabel(u'%s 待办' % date.strftime('%Y-%m-%d'))
        hl.addWidget(self._lb_head)
        hl.addStretch(1)
        tip = QLabel(u'可按住 Ctrl / Shift 多选')
        tip.setStyleSheet('color:#7C8794;font-size:12px;')
        hl.addWidget(tip)
        lay.addWidget(head)
        body = QVBoxLayout()
        body.setContentsMargins(10, 10, 10, 0)
        body.setSpacing(8)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.itemDoubleClicked.connect(self._edit)
        self.list.itemSelectionChanged.connect(self._sync_buttons)
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._ctx_menu)
        body.addWidget(self.list, 1)

        # 底部操作行：添加 / 编辑 / 删除 / 关闭
        btns = QHBoxLayout()
        btns.setSpacing(8)
        add = QPushButton(u'添加待办')
        add.setFixedSize(96, 28)
        add.setStyleSheet('QPushButton{background:#2F7BFF;color:white;border-radius:4px;}'
                          'QPushButton:hover{background:#2568E0;}')
        add.clicked.connect(self._add)
        btns.addWidget(add)
        self._btn_edit = QPushButton(u'编辑待办')
        self._btn_edit.setFixedSize(96, 28)
        self._btn_edit.setStyleSheet(
            'QPushButton{background:#F2F4F8;color:#202020;border:1px solid #DCE1E7;'
            'border-radius:4px;}'
            'QPushButton:hover{background:#E9EEF6;border-color:#9FC5F5;}'
            'QPushButton:disabled{color:#AAB0B8;border-color:#E6E7E8;background:#F7F8FA;}')
        self._btn_edit.clicked.connect(self._edit_selected)
        btns.addWidget(self._btn_edit)
        self._btn_del = QPushButton(u'删除待办')
        self._btn_del.setFixedSize(96, 28)
        self._btn_del.setStyleSheet(
            'QPushButton{background:#F2F4F8;color:#D33A3A;border:1px solid #E3C2C2;'
            'border-radius:4px;}'
            'QPushButton:hover{background:#FBE9E9;border-color:#D33A3A;}'
            'QPushButton:disabled{color:#AAB0B8;border-color:#E6E7E8;background:#F7F8FA;}')
        self._btn_del.clicked.connect(self._delete_selected)
        btns.addWidget(self._btn_del)
        btns.addStretch(1)
        close = QPushButton(u'关闭')
        close.setFixedSize(80, 28)
        close.setStyleSheet(
            'QPushButton{background:#FFFFFF;color:#4A5460;border:1px solid #DCE1E7;'
            'border-radius:4px;}'
            'QPushButton:hover{background:#F2F5F9;}')
        close.clicked.connect(self.accept)
        btns.addWidget(close)
        body.addLayout(btns)
        lay.addLayout(body, 1)

        # Delete 键快捷删除（支持多选）
        sc = QShortcut(QKeySequence(Qt.Key_Delete), self.list)
        sc.setContext(Qt.WidgetShortcut)
        sc.activated.connect(self._delete_selected)

        self.reload()

    @staticmethod
    def _item_color(raw):
        """浅色底上过浅的文字色自动加深，避免看不见"""
        try:
            c = QColor(raw)
        except Exception:
            return QColor('#202020')
        if not c.isValid():
            return QColor('#202020')
        lum = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()
        if lum > 200 and c.alpha() > 100:
            return QColor('#202020')
        c.setAlpha(255)
        return c

    def reload(self):
        self.list.clear()
        rows = self._store.for_date(self._date)
        for t in rows:
            it = QListWidgetItem(u'%s  %s' % (u'✓' if t['done'] else u'○', t['content']))
            it.setData(Qt.UserRole, t['id'])
            f = it.font()
            f.setItalic(bool(t['italic']))
            f.setUnderline(bool(t['underline']))
            it.setFont(f)
            it.setForeground(self._item_color(t['color']))
            self.list.addItem(it)
        self._lb_head.setText(u'%s 待办（%d 项）' % (self._date.strftime('%Y-%m-%d'),
                                                  len(rows)))
        self._sync_buttons()

    def _sync_buttons(self):
        n = len(self.list.selectedItems())
        self._btn_edit.setEnabled(n == 1)
        self._btn_del.setEnabled(n >= 1)
        self._btn_del.setText(u'删除待办' if n <= 1 else u'删除所选 (%d)' % n)

    def _add(self):
        dlg = TodoEditDialog(self._store, self._date, None, self)
        if dlg.exec_() == QDialog.Accepted:
            tid = self._store.add(**dlg.result_data)
            self.reload()
            self._select_by_id(tid)

    def _edit(self, item):
        tid = item.data(Qt.UserRole)
        t = self._store.get(tid)
        if not t:
            return
        dlg = TodoEditDialog(self._store, self._date, t, self)
        if dlg.exec_() == QDialog.Accepted:
            self._store.update(tid, **dlg.result_data)
            self.reload()
            self._select_by_id(tid)

    def _edit_selected(self):
        items = self.list.selectedItems()
        if len(items) != 1:
            QMessageBox.information(self, u'编辑待办', u'请先选中一条待办。')
            return
        self._edit(items[0])

    def _select_by_id(self, tid):
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.UserRole) == tid:
                it.setSelected(True)
                self.list.setCurrentItem(it)
                break

    # ------------------------------------------------ 删除
    def _ctx_menu(self, pos):
        item = self.list.itemAt(pos)
        m = QMenu(self)
        if item is not None:
            m.addAction(u'编辑待办', lambda: self._edit(item))
            m.addAction(u'删除待办', lambda: self._delete_items([item]))
        else:
            m.addAction(u'添加待办', self._add)
        m.exec_(self.list.viewport().mapToGlobal(pos))

    def _delete_selected(self):
        items = self.list.selectedItems()
        if not items:
            # 没有选中项时给出提示，而不是静默无反应
            QMessageBox.information(self, u'删除待办', u'请先选中要删除的待办。')
            return
        self._delete_items(items)

    def _delete_items(self, items):
        ids, names = [], []
        for it in items:
            tid = it.data(Qt.UserRole)
            t = self._store.get(tid)
            if not t:
                continue
            ids.append(tid)
            names.append(t.get('content', ''))
        if not ids:
            return
        if len(ids) == 1:
            msg = u'确定删除这条待办吗？\n\n%s' % names[0]
        else:
            head = u'\n'.join(u'· %s' % n for n in names[:8])
            more = u'\n…等 %d 条' % len(names) if len(names) > 8 else u''
            msg = u'确定删除这 %d 条待办吗？\n\n%s%s' % (len(ids), head, more)
        r = QMessageBox.question(self, u'删除待办', msg,
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r != QMessageBox.Yes:
            return
        for tid in ids:
            self._store.remove(tid)
        self.reload()
