# 桌面悬浮日历

一个面向 **UOS / 飞腾 D3000（aarch64）** 的原生桌面日历：半透明悬浮在桌面上，带农历、法定节假日、待办与提醒。无登录、无会员、无广告；唯一的联网行为是**检查更新**（默认每天一次，可在设置里关掉）。

- 语言：Python 3 + PyQt5
- 架构：aarch64（LoongArch / x86 只需重新打包，代码无架构相关分支）
- 许可：MIT
- 当前版本：**1.4.3.0**
- 仓库：[GitHub](https://github.com/JiangZY5959/desktop-calendar) ｜ 国内镜像 [GitCode](https://gitcode.com/gcw_6ciOFeue/desktop-calendar)（**两处同步更新**，GitHub Release 附件下载更方便）

![主界面](screenshots/main.png)

## 下载

| 来源 | 安装包 | 平台 |
|---|---|---|
| GitHub Release（推荐，永久地址） | [desktop-calendar_1.4.3.0_arm64.deb](https://github.com/JiangZY5959/desktop-calendar/releases/download/v1.4.3.0/desktop-calendar_1.4.3.0_arm64.deb) | UOS / 飞腾 aarch64 |
| GitCode 直链（国内） | [desktop-calendar_1.4.3.0_arm64.deb](https://raw.gitcode.com/gcw_6ciOFeue/desktop-calendar/blobs/bddd24462c83fa9833002f02cccef347bce29764/releases/desktop-calendar_1.4.3.0_arm64.deb) | UOS / 飞腾 aarch64 |

也可以在 GitHub 的 [Releases 页面](https://github.com/JiangZY5959/desktop-calendar/releases) 直接点附件下载。

安装包同时放在仓库的 [`releases/`](releases/) 目录中，可在网页端点开目录后右上角直接下载。已安装旧版的用户不必手动下载：**软件会自己检查更新并安装**（见下文）。

命令行下载（二选一）：

```bash
# GitHub
wget -O desktop-calendar.deb \
  https://github.com/JiangZY5959/desktop-calendar/releases/download/v1.4.3.0/desktop-calendar_1.4.3.0_arm64.deb
sudo dpkg -i desktop-calendar.deb

# 或 GitCode（国内更快）
wget -O desktop-calendar.deb \
  https://raw.gitcode.com/gcw_6ciOFeue/desktop-calendar/blobs/bddd24462c83fa9833002f02cccef347bce29764/releases/desktop-calendar_1.4.3.0_arm64.deb
sudo dpkg -i desktop-calendar.deb
```

> GitCode 不支持 `raw/分支/路径` 这种直链，只能用 `raw.gitcode.com/<owner>/<repo>/blobs/<文件 blob sha>/<路径>`；文件一改 sha 就变，所以每个版本的地址都不同。因此**推荐用上面的 GitHub 永久地址**。机器可读的版本清单在 [`releases/latest.json`](releases/latest.json)（构建时由 `make_manifest.py` 生成，含 sha256 与直链），软件的检查更新就读它。

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
- 安装后弹出**一个**询问窗口，一次勾选「开机自动启动」与「立即运行」（60 秒无操作自动按"稍后"处理）
- 询问窗口用软件自带的界面实现，**不依赖 zenity**（很多 UOS 机器没装它，依赖就会"装完什么都不弹"）；实在弹不出来时退回 zenity / 终端提问
- 无人值守安装（apt 静默、升级覆盖）不打扰；升级时也不再重复询问
- 安装时实在没问成的（比如终端里装、无图形环境），**首次运行软件时会补问一次**是否开机自启
- 安装后自动在用户桌面创建快捷方式
- `deb` 遵循 UOS 应用规范，安装到 `/opt/apps/com.desktop.calendar/`

### 升级与数据安全
- **升级时保留待办与设置**：升级前自动备份待办库与设置（root 安装放 `/var/backups/desktop-calendar`，否则在家目录 `~/.desktop-calendar-backup`，保留最近 5 份）；装完发现文件缺失或为空会自动补回来
- **卸载、甚至彻底清除（purge）都不动用户数据**——重装或升级回来，待办和设置原样还在
- **装完自动"关旧开新"**：升级脚本先请正在运行的旧版本**保存退出**（窗口位置、设置先落盘），等它真正退出后再把新版本拉起来；绝不会新旧两个进程同时读写同一份数据
- **单实例接管**：手动再开一个日历时，也会先请旧实例退出，始终只有一个在跑
- 进程识别按"进程名 + 启动参数"精确匹配，正在装包的 dpkg、终端里的 shell 不会被误伤

### 检查更新
- 数据源是 **GitCode 公开仓库里的版本清单**（也可在上方的 GitHub Release 页面手动下载），**只读公开数据，不需要账号或令牌**
- GitHub 与 GitCode 两处同时发布，内容完全一致；软件内置的主数据源是 GitCode 清单（国内访问更快），GitHub 作为手动下载的镜像
- 频率**默认每天检查一次**，设置里可改为每周 / 每月 / 仅手动；选「仅手动」后平时零联网
- 选项设置里有与「基础设置」「背景设置」同级的**独立「检查更新」页签**：看频率、看上次检查时间、点「立即检查」（项目主页入口在「关于」里）
- 发现新版本时弹出提示，附更新说明，可选 **立即更新 / 稍后再说 / 跳过此版本**（跳过只针对这一个版本，下个版本照常提示）
- 后台静默检查不打扰：没新版本、查不到（断网等）都只是安静记一条日志
- 点「立即更新」后**自动下载安装包**：自绘进度条、可取消，下载完校验体积、deb 包头与 sha256
- 校验通过后调用系统安装器安装：优先 UOS 自带的 `deepin-deb-installer`，其次 `pkexec apt-get` / `dpkg`
- **装好后日历自动换成新版本**：先关旧进程再打开新版，不需要手动重启
- 命令行也能自检：`desktop-calendar --check-update`

---

## 目录结构

```
.
├── brl/                    主程序包
│   ├── __main__.py         入口（含 --quit / --backup / --ensure 等维护参数）
│   ├── appctx.py           应用上下文、托盘、自启动、桌面图标、信号优雅退出
│   ├── appdata.py          升级数据保护：实例登记、备份恢复、旧路径迁移
│   ├── mainwin.py          主窗口：布局、主题应用、提醒检查、锁定
│   ├── caltable.py         日历表格绘制（格子、待办、节日）
│   ├── settings.py         选项设置对话框（基础 / 背景 / 检查更新）
│   ├── update.py           检查更新：版本比较、清单拉取、下载校验、调用安装器
│   ├── updatedlg.py        更新相关界面：提示、下载进度、忙碌弹层
│   ├── colorpick.py        自制取色盘
│   ├── timepick.py         仿 iOS 滚轮时间选择
│   ├── todo.py             待办清单与编辑对话框
│   ├── theme.py            主题表与绘制工具
│   ├── lunar.py            农历 / 节气计算（纯 Python，1900-2099）
│   ├── holidays.py         法定节假日与调休数据（依据国务院办公厅年度安排整理）
│   ├── data.py  store.py  defaults.py  x11fix.py
│   └── resources/icons/    自制扁平图标（17 个）
├── makedeb.py              打包脚本：生成 aarch64 deb（含升级收尾脚本 desktop-calendar-upgrade）
├── make_manifest.py        生成 releases/latest.json 版本清单（含 sha256 与 blob 直链）
├── verify.py               全量回归验证（按功能分节的单文件套件）
├── brltest_env.py          测试用 XDG 隔离（防止测试污染真实配置）
└── screenshots/            文档截图
```

---

## 依赖

- Python 3（UOS 20 自带 3.7 即可）
- PyQt5（`python3-pyqt5`）
- 打包需要：`dpkg-deb`、`fakeroot`

程序不使用除 Qt 之外的第三方库；联网只用 Python 标准库（`urllib`），只为检查更新，且可关闭。

---

## 构建

```bash
cd <本目录>
python3 makedeb.py            # 生成 deb
python3 make_manifest.py      # 生成 releases/latest.json（版本清单）
```

产物在 `dist/desktop-calendar_<版本>_arm64.deb`。发布顺序：先把 deb 放到 `releases/`，再跑 `make_manifest.py`，然后把 deb、清单、README、CHANGELOG 一起提交——清单里的下载直链依赖 deb 的 blob sha，三者必须同一次提交。

> 打包脚本使用持久化的 `dist/stage` 暂存目录。如果删除过源码里的资源文件，请先 `rm -rf dist/stage` 再打包，否则旧文件会混进新包。

版本号与软件名的唯一定义处是 `brl/__init__.py` 的 `__version__` / `APP_NAME`；`makedeb.py` 中的 `VER` 需与之保持一致（有验证脚本守护）。

---

## 安装

```bash
sudo dpkg -i desktop-calendar_1.4.3.0_arm64.deb
```

首次安装会弹出**一个**询问窗口（是否开机自启、是否立即运行）；**升级覆盖安装不询问**，并自动完成：备份用户数据 → 请旧版本保存退出 → 补齐缺失的数据 → 打开新版本。

卸载：

```bash
sudo dpkg -r desktop-calendar
```

卸载不影响待办与设置；彻底清除（`purge`）也只清掉系统级的升级备份，用户数据仍保留。

---

## 配置与数据位置

| 内容 | 路径 |
|---|---|
| 配置 | `~/.config/desktop-calendar/calendar.ini` |
| 待办数据 / 日志 | `~/.local/share/desktop-calendar/` |
| 升级备份 | `/var/backups/desktop-calendar/`（无权限时在 `~/.desktop-calendar-backup/`） |
| 更新缓存（下载的安装包） | `~/.local/share/desktop-calendar/updates/` |
| 开机自启 | `~/.config/autostart/com.desktop.calendar.desktop` |
| 安装位置 | `/opt/apps/com.desktop.calendar/` |

---

## 开发：验证

回归验证已融合为单文件 `verify.py`，按功能分节（原 verify7~19、selftest、e2e、lint 共 16 个脚本全部并入）：

```bash
python3 verify.py              # 跑全部分节（每节独立子进程，互不污染）
python3 verify.py v19          # 只跑某一节
python3 verify.py v7 v19 lint  # 只跑指定的几节
python3 verify.py --list       # 列出分节
```

合计 400 余项断言，覆盖界面、待办、提醒、主题、取色、更新、打包、安装脚本、X11 窗口行为等。

各分节职责：

| 分节 | 覆盖内容 |
|---|---|
| v7 | 界面基础结构与控件 |
| v8 | 中文化、自启动配置文件读写 |
| v9 | 生成 deb 的包内结构与内容 |
| v11 | 日历格子与待办绘制 |
| v12 | 待办清单交互 |
| v13 | 透明度滑杆与工具图标 |
| v14 | 提醒逻辑与今日格 |
| v15 | 选中格、时间框、默认值、提醒方向、屏幕自适应 |
| v16 | 时间盘与提醒弹窗 |
| v17 | 安装流程、改名、桌面图标、版本一致性 |
| v18 | 取色盘、锁定贴底、任务栏隐藏、托盘行为（需真桌面 X11） |
| v19 | 检查更新：版本比较、频率、清单解析、下载校验、安装调用、设置页签 |
| v20 | 升级保护：备份恢复、旧路径迁移、进程识别、关旧开新端到端 |
| v21 | 询问时机、配置键迁移、齿轮菜单、关于窗口 |
| data | 农历/节假日/主题/存储等数据层自检 |
| e2e | 开机自启端到端 |
| lint | 别名/命名一致性 |

所有测试通过 `brltest_env.py` 做 XDG 目录隔离，**不会读写用户真实配置**。

> 提示：v18 断言真实 X11 窗口状态，须在真桌面下跑（有 `DISPLAY` 时自动用 xcb）；离屏环境会假失败。受限环境下 `rm` / `os.remove` 可能被安全策略改写成"移入回收站"，导致自启动相关测试出现假失败；测试目录应放在 `/tmp` 而非 `/home` 下。

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
