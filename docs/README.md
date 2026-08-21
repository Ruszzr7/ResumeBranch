# ResumeBranch 文档

项目概览、能力边界和最快启动方式见仓库根目录的 [README](../README.md)。以下文档分别维护具体流程，避免在 README 中重复保存容易过期的细节。

## 部署与运行

- [Windows 本地部署](local-deployment.md)：默认个人模式，SQLite、数据备份、导出与验活。
- [Windows 本机多用户部署](multi-user-local.md)：使用本机 MySQL 测试登录、邀请码和用户隔离。
- [Docker 多人自托管部署](deployment.md)：Linux/服务器 Compose 拓扑、配置、备份与安全边界。

## 开发与验收

- [测试与验收](testing.md)：自动化命令、人工回归清单和专项测试前置条件。
- [Agent 架构与状态边界](agent-architecture.md)：Release 1 的实际路由、技能、上下文、确认与并发机制。

如文档与代码不一致，以当前代码、`.env*.example`、启动脚本和运行时 OpenAPI 为准，并应同步修正文档。
