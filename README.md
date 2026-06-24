# 金十快讯监控工具

一个用于监控金十数据快讯的 Windows 桌面工具。程序会实时拉取快讯内容，在界面中展示最新消息，并支持关键词过滤、弹窗提醒、系统托盘运行和钉钉 Webhook 推送。

## 功能特点

- 实时监控金十快讯，自动刷新最新消息
- 支持关键词监控，命中任意关键词即可标记和筛选
- 支持桌面弹窗提醒和提示音
- 支持最小化到系统托盘，后台持续运行
- 支持复制、导出 TXT、导出 CSV、导出日志
- 支持钉钉机器人 Webhook 推送
- 内置简单规则分析，用于标记影响级别、方向和相关品种
- 支持 PyInstaller 打包为 Windows 可执行程序

## 运行环境

- Windows
- Python 3.11 或更高版本

## 安装依赖

建议先创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 启动程序

```powershell
python main.py
```

程序启动后会自动开始监控。关闭窗口时，程序默认会最小化到系统托盘并继续后台运行；如需彻底退出，可通过托盘菜单选择退出。

## 关键词监控

在界面底部的“关键词”输入框中填写关键词，支持以下分隔方式：

- 中文逗号
- 英文逗号
- 空格
- 换行

开启“启用关键词过滤”后，列表中只显示命中关键词的快讯。未开启过滤时，全部快讯仍会显示，但命中的关键词会在快讯卡片中标出。

## 钉钉推送

在“Webhook”输入框中填写钉钉机器人的 Webhook 地址，保存后开启推送即可。

Webhook 属于敏感配置，只会保存在当前 Windows 用户的本地数据目录中，不应放入下载包、仓库或发布附件。

## 打包为 EXE

项目提供了 Windows 打包脚本：

```powershell
.\build.bat
```

脚本会自动创建虚拟环境、安装依赖，并通过 PyInstaller 打包。打包完成后，输出目录为：

```text
dist\Jin10FlashMonitor
```

## 本地数据

程序会在当前 Windows 用户的数据目录中保存配置、日志和导出文件，默认位置为：

```text
%LOCALAPPDATA%\Jin10FlashMonitor
```

主要包括：

- 关键词配置
- Webhook 配置
- 已发送消息缓存
- 运行日志
- 导出的 TXT / CSV 文件

构建产物、虚拟环境和本地配置不会提交到仓库中。发布前请使用 `build.bat` 重新打包；脚本会清理旧构建中的本地配置，并检查输出目录中是否误带 `settings.json`、钉钉 Webhook 或相关敏感字段。

## 项目结构

```text
main.py                  程序入口
ui.py                    桌面界面、托盘、弹窗和用户交互
monitor.py               监控循环和事件分发
scraper.py               金十快讯抓取与解析
news_analyzer.py         快讯规则分析
notifier.py              钉钉 Webhook 通知
config.py                本地配置读写
models.py                数据模型
logger.py                日志和数据目录
deduper.py               快讯去重
build.bat                Windows 打包脚本
jin10_flash_monitor.spec PyInstaller 配置
```

## 说明

本项目仅用于学习和个人效率工具场景。请合理控制请求频率，并遵守目标网站和相关服务的使用规则。
