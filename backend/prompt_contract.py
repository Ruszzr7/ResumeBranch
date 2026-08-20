"""Stable, user-grounded contracts shared by conversation and proposal prompts."""

from __future__ import annotations

import json
from typing import Any

from .layout_config import normalize_layout_config
from .layout_capabilities import build_layout_context_text


CONTENT_STRUCTURE_GUIDANCE = """
【经历内容结构契约】
1. 工作经历和项目经历的 content_blocks 只允许三种语义角色：introduction（项目简介）、responsibilities（项目职责）、generic（普通内容），不能创建其他内容类型或任意自定义标题。只有原文明确出现“项目简介/项目背景/项目概述/项目说明”或“项目职责/主要职责/个人职责/负责内容”等语义标题时，才填写对应 label；generic 的 label 必须为空。
2. 三种角色的默认展示形式固定为：项目简介用段落，项目职责用编号，普通内容用分点。仅当原文明确使用另一种段落/分点/编号形式时才保留原形式；列表条目只保存正文，不重复写序号或圆点，标题为空表示保留内容但不显示标题。
3. 项目简介和项目职责的语义标题在渲染时与内容同级、各有一个分点；项目职责标题下的多条内容使用编号，普通内容与两者保持同级并使用分点。位于分点内部的局部粗体前缀必须留在同一个正文条目中，不能提升为 label 或新内容块。
4. 【内容块边界与分类顺序】先按原文视觉结构划分候选内容组：栏目标题、段落/分点/编号、缩进、对齐、空行和连续性共同确定边界；视觉边界优先于语义猜测。项目简介标题及其正文属于 introduction；只有项目简介正文结束后的后续内容才进入职责候选区。此后的连续内容默认属于 responsibilities，先采用第一个连续视觉组作为职责组；只有后续内容出现明确不同的视觉组（例如缩进层级、分点位置或编号/分点结构发生清晰变化）时，才另建 generic。若整个经历没有任何明确的项目简介/项目职责标题，全部内容归入 generic，不根据语义自行补造 introduction 或 responsibilities。
5. 【解析阶段视觉证据】在每个 content_block 中填写 source_layout_group、source_indent_level、source_marker_type 三个解析辅助字段，用来表示原文中连续的视觉组；同一视觉组的内容必须使用相同的 source_layout_group。视觉组发生变化时必须拆成新的 content_block。它们只供后处理分类使用，最终不会保存或显示。不要因为某个词、句子含义或“看起来像职责”就拆组；无法确认视觉边界时保持在当前职责组。
6. 【结构示例】如果项目简介正文之后有四个分点，其中前三个缩进和分点位置一致，第四个明显没有缩进，则前三个归 responsibilities，第四个归 generic；判断依据是视觉组差异，而不是“第四条”这一位置本身。项目职责默认使用编号，普通内容默认使用分点。
7. 【内容完整性】项目简介正文之后的内容先按上述规则归入项目职责，不因单个词语或句子含义擅自拆分；出现新的明确标题或清晰的视觉边界时再结束当前组并建立下一个 generic 或语义组。所有可见内容必须原样进入某个 content_blocks 且只能出现一次，不能省略；无法确定边界时保留为当前职责组。
8. 教育经历栏目下、下一个顶层栏目之前的无标题分点，必须进入“教育经历补充”；只有原文存在独立的“荣誉/奖项/奖学金”标题时才进入主要荣誉。不能仅凭条目语义把教育经历内部内容改分到主要荣誉。
9. 只有原文确实存在独立栏目时，才把语言、证书、荣誉或论文分别映射到对应模块；一个可见栏目混合多种内容时必须整体保留为自定义栏目，不能按语义拆散。
10. 用户没有要求修改的内容和布局必须原样保留；任何不确定的归类都保留原文，不猜测、不补写。粗体只依据原文视觉证据，不能因为英文、缩写、技术名词、数字、百分比或看起来重要就推断加粗。段落或分点开头出现完整粗体片段并紧接冒号/中文冒号或其他分隔符（例如“**重点内容**：XXXXX”）时，必须优先检查并保留开头实际粗体片段；这是高优先级的局部粗体证据，但只标记冒号前实际粗体范围，不延伸到后文。
""".strip()


def build_layout_context(
    layout_data: dict[str, Any] | None,
    *,
    include_full_config: bool = False,
) -> str:
    """Return the capability contract and the current normalized layout.

    ``include_full_config`` is deliberately opt-in.  Ordinary conversation
    only needs the supported-path index and current editable values; a layout
    mission or a visual layout request opts in to the complete renderer
    configuration so the model can reason about the actual state rather than
    guessing from historical messages.
    """
    config = normalize_layout_config(layout_data or {})
    global_config = config["global"]
    summary = {
        "version": config["version"],
        "typography": {"fontSizes": config["typography"]["fontSizes"]},
        "global": {
            key: global_config[key]
            for key in (
                "lineHeight", "moduleMargin", "marginVertical", "marginHorizontal",
                "titleStyle", "sectionOrder", "hiddenSections", "titleOverrides", "sectionPlacements",
            )
        },
        "basics": {
            key: config["basics"].get(key)
            for key in ("preset", "contactLayout", "photoPosition", "photoHeightMm", "hiddenFields")
        },
        "education": {
            key: config["education"].get(key)
            for key in ("preset", "schoolTagStyle", "metricsPlacement", "hiddenMetrics", "supplementListStyle")
        },
        "content_styles": {
            section: {
                key: config[section].get(key)
                for key in ("listStyle", "detailsStyle", "showRole", "showDate", "showJobType", "hiddenComponents")
                if key in config[section]
            }
            for section in ("skills", "research_interests", "honors", "publications", "work_experience", "project_experience", "others", "self_evaluation")
        },
    }
    return (
        "【当前排版契约】以下是已经归一化的当前布局，只能在用户明确要求时修改；"
        "全局行距和模块间距对所有模块生效，模块不能自行覆盖它们。\n"
        f"{json.dumps(summary, ensure_ascii=False, indent=2)}\n"
        "模块标题样式由 global.titleStyle 统一控制；sectionOrder 只影响模块顺序；"
        "sectionPlacements 仅表示并入教育经历的子模块关系，不等于删除原数据。\n"
        f"{build_layout_context_text(layout_data, include_full_config=include_full_config)}"
    )


def build_model_contract_context(
    layout_data: dict[str, Any] | None,
    *,
    include_full_config: bool = False,
) -> str:
    return (
        f"{CONTENT_STRUCTURE_GUIDANCE}\n\n"
        f"{build_layout_context(layout_data, include_full_config=include_full_config)}"
    )
