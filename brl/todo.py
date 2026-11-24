# -*- coding: utf-8 -*-
"""待办/记事：编辑窗（还原 UIWnd 520x460）+ 列表（EditNoteList 400x360）。"""
import datetime

from PyQt5.QtCore import Qt, QDate, QTime, QPoint, QSize, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QFont, QPen, QKeySequence, QCursor
from PyQt5.QtWidgets import (QWidget, QLabel, QLineEdit, QComboBox, QCheckBox,
                             QPushButton, QHBoxLayout, QVBoxLayout, QGridLayout,
                             QDateEdit, QTimeEdit, QDialog, QListWidget,
                             QListWidgetItem, QFrame, QSizePolicy,
                             QShortcut, QMenu, QAbstractItemView, QApplication,
                             QRadioButton, QButtonGroup, QSpinBox)

from . import data as D
from . import theme as T
from . import lunar as L
from .timepick import TimePick, TimePopup, TimeWheel, ACCENT
from . import APP_NAME
from . import updatedlg as DLG

def style_date_picker(date_edit):
    """把 QDateEdit 的日历弹窗年份框撑宽到能完整显示 4 位年份。

    UOS 上 QCalendarWidget 顶部的年份 QSpinBox 默认被压到 ~40px，
    "2026" 只露出 "20"。直接对内部控件设 min-width 并同步样式表。
    """
    cal = date_edit.calendarWidget()
    cal.setStyleSheet(
        'QCalendarWidget QSpinBox{min-width:80px;font-size:13px;padding:2px 4px;}'
        'QCalendarWidget QToolButton{font-size:13px;padding:3px 6px;}')
    ye = cal.findChild(QSpinBox, 'qt_calendar_yearedit')
    if ye is not None:
        ye.setMinimumWidth(80)
    return cal


CATEGORIES = [u'生活', u'工作', u'家庭', u'亲友', u'自己']
# 事项类型：单次 / 重复。重复项必填开始日+截止日+频率；
# 编码沿用历史约定 0=单次 1每年 2每月 3每周，老数据不改。
KINDS = [u'单次事项', u'重复事项']
REPEATS = [u'每年重复', u'每月重复', u'每周重复']   # 对应 repeat 编码 1/2/3


def flat_combo_style():
    """重复频率下拉专用：单层窄边框，不给 drop-down 再画一条分隔线。

    通用 combo_style 的 ::drop-down 带 border-left + 独立背景，在浅色编辑窗
    里看着像外面又套了一层；这个下拉单独用无分隔线的扁平样式。
    """
    arrow = D.res('icons', 'nav_down.png')
    return (
        'QComboBox{background:#FFFFFF;border:1px solid #E6E7E8;border-radius:4px;'
        'padding:5px 22px 5px 8px;color:#202020;font-size:13px;}'
        'QComboBox:hover{border:1px solid #A9CDF7;}'
        'QComboBox::drop-down{width:20px;border:0;background:transparent;}'
        'QComboBox::down-arrow{image:url(%s);width:12px;height:12px;}' % arrow +
        'QComboBox QAbstractItemView{background:#FFFFFF;border:1px solid #E6E7E8;'
        'border-radius:6px;padding:4px;outline:0;}'
        'QComboBox QAbstractItemView::item{min-height:28px;padding:5px 8px;'
        'color:#202020;background:transparent;}'
        'QComboBox QAbstractItemView::item:hover{background:#EDF4FE;color:#202020;}'
        'QComboBox QAbstractItemView::item:selected{background:#DCEAFB;color:#202020;}')
# 提醒方式：下拉显示顺序 ≠ 数据库里存的编码。
# 编码是历史约定：0=不提醒 1=前一天 2=当天，老用户的数据不能动，
# 新增选项只能从 3 往后排；显示上按"由近到远"排，符合直觉。
REMIND_ITEMS = [
    (0, u'不提醒'),
    (2, u'当天提醒'),
    (1, u'前一天提醒'),
    (3, u'前两天提醒'),
    (4, u'前三天提醒'),
    (5, u'前一周提醒'),
    (6, u'前两周提醒'),
    (7, u'前一个月提醒'),
]
# remind 编码 -> 提前天数（0=当天；None=不提醒）
REMIND_LEAD = {0: None, 1: 1, 2: 0, 3: 2, 4: 3, 5: 7, 6: 14, 7: 30}


