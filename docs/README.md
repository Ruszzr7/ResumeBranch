# ResumeBranch 文档

项目概览、能力边界和最快启动方式见仓库根目录的 [README](../README.md)。以下文档分别维护具体流程，避免在 README 中重复保存容易过期的细节。

## 三种交付方式

- [源码开发/测试版](source-development-testing.md)：从 GitHub 获取源码，通过 Windows 脚本测试单用户和多用户配置。
- [多用户 Docker 部署版](docker-multi-user-deployment.md)：从源码和 Docker Compose 运行多用户版本，用于本地部署验收或服务器部署。
- [Windows 单用户安装版](windows-single-user-installation.md)：从 GitHub Releases 下载安装程序，直接安装并运行单用户版本。

安装包的构建细节见 [Windows 安装包构建说明](../packaging/README.md)。

## 开发与验收

- [测试与验收](testing.md)：自动化命令、人工回归清单和专项测试前置条件。
- [Agent 架构与状态边界](agent-architecture.md)：Release 1 的实际路由、技能、上下文、确认与并发机制。

如文档与代码不一致，以当前代码、`.env*.example`、启动脚本和运行时 OpenAPI 为准，并应同步修正文档。
