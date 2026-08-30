"""Stable, user-grounded contracts shared by conversation and proposal prompts."""

from __future__ import annotations

import json
from typing import Any

from .layout_config import normalize_layout_config
from .layout_capabilities import build_layout_context_text
from .resume_contract import build_resume_edit_contract_text


CONTENT_STRUCTURE_GUIDANCE = """
【经历内容结构契约】
1. 工作经历的 content_blocks 只允许 introduction（工作简介）、responsibilities（工作职责）、generic（其他工作内容）三种语义角色；项目经历使用 introduction（项目简介）、responsibilities（项目职责）、generic（其他项目内容），并额外允许 tech_stack（技术栈）。不能创建其他 semantic_role。tech_stack 只用于项目内明确的技术栈/技术选型/使用技术/技术工具内容；generic 表示无法或无需映射到其他角色的经历正文。
2. semantic_role 只说明内容含义，不决定排列形式。paragraph、bullet_list、numbered_list 三种 type 均可用于允许的语义角色；paragraph 的正文写入 text，列表正文写入 items，列表项不得重复序号或圆点。修改已有内容块时保留其当前 type，只有用户明确要求改变段落、分点或编号形式时才改变 type。
3. content_blocks 的顺序按当前简历数据和用户明确要求保留；不能仅因角色名称擅自移动、拆分或合并内容块。标题是否显示由 label 决定，label_bold 只表示标题字重；generic 不应凭空增加语义标题。简历内容通过所属上级模块路径、当前显示标签和稳定内部语义共同定位；修改 label 不得改变 semantic_role，同名内容无法由上级模块唯一确定时必须先澄清。局部粗体必须留在同一个正文 text 或 items 条目中，不能提升为 label 或新内容块。
4. 【内容块边界与分类】先按原文视觉结构划分候选内容组：栏目标题、段落/分点/编号、缩进、对齐、空行和连续性共同确定边界；视觉边界优先于语义猜测。明确的技术栈标题及其正文属于 tech_stack；工作简介或项目简介标题及其正文属于 introduction；工作职责或项目职责标题及其正文属于 responsibilities。没有明确语义标题时不根据词义或技术名词自行补造角色，内容保留为 generic。
5. 【解析阶段视觉证据】在解析产生 content_block 时可填写 source_layout_group、source_indent_level、source_marker_type 三个辅助字段表示连续视觉组；它们只供后处理分类，最终不会保存或显示。无法确认视觉边界时保持在当前内容组，不因单个词语或句子含义拆组。
6. 【内容完整性】所有可见经历正文必须原样进入某个 content_blocks 且只能出现一次，不能省略。项目简介之后没有明确新标题或视觉边界的内容保持在当前内容组；不确定时保留原文，不猜测、不补写。
7. 教育经历栏目下、下一个顶层栏目之前的无标题内容进入 education_supplement（教育经历补充）；只有原文存在独立的荣誉/奖项/奖学金标题时才进入 honors（主要荣誉）。工作经历中的无独立标题补充内容使用 work_experience 的 generic 内容块（其他工作内容）；项目经历中的无独立标题补充内容使用 project_experience 的 generic 内容块（其他项目内容）。三者是不同根路径下的补充内容，不能互相挪用或按语义重复写入。
8. 只有原文确实存在独立栏目时，才把语言、证书、荣誉或论文分别映射到对应模块；一个可见栏目混合多种内容时必须整体保留为 custom_sections，不能按语义拆散。用户没有要求修改的内容和布局必须原样保留。
9. 粗体只依据原文视觉证据，不能因为英文、缩写、技术名词、数字、百分比或看起来重要就推断加粗。段落或分点开头出现完整粗体片段并紧接冒号/中文冒号或其他分隔符时，只标记冒号前实际粗体范围，不延伸到后文。
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
        "education": {
            key: config["education"].get(key)
            for key in ("schoolTagStyle", "hiddenMetrics", "supplementListStyle")
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
        f"{build_resume_edit_contract_text()}\n\n"
        f"{build_layout_context(layout_data, include_full_config=include_full_config)}"
    )
