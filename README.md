# 桌面悬浮日历

一个面向 **UOS / 飞腾 D3000（aarch64）** 的原生桌面日历：半透明悬浮在桌面上，带农历、法定节假日、待办与提醒，无登录、无会员、无联网请求。

- 语言：Python 3 + PyQt5
- 架构：aarch64（LoongArch / x86 只需重新打包，代码无架构相关分支）
- 许可：MIT
- 当前版本：**1.3.3.0**

![主界面](screenshots/main.png)

---

## 功能

### 日历
- 月视图 / 周视图一键切换；滚轮上翻上月、下翻下月
- 农历日期、二十四节气、传统节日与法定节日名
- 法定节假日与调休上班日自动区分（休息日高亮，调休上班日单独标记）
- 今日格整格高亮；选中格同样整格填充；点击格子时格内文字不会位移
- 鼠标滚轮、上下月按钮、今日按钮三种导航

### 待办与提醒
- 待办支持标题、颜色标记、完成状态、所属日期
- 待办清单内可新增、编辑、批量删除（Ctrl / Shift 多选），操作后停留在清单而不是跳回主界面
- 日期格子内**逐条列出**当天待办：空间不足时自动逐级缩小字号，尽量全部显示，而不是折叠成"共 N 项"
- 提醒时间用仿 iOS 的滚轮时间盘选择，精确到分钟
- 提醒可设为当天或提前一天触发，弹窗跟随当前主题配色；同一条待办同一天只弹一次
- 待办数据存本地 SQLite，配置文件为 INI，程序目录之外不留垃圾

### 外观
- 8 套内置原创主题，设置页每张主题卡用该主题自身配色实时绘制迷你月历预览（不依赖预览图片）
- 所有前景色均可自定义：背景、网格、星期标题栏边框、今日格、内/外边框、各类字体颜色
- 透明度滑杆（UOS 风格引擎不渲染 `QSlider::sub-page`，故为自绘控件）
- 字体大小可调，格子内待办行高按字体真实度量计算，调大字号也不会被裁切
- 自制 Photoshop 风格取色盘：SV 取色区 + 色相条 + RGB/HSV/十六进制输入 + 色板 + 屏幕取色
- 图标、月份文字、悬停色随主题明暗自动反色

### 窗口行为
- **锁定**：窗口紧贴桌面，加 `_NET_WM_STATE_BELOW`，**任何情况下都不会盖到其他软件前面**，且不可移动
- **解锁**：恢复普通层级，可自由拖动
- 锁定/解锁通过 X11 直接改窗口状态（ctypes 直连 libX11），不重建窗口，因此**不会闪一下**
- 不出现在任务栏与分页器（`SKIP_TASKBAR` / `SKIP_PAGER`），只在托盘留一个图标
- 托盘图标单击 = 显示主界面（不会来回切换隐藏）；动画效果已去掉
- 首次启动按屏幕分辨率等比确定窗口位置和大小；之后记住用户自己调整的结果，只要不卸载重装就按用户设定显示

### 系统集成
- 安装后询问是否立即运行、是否设为开机自动启动（60 秒无操作自动跳过，静默安装不卡流程）
- 安装后自动在用户桌面创建快捷方式
- `deb` 遵循 UOS 应用规范，安装到 `/opt/apps/com.desktop.calendar/`

---

## 目录结构

```
.
├── brl/                    主程序包
│   ├── __main__.py         入口（含 --set-autostart / --make-desktop-icon 维护参数）
│   ├── appctx.py           应用上下文、托盘、自启动、桌面图标
│   ├── mainwin.py          主窗口：布局、主题应用、提醒检查、锁定
│   ├── caltable.py         日历表格绘制（格子、待办、节日）
│   ├── settings.py         选项设置对话框
│   ├── colorpick.py        自制取色盘
│   ├── timepick.py         仿 iOS 滚轮时间选择
│   ├── todo.py             待办清单与编辑对话框
│   ├── theme.py            主题表与绘制工具
│   ├── lunar.py            农历 / 节气计算（纯 Python，1900-2099）
│   ├── holidays.py         法定节假日与调休数据（依据国务院办公厅年度安排整理）
│   ├── data.py  store.py  defaults.py  x11fix.py
│   └── resources/icons/    自制扁平图标（17 个）
├── makedeb.py              打包脚本：生成 aarch64 deb
├── verify7..verify18.py    回归验证脚本
├── selftest.py             数据与自检
├── e2e_autostart.py        自启动端到端测试
├── lint_aliases.py         别名/命名一致性检查
├── brltest_env.py          测试用 XDG 隔离（防止测试污染真实配置）
└── screenshots/            文档截图
```

