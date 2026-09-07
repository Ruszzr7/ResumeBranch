# ResumeBranch Agent 核心评测总集

`cases.json` 是唯一保留的 700 条统一评测数据：路由 200 条、Skill 选择 400 条（含新增 100 条教练 Skill 案例）、修改安全 100 条。数据由基础合并集、v3-hard、v4-hard 和教练专项案例汇总而成；各案例 ID 在总集内唯一，提示词不重复。旧版本目录已清理。

总集独立运行器、指标模块和数据审查位于本目录；审查脚本从总集内的 `v4-` ID 自包含提取困难集，不依赖旧版本目录。离线评测命令：

```powershell
.\\.venv-win\\Scripts\\python.exe tests\\agent_core_eval\\total\\run_eval.py --mode offline
```

新增数据审查命令：

```powershell
.\.venv-win\Scripts\python.exe tests\agent_core_eval\total\audit_dataset.py
```

该命令只执行结构、契约、路由和安全离线检查，不调用真实模型 API；结果写入 `audit.md`。

400 条 Skill 案例均以 `conversation_llm` 为入口，评估模型对修改 Skill、快照 Skill、教练 Skill 和 No-tool 的自主选择。三个 Skill 分别按调用与否计算 Precision、Recall，并记录完整 TP/FP/FN/TN。确定性 `direct_edit` 入口继续由 200 条路由案例及现有后端测试覆盖，不在 Skill 集内单独统计。定向复测命令：

```powershell
.\.venv-win\Scripts\python.exe tests\agent_core_eval\total\run_eval.py --mode online --case-ids skill-003,skill-009
```

需要照片视觉证据的案例在 `cases.json` 中标记 `fixture: "photo"`，运行器只为这些案例注入本地生成的中性照片；默认无照片夹具保持不变。主报告突出路由准确率、三个 Skill 的 Precision/Recall 和最终修改结果准确率；操作 JSON 严格匹配仅保留为诊断信息。
