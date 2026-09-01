# Windows 单用户安装版

本文对应第三种交付方式：普通用户从 GitHub Releases 下载 Windows x64 安装程序，安装后直接使用。该版本仅支持单用户本地使用，不包含注册、登录、邀请码或多用户数据隔离功能。

本文不说明源码依赖、Windows 开发脚本或 Docker。对应文档：

- [源码开发/测试版](source-development-testing.md)
- [多用户 Docker 部署版](docker-multi-user-deployment.md)

## 安装包内容

安装包包含：

- ResumeBranch 前后端程序和前端生产文件。
- 私有 Python 运行环境及后端依赖。
- Nginx、Poppler 和内置 Headless Chromium。
- 图形化启动器 ResumeBranch.exe。

目标电脑不需要预先安装 Python、Node.js、npm、Docker、MySQL 或 Inno Setup。安装程序不会修改系统 PATH，也不会注册系统级运行环境。

启动器由安装包一并安装，不能脱离安装目录单独分发。桌面快捷方式只是指向安装后的 ResumeBranch.exe。

## 获取与安装

普通用户应从 GitHub Releases 下载：

~~~text
ResumeBranch-Setup-v1.1.3-x64.exe
~~~

运行安装程序后：

1. 选择安装位置。
2. 按需选择创建桌面快捷方式。
3. 安装完成后按需选择立即启动。

安装程序默认使用当前用户的应用目录，不要求管理员权限。安装目录中包含完整的应用文件、私有运行环境、依赖和用户数据目录。

## 启动与停止

启动方式：

- 双击安装目录中的 ResumeBranch.exe。
- 双击安装时创建的桌面快捷方式。

启动器会启动私有单用户后端和本地页面服务，随后在默认浏览器打开：

~~~text
http://127.0.0.1:5173
~~~

服务只监听本机回环地址，不对局域网或公网开放。需要停止已启动的本地服务时，在安装目录执行：

~~~powershell
.\ResumeBranch.exe --stop
~~~

## 初始配置与数据

首次安装时，用户数据和 API 配置均为空。需要使用 AI 对话或简历解析时，再在页面的 API 设置中填写对应配置。

单用户版使用 SQLite，不需要单独启动数据库服务。主要数据位于：

~~~text
app/data/resumebranch.db
app/data/source_documents/
app/data/langgraph_checkpoints.sqlite
app/data/llm_profiles.json
app/output/resumes/
~~~

简历导出的 PDF 和 DOCX 保存在 app/output/resumes/。建议定期导出简历，并同时备份整个 app/data/ 和 app/output/resumes/ 目录。

## 卸载与重新安装

当前 Release 1.1.3 不提供在线更新器。卸载或重新安装前，请先导出需要保留的简历，并备份 app/data/ 和 app/output/resumes/。

卸载程序会停止安装包启动的后端和页面服务，并清理私有运行时文件；用户数据不会被静默覆盖。若要彻底删除用户数据，应在确认备份后手动删除安装目录中的 app/data/ 和 app/output/resumes/。

## 构建说明

安装包是维护者生成的发布文件。维护者可在 Windows x64 环境从项目根目录执行：

~~~powershell
.\packaging\build-installer.ps1
~~~

生成文件位于：

~~~text
output/installer/ResumeBranch-Setup-v1.1.3-x64.exe
~~~

构建过程和运行时来源见 [Windows 安装包构建说明](../packaging/README.md)。