def remind_lead(code):
    """提醒编码换算成提前多少天提醒；0/未知编码一律当"不提醒"。"""
    try:
        return REMIND_LEAD.get(int(code or 0))
    except (TypeError, ValueError):
        return None
PALETTE = ['#FFFFFFFF', '#FFFF4D4D', '#FFFFA640', '#FFFFE14D', '#FF5CD65C',
           '#FF4DC4FF', '#FF7C8CFF', '#FFFF7CD6', '#FF9E9E9E', '#FF000000']


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
    """编辑待办：单次事项只填到期日；重复事项填起止日+频率。"""

    def __init__(self, store, date=None, todo=None, parent=None):
        QDialog.__init__(self, parent)
        self._store = store
        self._todo = todo
        self.setWindowTitle(u'编辑待办')
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedSize(520, 520)
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
        self.cb_type.setStyleSheet(T.combo_style())
        self.cb_type.setCursor(Qt.PointingHandCursor)
        bl.addWidget(self.cb_type, 1, 1)

        bl.addWidget(QLabel(u'文本颜色:'), 2, 0)
        self.clr = ColorPicker()
        bl.addWidget(self.clr, 2, 1)
        self.ck_italic = QCheckBox(u'斜体')
        bl.addWidget(self.ck_italic, 2, 2)
        self.ck_line = QCheckBox(u'横线')
        bl.addWidget(self.ck_line, 2, 3)

        # 第 3 行：事项类型单选（单次/重复），选中即时切换后续日期控件。
        bl.addWidget(QLabel(u'事项类型:'), 3, 0)
        self.rb_single = QRadioButton(KINDS[0])
        self.rb_repeat = QRadioButton(KINDS[1])
        self.rb_single.setChecked(True)
        for rb in (self.rb_single, self.rb_repeat):
            rb.setCursor(Qt.PointingHandCursor)
        self.kind_group = QButtonGroup(self)
        self.kind_group.addButton(self.rb_single, 0)
        self.kind_group.addButton(self.rb_repeat, 1)
        kind_box = QWidget()
        hb = QHBoxLayout(kind_box)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.setSpacing(18)
        hb.addWidget(self.rb_single)
        hb.addWidget(self.rb_repeat)
        hb.addStretch(1)
        bl.addWidget(kind_box, 3, 1, 1, 3)

        # 第 4 行：日期区。单次显示「待办日期」；重复显示「开始/截止日」。
        self.lb_date = QLabel(u'待办日期:')
        bl.addWidget(self.lb_date, 4, 0)
        self.dt = QDateEdit()
        self.dt.setCalendarPopup(True)
        self.dt.setDisplayFormat('yyyy-MM-dd')
        self.dt.setDate(QDate(date.year, date.month, date.day) if date else QDate.currentDate())
        style_date_picker(self.dt)
        bl.addWidget(self.dt, 4, 1)
        self.lb_end = QLabel(u'截止日期:')
        bl.addWidget(self.lb_end, 4, 2)
        self.dt_end = QDateEdit()
        self.dt_end.setCalendarPopup(True)
        self.dt_end.setDisplayFormat('yyyy-MM-dd')
        self.dt_end.setDate(self.dt.date().addMonths(1))
        style_date_picker(self.dt_end)
        bl.addWidget(self.dt_end, 4, 3)

        # 第 5 行：重复频率（仅重复事项可见）
        self.lb_repeat = QLabel(u'重复频率:')
        bl.addWidget(self.lb_repeat, 5, 0)
        self.cb_repeat = QComboBox()
        self.cb_repeat.addItems(REPEATS)
        self.cb_repeat.setStyleSheet(flat_combo_style())   # 单层边框，无双层视觉
        self.cb_repeat.setCursor(Qt.PointingHandCursor)
        bl.addWidget(self.cb_repeat, 5, 1)

        bl.addWidget(QLabel(u'待办提醒:'), 6, 0)
        self.cb_remind = QComboBox()
        for _code, _text in REMIND_ITEMS:
            self.cb_remind.addItem(_text, _code)
        self.cb_remind.setStyleSheet(T.combo_style())
        self.cb_remind.setMinimumWidth(150)
        self.cb_remind.setCursor(Qt.PointingHandCursor)
        bl.addWidget(self.cb_remind, 6, 1)
        bl.addWidget(QLabel(u'提醒时间:'), 6, 2)
        self.tm = TimePick()
        bl.addWidget(self.tm, 6, 3)
        self.cb_remind.currentIndexChanged.connect(self._sync_remind)
        # toggled 而非 buttonClicked：程序回填 setChecked 时也能即时联动
        self.rb_single.toggled.connect(self._sync_kind)
        self.rb_repeat.toggled.connect(self._sync_kind)
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
            rep = int(todo.get('repeat') or 0)
            (self.rb_single if rep == 0 else self.rb_repeat).setChecked(True)
            if rep > 0:
                self.cb_repeat.setCurrentIndex(max(0, min(len(REPEATS) - 1, rep - 1)))
                end_s = (todo.get('end_date') or '')[:10]
                if len(end_s) != 10 and todo.get('date'):
                    from .store import Store
                    end_s = Store.plus_month(todo['date'])
                if len(end_s) == 10:
                    y, m, d = end_s.split('-')
                    self.dt_end.setDate(QDate(int(y), int(m), int(d)))
            else:
                self.dt_end.setDate(self.dt.date().addMonths(1))
            _idx = self.cb_remind.findData(int(todo['remind'] or 0))
            self.cb_remind.setCurrentIndex(_idx if _idx >= 0 else 0)
            if todo['remind_time']:
                hh, mm = todo['remind_time'].split(':')[:2]
                self.tm.setTime(QTime(int(hh), int(mm)))
        self._sync_kind()

    def _sync_remind(self, *args):
        """选"不提醒"时把时间选择置灰，选了提醒才可调时间"""
        self.tm.setEnabled(bool(self.cb_remind.currentData()))

    def _sync_kind(self, *args):
        """按事项类型即时切换日期区：单次只留待办日期，重复显示起止日和频率。"""
        is_repeat = self.rb_repeat.isChecked()
        self.lb_date.setText(u'开始日期:' if is_repeat else u'待办日期:')
        for w in (self.lb_end, self.dt_end, self.lb_repeat, self.cb_repeat):
            w.setVisible(is_repeat)

    def _ok(self):
        if not self.ed_content.text().strip():
            DLG.info(self, APP_NAME, u'请输入待办内容')
            return
        d = self.dt.date()
        is_repeat = self.rb_repeat.isChecked()
        end_s, repeat = '', 0
        if is_repeat:
            e = self.dt_end.date()
            if e < d:
                DLG.info(self, APP_NAME, u'截止日期不能早于开始日期')
                return
            end_s = '%04d-%02d-%02d' % (e.year(), e.month(), e.day())
            repeat = self.cb_repeat.currentIndex() + 1   # REPEATS[0] = 每年 = 编码 1
        # 月末/闰日重复会在部分月份落到月末最后一天：保存时告知用户原因，
        # 同一个编辑窗实例只提示一次，避免反复点确定反复弹。
        fallback = ''
        if is_repeat and not getattr(self, '_fallback_noticed', False):
            from .store import fallback_reason
            fallback = fallback_reason(repeat, d.day(), d.month())
            if fallback:
                self._fallback_noticed = True
                DLG.info(self, APP_NAME,
                         u'你设置的重复日期会自动调整：\n\n%s\n\n'
                         u'这是正常行为，待办不会漏掉。' % fallback)
        remind = int(self.cb_remind.currentData() or 0)
        self.result_data = dict(
            content=self.ed_content.text().strip(),
            category=self.cb_type.currentText(),
            color=self.clr.color(),
            italic=1 if self.ck_italic.isChecked() else 0,
            underline=1 if self.ck_line.isChecked() else 0,
            date='%04d-%02d-%02d' % (d.year(), d.month(), d.day()),
            repeat=repeat,
            end_date=end_s,
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
        self.setFixedSize(480, 380)
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

        # 底部操作行：添加 / 编辑 / 完成 / 删除 / 关闭
        # 五个按钮固定 96px 时 400 宽的窗里会挤成一团，这里加宽窗口并按
        # 文字给每个按钮合理宽度，右侧留 stretch 把「关闭」推到最右。
        btns = QHBoxLayout()
        btns.setSpacing(8)
        add = QPushButton(u'添加待办')
        add.setFixedSize(84, 28)
        add.setStyleSheet('QPushButton{background:#2F7BFF;color:white;border-radius:4px;}'
                          'QPushButton:hover{background:#2568E0;}')
        add.clicked.connect(self._add)
        btns.addWidget(add)
        self._btn_edit = QPushButton(u'编辑')
        self._btn_edit.setFixedSize(84, 28)
        self._btn_edit.setStyleSheet(
            'QPushButton{background:#F2F4F8;color:#202020;border:1px solid #DCE1E7;'
            'border-radius:4px;}'
            'QPushButton:hover{background:#E9EEF6;border-color:#9FC5F5;}'
            'QPushButton:disabled{color:#AAB0B8;border-color:#E6E7E8;background:#F7F8FA;}')
        self._btn_edit.clicked.connect(self._edit_selected)
        btns.addWidget(self._btn_edit)
        self._btn_done = QPushButton(u'标记完成')
        self._btn_done.setFixedSize(84, 28)
        self._btn_done.setStyleSheet(
            'QPushButton{background:#F2F4F8;color:#27835B;border:1px solid #BFE4D0;'
            'border-radius:4px;}'
            'QPushButton:hover{background:#E6F5ED;border-color:#27835B;}'
            'QPushButton:disabled{color:#AAB0B8;border-color:#E6E7E8;background:#F7F8FA;}')
        self._btn_done.clicked.connect(self._toggle_done_selected)
        btns.addWidget(self._btn_done)
        self._btn_del = QPushButton(u'删除')
        self._btn_del.setFixedSize(84, 28)
        self._btn_del.setStyleSheet(
            'QPushButton{background:#F2F4F8;color:#D33A3A;border:1px solid #E3C2C2;'
            'border-radius:4px;}'
            'QPushButton:hover{background:#FBE9E9;border-color:#D33A3A;}'
            'QPushButton:disabled{color:#AAB0B8;border-color:#E6E7E8;background:#F7F8FA;}')
        self._btn_del.clicked.connect(self._delete_selected)
        btns.addWidget(self._btn_del)
        btns.addStretch(1)
        close = QPushButton(u'关闭')
        close.setFixedSize(84, 28)
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
            f.setUnderline(bool(t['underline']) or bool(t['done']))
            it.setFont(f)
            col = self._item_color(t['color'])
            if t['done']:
                col.setAlpha(150)
            it.setForeground(col)
            self.list.addItem(it)
        self._lb_head.setText(u'%s 待办（%d 项）' % (self._date.strftime('%Y-%m-%d'),
                                                  len(rows)))
        self._sync_buttons()

    def _sync_buttons(self):
        n = len(self.list.selectedItems())
        self._btn_edit.setEnabled(n == 1)
        self._btn_done.setEnabled(n >= 1)
        self._btn_del.setEnabled(n >= 1)
        self._btn_del.setText(u'删除' if n <= 1 else u'删除 (%d)' % n)
        if n == 1:
            tid = self.list.selectedItems()[0].data(Qt.UserRole)
            t = self._store.get(tid)
            self._btn_done.setText(u'取消完成' if t and t.get('done') else u'标记完成')
        else:
            self._btn_done.setText(u'标记完成' if n <= 1 else u'标记完成 (%d)' % n)

    def _set_done(self, ids, done):
        for tid in ids:
            self._store.update(tid, done=1 if done else 0)
        self.reload()

    def _toggle_done_selected(self):
        items = self.list.selectedItems()
        if not items:
            DLG.info(self, u'标记完成', u'请先选中要操作的待办。')
            return
        ids = [it.data(Qt.UserRole) for it in items]
        t = self._store.get(ids[0])
        mark = not (t and t.get('done'))
        self._set_done(ids, mark)

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
            DLG.info(self, u'编辑待办', u'请先选中一条待办。')
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
            tid = item.data(Qt.UserRole)
            t = self._store.get(tid)
            done = bool(t and t.get('done'))
            m.addAction(u'取消完成' if done else u'标记完成',
                        lambda: self._set_done([tid], not done))
            m.addAction(u'删除待办', lambda: self._delete_items([item]))
        else:
            m.addAction(u'添加待办', self._add)
        m.exec_(self.list.viewport().mapToGlobal(pos))

    def _delete_selected(self):
        items = self.list.selectedItems()
        if not items:
            # 没有选中项时给出提示，而不是静默无反应
            DLG.info(self, u'删除待办', u'请先选中要删除的待办。')
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
        # 按钮写中文的「删除 / 取消」：系统 QMessageBox 在 UOS 上给的是
        # 英文 Yes / No，还带原生标题栏装饰，跟软件自己的卡片风格不搭。
        if not DLG.confirm(self, u'删除待办', msg, ok=u'删除'):
            return
        for tid in ids:
            self._store.remove(tid)
        self.reload()
