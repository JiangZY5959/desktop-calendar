# -*- coding: utf-8 -*-
"""第十二轮验证（1.2.7.2）

① 待办提醒可用：提醒下拉可选、选"不提醒"时时间置灰、选项/下拉箭头样式统一
② 选中后可编辑；添加/编辑确定后**留在清单**（不再跳回主界面）
③ 支持多选批量删除
"""
import os
import sys
import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
# 测试隔离：配置/数据全部落到临时目录，绝不碰用户真实配置
import brltest_env as _ENV
_ENV.isolate('v12')

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtCore import Qt, QTime
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

app = QApplication(sys.argv)

from brl import store, todo

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
src = open(os.path.join(HERE, 'brl', 'todo.py')).read()
tsrc = open(os.path.join(HERE, 'brl', 'timepick.py')).read()
d0 = datetime.date.today()

print('== ① 提醒可用 / 时间可选')
ck('有可点的时间选择器 TimePick', 'class TimePick' in tsrc)
ck('iPhone 式滚轮控件', 'class TimeWheel' in tsrc and 'def wheelEvent' in tsrc)
ck('悬浮式时间盘 TimePopup', 'class TimePopup' in tsrc and 'Qt.Popup' in tsrc)
ck('滚轮全部自绘（不依赖系统风格）',
   'def paintEvent' in tsrc and 'QComboBox' not in tsrc)
ck('不再使用只能键盘调的 QTimeEdit 控件', 'self.tm = QTimeEdit()' not in src)
ck('提醒文案精简', u"REMINDS = [u'不提醒', u'前一天提醒', u'当天提醒']" in src)
ck('下拉框自绘箭头', 'down-arrow{image:url(' in src)
ck('箭头图标存在', os.path.exists(os.path.join(HERE, 'brl', 'resources', 'icons',
                                            'nav_down.png')))

ed = todo.TodoEditDialog(S, d0, None, None)
ed.show()
app.processEvents()
ck('默认"不提醒"时时间置灰', not ed.tm.isEnabled())
ed.cb_remind.setCurrentIndex(2)
app.processEvents()
ck('选"当天提醒"后时间可选', ed.tm.isEnabled())
ed.tm.setTime(QTime(7, 30))
app.processEvents()
ck('时间能改为 07:30', ed.tm.text() == '07:30', ed.tm.text())
ed.tm.setTime(QTime(21, 45))
app.processEvents()
ck('时间能改到 21:45（分钟不受 5 分钟档限制）', ed.tm.text() == '21:45',
   ed.tm.text())
ed.ed_content.setText(u'__提醒验证__')
ed._ok()
ck('确定后带回 remind/remind_time',
   ed.result_data['remind'] == 2 and ed.result_data['remind_time'] == '21:45',
   str(ed.result_data['remind_time']))
ck('时间下拉框有最小宽度(不被挤没)', ed.tm.width() >= ed.tm.minimumWidth(),
   '%d/%d' % (ed.tm.width(), ed.tm.minimumWidth()))
ed.grab().save(os.path.join(HERE, 'v17_todoedit.png'))

print('== ② 选中可编辑 / 确定后留在清单')
ck('清单有"编辑待办"按钮', u'_btn_edit = QPushButton(u\'编辑待办\')' in src)
ck('_add 不再 accept 关闭清单', 'self._store.add(**dlg.result_data)\n            self.reload()' in src)
ck('_edit 不再 accept 关闭清单', 'self._store.update(tid, **dlg.result_data)\n            self.reload()' in src)
ck('有"关闭"按钮回到主界面', u"close = QPushButton(u'关闭')" in src)

tid0 = S.add(u'__第十二轮__', date=d0.isoformat())
dlg = todo.TodoListDialog(S, d0, None)
dlg.show()
app.processEvents()

real_exec = todo.TodoEditDialog.exec_
def fake_exec(self, *a, **k):
    self.ed_content.setText(u'__新增验证__')
    self.cb_remind.setCurrentIndex(1)
    self.tm.setTime(QTime(8, 15))
    self._ok()
    return QDialog.Accepted
todo.TodoEditDialog.exec_ = fake_exec
dlg._add()
app.processEvents()
todo.TodoEditDialog.exec_ = real_exec
ck('添加后清单仍打开', dlg.isVisible())
ck('添加后清单已刷新出新条目',
   any(u'__新增验证__' in dlg.list.item(i).text() for i in range(dlg.list.count())))
new_id = [S.for_date(d0)[i]['id'] for i in range(len(S.for_date(d0)))
          if S.for_date(d0)[i]['content'] == u'__新增验证__']
ck('新增条目已落库', len(new_id) == 1)
if new_id:
    ck('提醒时间按所选落库(08:15)', S.get(new_id[0])['remind_time'] == '08:15',
       S.get(new_id[0])['remind_time'])
ck('新增后自动选中该条',
   dlg.list.currentItem() is not None and
   dlg.list.currentItem().data(Qt.UserRole) == (new_id[0] if new_id else None))

# 编辑：选中一条 → 编辑按钮可用 → 改内容后仍在清单
dlg.list.setCurrentRow(0)
app.processEvents()
ck('选中后编辑按钮可用', dlg._btn_edit.isEnabled())
item0 = dlg.list.currentItem()
tid0_check = item0.data(Qt.UserRole)
def fake_exec2(self, *a, **k):
    self.ed_content.setText(u'__已编辑__')
    self._ok()
    return QDialog.Accepted
todo.TodoEditDialog.exec_ = fake_exec2
dlg._edit(item0)
app.processEvents()
todo.TodoEditDialog.exec_ = real_exec
ck('编辑后清单仍打开', dlg.isVisible())
ck('编辑内容已生效', (S.get(tid0_check) or {}).get('content') == u'__已编辑__',
   (S.get(tid0_check) or {}).get('content'))
ck('编辑后条目仍被选中',
   dlg.list.currentItem() is not None and
   dlg.list.currentItem().data(Qt.UserRole) == tid0_check)

print('== ③ 多选批量删除')
ck('列表支持多选', 'QAbstractItemView.ExtendedSelection' in src)
ids = [S.add(u'__批量删除%d__' % i, date=d0.isoformat()) for i in range(3)]
dlg.reload()
app.processEvents()
picked = []
for i in range(dlg.list.count()):
    it = dlg.list.item(i)
    if it.data(Qt.UserRole) in ids:
        it.setSelected(True)
        picked.append(it)
app.processEvents()
ck('已选中 3 条', len(dlg.list.selectedItems()) == 3,
   str(len(dlg.list.selectedItems())))
ck('删除按钮显示所选数量', u'删除所选' in dlg._btn_del.text(), dlg._btn_del.text())

real_q = QMessageBox.question
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
dlg._delete_selected()
QMessageBox.question = real_q
app.processEvents()
left = [S.get(i) for i in ids]
ck('3 条全部从库中删除', all(x is None for x in left))
ck('批量删除后清单仍打开', dlg.isVisible())
ck('清单里不再显示被删条目',
   all(dlg.list.item(i).data(Qt.UserRole) not in ids for i in range(dlg.list.count())))

dlg.list.clearSelection()
app.processEvents()
ck('无选中时删除按钮置灰', not dlg._btn_del.isEnabled())
dlg.grab().save(os.path.join(HERE, 'v17_todolist.png'))

# 清理
for i in [tid0, tid0_check] + (new_id or []):
    if i:
        S.remove(i)
dlg.deleteLater()

print('\n结果: PASS=%d FAIL=%d' % (npass, nfail))
sys.exit(1 if nfail else 0)