---

## 依赖

- Python 3（UOS 20 自带 3.7 即可）
- PyQt5（`python3-pyqt5`）
- 打包需要：`dpkg-deb`、`fakeroot`

程序**没有任何网络请求**，也不使用除 Qt 之外的第三方库。

---

## 构建

```bash
cd <本目录>
python3 makedeb.py
```

产物在 `dist/desktop-calendar_<版本>_arm64.deb`。

> 打包脚本使用持久化的 `dist/stage` 暂存目录。如果删除过源码里的资源文件，请先 `rm -rf dist/stage` 再打包，否则旧文件会混进新包。

版本号与软件名的唯一定义处是 `brl/__init__.py` 的 `__version__` / `APP_NAME`；`makedeb.py` 中的 `VER` 需与之保持一致（有验证脚本守护）。

---

## 安装

```bash
sudo dpkg -i desktop-calendar_1.3.3.0_arm64.deb
```

安装过程中会弹出两次询问（是否开机自启、是否立即运行），可用图形界面点选，也可直接关闭跳过。

卸载：

```bash
sudo dpkg -r desktop-calendar
```

手动创建的桌面快捷方式需自行删除（卸载脚本不会动用户桌面）。

---

## 配置与数据位置

| 内容 | 路径 |
|---|---|
| 配置 | `~/.config/desktop-calendar/calendar.ini` |
| 待办数据 / 日志 | `~/.local/share/desktop-calendar/` |
| 开机自启 | `~/.config/autostart/com.desktop.calendar.desktop` |
| 安装位置 | `/opt/apps/com.desktop.calendar/` |

---

## 开发：验证

改动后请跑全量回归（用系统自带的 `python3` 即可）：

```bash
for f in verify7 verify8 verify9 verify11 verify12 verify13 verify14 \
         verify15 verify16 verify17 verify18; do python3 $f.py; done
python3 selftest.py
python3 e2e_autostart.py
python3 lint_aliases.py
```

合计 300 余项断言，覆盖界面、待办、提醒、主题、取色、打包、安装脚本、X11 窗口行为等。

各脚本职责：

| 脚本 | 覆盖内容 |
|---|---|
| verify7 | 界面基础结构与控件 |
| verify8 | 中文化、自启动配置文件读写 |
| verify9 | 生成 deb 的包内结构与内容 |
| verify11 | 日历格子与待办绘制 |
| verify12 | 待办清单交互 |
| verify13 | 透明度滑杆与工具图标 |
| verify14 | 提醒逻辑与今日格 |
| verify15 | 选中格、时间框、默认值、提醒方向、屏幕自适应 |
| verify16 | 时间盘与提醒弹窗 |
| verify17 | 安装流程、改名、桌面图标、版本一致性 |
| verify18 | 取色盘、锁定贴底、任务栏隐藏、托盘行为 |
| selftest | 农历/节假日/主题/存储等数据层自检 |
| e2e_autostart | 开机自启端到端 |

所有测试通过 `brltest_env.py` 做 XDG 目录隔离，**不会读写用户真实配置**。

> 提示：受限环境下 `rm` / `os.remove` 可能被安全策略改写成"移入回收站"，导致自启动相关测试出现假失败；测试目录应放在 `/tmp` 而非 `/home` 下。

---

## 合规说明

本项目为**独立编写的实现**，不含任何第三方软件的图片、皮肤、配色表或数据库等素材：

- 图标为自制扁平图标，形状参考 [Bootstrap Icons](https://icons.getbootstrap.com/)（MIT License）并自行绘制
- 农历数据表为公开的农历编码表整理，算法为纯 Python 实现
- 法定节假日与调休数据依据国务院办公厅公布的年度放假安排手工整理
- 主题配色为原创设计，界面预览由代码实时绘制

---

## 许可证

[MIT](LICENSE)
