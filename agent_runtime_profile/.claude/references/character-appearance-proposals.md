# 外貌提案的证据与版本合同

这份参考配合 `analyze-character-appearance`，处理已登记角色的手动分析。它不改变 `patch_project` 默认行为，不给每次脚本规划加分析前置条件。

## 五个工具

| 工具 | 入参要点 | 结果与副作用 |
|---|---|---|
| collect_character_evidence | character_name；可选 extra_aliases、declared_user_constraints、comparison_characters | 冻结登记原文与角色/参考依据，保存 snapshot；返回扫描量、命中页数、候选归属。正式资产不变 |
| read_character_evidence | snapshot_id、零起始 page | 有界精确原文片段、evidence_id、下一页与服务器交付回执。只新增回执 |
| save_character_appearance_proposal | snapshot_id/revision、receipt_ids、coverage、proposal；可选 parent_proposal_id | 校验出处/交付/当前依据，保存不可变新版本和服务器 selections。正式资产不变 |
| get_character_appearance_proposal | proposal_id | 完整提案、版本、规范化引用、受控依据摘要、current/applied_current/stale及应用记录 |
| apply_character_appearance_proposal | proposal_id/revision、selection_id、character_name、target；衍生加 derivative_name | 选择性写本体或衍生 description，独立审计，不生成图片 |

## 提案结构

`proposal.summary` 概括本次分析；`proposal.stages[]` 按语义时期而非文件分组：

- `stage_id/label`：提案内唯一的时期标识和可读名称。
- `period_status/period_reason/period_citations`：明确时期的来源或未知理由。
- `source_facts[]`：`statement`、精确 `citations`、`attribution`（explicit_name/contextual/ambiguous）及归属理由。
- `conflicts[]`：问题、来源引用、可留空的解决说明。
- `unknowns[]`：原文不足或指代不明。
- `production_supplements[]`：补全说明和理由，不能标为原文。
- `base_description`：可选自足本体外貌候选。
- `derivatives[]`：可选相对本体的稳定变化；name/description/change_kind/persistence_reason。change_kind仅 life_stage、wardrobe、body_change、identity。

`proposal.reference_notes[]` 记录调用方观察或转述；参考路径必须属于冻结的目标参考身份。服务器不识别图片内容，不能用布尔值伪装成服务器看过图。

`declared_user_constraints` 随 collect 的声明上下文冻结，save 不接受临时替换。后续 collect 若修改这些约束、检索称谓或对照角色，旧依据失效。它们的来源是调用方声明，不是服务器验证过的人类确认。

## 精确引用与交付

引用必填 `{evidence_id, quote}`，原句在片段中唯一时，服务器自行计算 offset。`start/end` 可选但必须成对；原句出现多次时提供更完整唯一原句或明确区间。服务器从不可变片段找回路径和页码，验证原始 UTF-8 解码正文的 Python Unicode `[start,end)` 切片；保持 CRLF、组合字符和非 BMP 字符，不改写原句。存档 verified_citations 始终记录服务器确定的 path/start/end。

程序扫描所有登记原文，不代表 Agent 语义读完正文。`coverage=all_match_contexts` 只证明所有关键词上下文页由工具提供；`partial` 仍要求被引用页有有效回执。引文存在不证明外貌解释正确，别名命中不证明唯一身份。

快照冻结 raw source revision、登记/叙事顺序、全部角色名/别名与既有外貌描述/衍生、目标 description/derivatives/参考路径和文件 hash、声明上下文。参考 hash 只标识文件内容。

## 应用边界

先保留提案，用户选择后应用。服务器选择 ID 来自保存版本，不能拼造。base只改本体description，derivative使用既有衍生合并规则，仅改选中变化描述；图片、参考、语音、其他资产/衍生保留。单镜头血污不新建衍生；用户明确指定或跨多场景保持的受伤/血袍造型可登记持续衍生，旧血袍保留。

应用审计记录选定提案revision、选择/目标、描述前后digest和调用方。重复选择在锁内核验后无写返回；同提案连续应用只允许当前依据匹配其已提交result basis，外部变化不得混入。旧版可读，过期拒绝覆盖。

`drafts/character_appearance/` 整子树由 Agent Write/Edit hook和Bash sandbox写禁保护，专用工具在主进程中持锁保存；不要直接编辑、重算摘要或伪造交付回执。
