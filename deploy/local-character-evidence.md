# 人物原文证据与外貌提案：本地部署记录

2026-11-10 已部署人物原文证据与外貌提案工具，以及兼容生产 0.35 的资产描述编辑前端。`deploy-arcreel-1` 健康运行；长期 `docker-compose.override.yml` 已指向最终镜像，保留原有 `pull_policy: never` 和其余设置。

| 内容 | 已部署值 |
|---|---|
| 镜像 tag | `arcreel/arcreel:local-character-evidence-ui-20261110-r5` |
| Docker 镜像精确 `.Id` | `sha256:009ebb3f21d4479db5e063acf19a17e500b17992887ad5f7197b6c024e09ce86` |
| 容器 ID | `db210f4b503f57b0afef8f918de2e4e4a8c64f4bcf32d7f1d6070b79dad3e849` |
| r3 的基底（上一版 UI 镜像） | `sha256:5542a14b70d359c88069d871bd21904a28823549751f87eef06f5c7efa27b9e0` |
| 后端候选基底 | `sha256:98d27cd77e3b6903d51d5f18d464d9db9667712122757fe63895645e7eae2b71` |
| 回滚镜像精确 `.Id` | `sha256:daac5ee48fac86b6da22a449971bc3d345013e6c60a32e4fca4481a347695038` |
| 项目数据卷 | `arcreel-data` → `/app/projects` |
| 本地端口 | `127.0.0.1:1241` |

新增 `collect_character_evidence`、`read_character_evidence`、`save_character_appearance_proposal`、`get_character_appearance_proposal`、`apply_character_appearance_proposal` 五个工具。程序扫描所有已登记原文，模型按页读取关键词命中上下文；提案区分原文事实、未知项与制作补全，并校验原句引用。原文、角色依据或声明约束变化后，旧提案会被判为过期。

收集、保存和读取提案保留正式资产；显式应用仅更新所选本体或衍生的外貌描述。角色图、参考图、声音和已有血袍等资产继续保留。图片生成仍需单独发起。

## 已完成的部署检查

部署前确认真实 `tasks` / `agent_sessions` 没有活动作业。健康检查通过，挂载、端口与配置哈希一致，23 份原文、剧本、资产、参考和版本图保护文件与部署前完全一致。

断网私有容器已验证五个真实工具声明、三种内容模式的 profile 物化、Write/Edit/Bash 写保护、选择性应用、重复无写和过期拒绝；没有模型或图片生成请求。最终前端的 156 份冻结 dist 文件逐一匹配。

目标项目 `/app/projects/projects/proj-e85dd4ae` 的 `drama` profile 已由正常流程同步。新增 `.claude/skills/analyze-character-appearance/SKILL.md` 和 `.claude/references/character-appearance-proposals.md` 的镜像源、项目文件与 manifest 三份哈希一致。部署后的核验只读，未调用普通或强制同步。

**真实内置 Agent 提案验收：通过（r3）。** 首次验收失败的原因是 `snapshot_revision` / `proposal_revision` 的 schema pattern 带 Python 专属的 `\Z`，模型网关（krisphyn，`cn:deepseek-v4.1-flash`）拒绝任何携带 save/apply 工具的请求并报「可用渠道不存在」。r3 只覆盖 `lib/character_appearance/models.py`，把 pattern 改为 `^sha256-v1:[0-9a-f]{64}$`；修正后 61 个工具一起发送返回 200。

验收经正式会话接口发起（会话 `cc40ffd3-9088-40c8-aab2-1a2287f2d9ff`，未走浏览器点击）：扫描 5 份原文 44,926 字符、57 处命中、3 页全部读取，保存并回读提案 `cap_57fb8f5b49c3481aa5fe6d298fd3f8bf`（`current`），0 次网关错误。未应用描述、未生成图片，`project.json` 与角色图未变。构建目录与验收脚本在 `D:\AI\_tmp\arcreel-character-evidence-20261110\schema-regex-fix`。

## 后续默认启动

在 `D:\AI\ArcReel\deploy` 使用两个常规配置文件即可保持此版本，无需依赖本轮临时覆盖文件。启动前应确认本地 tag 仍解析为上表的精确 `.Id`：

```powershell
docker image inspect --format '{{.Id}}' arcreel/arcreel:local-character-evidence-ui-20261110
docker compose --file docker-compose.yml --file docker-compose.override.yml up -d --no-deps --pull never arcreel
```

此处记录后续操作命令；更新长期配置和本说明时未再次启动、重启或部署服务。

## 备份、证据与回滚

本轮部署报告目录：`D:\AI\_tmp\arcreel-character-evidence-20261110\deployment\20261110T053816-105868Z`。

- `report.json`：成功部署、精确镜像、健康、配置哈希和保护文件结果。
- `protected-before.json` / `protected-after.json`：23 份保护文件哈希。
- `profile-postdeployment-check.json`：新增 profile 三份哈希一致的只读证据。
- `long-term-compose-override-update.json`：长期配置仅 image 行变化、其余渲染设置一致的证据。
- `backup/`：原 Compose 配置、`.env` 备份和 `projects-and-consistent-sqlite.tar.gz`。SQLite 使用只读连接和 `sqlite3.backup` 产生一致快照，完整性检查为 `ok`。
- `backup/long-term-docker-compose.override.before-ui.yml`：更新长期配置前的原文件，SHA256 为 `bd0e3076d20ae1442b350151e57e63e40834da235a0ec2bd1fecc358f6c808fd`。

项目与一致数据库归档大小为 `121199280` 字节，SHA256 为 `555439d8fd4c4e0b13ebac324a5d15b1cdc41ee487ac7e5b61bc28fc23e0eba5`。备份包含原配置与项目数据；公开检查结果只记录路径、字段名和哈希。

本轮运行容器的 Compose 文件顺序包括旧覆盖文件和最后的候选 SHA 覆盖文件。回滚时保留此顺序，并将 `rollback.override.json` 作为最后一个文件，使镜像固定回到上表的 `daac…` 版本：

```powershell
docker compose --project-name deploy --project-directory D:\AI\ArcReel\deploy `
  --file D:\AI\ArcReel\deploy\docker-compose.yml `
  --file D:\AI\ArcReel\deploy\docker-compose.override.yml `
  --file D:\AI\_tmp\arcreel-asset-descriptions-20261110\overlay\deployment.override.json `
  --file D:\AI\_tmp\arcreel-character-evidence-20261110\deployment\20261110T053816-105868Z\deployment.override.json `
  --file D:\AI\_tmp\arcreel-character-evidence-20261110\deployment\20261110T053816-105868Z\rollback.override.json `
  up -d --no-deps --pull never arcreel
```

若要长期保持回滚版本，还需将常规 `docker-compose.override.yml` 的 image 改回 `arcreel/arcreel:local-asset-descriptions-20261110`，并核验其精确 `.Id`。镜像回滚继续使用原数据卷；恢复项目或数据库备份前，先核对部署后的用户编辑，避免覆盖新内容。

## r4：自动补检省称

r4 在 r3（`sha256:5de25ec8abd3d4a58d15d408d629bd57c4b87e329934bd890c9820e6d1b0fe49`）上覆盖 `lib/character_appearance/evidence.py`、`service.py`、`server/agent_toolset/character_appearance.py` 和 `analyze-character-appearance/SKILL.md`。采集时服务器自动加入角色名与已登记别名在原文中独立出现的后缀省称（标 `derived_short_form`，仍只是候选归属），不再依赖 Agent 每次自行补别名。

对当前项目原文的只读核对：古月博新增「族长」，命中 9 → 56、2 → 3 页；沈翠新增「丫鬟」，46 → 52；古月方源新增「老魔」，328 → 330；方正无变化。与名字字面无关的称谓（如「家主」「舅父」）程序推不出，仍需登记为别名或由 Agent 查原文后提供。r4 未重跑内置 Agent 全流程。构建目录：`D:\AI\_tmp\arcreel-character-evidence-20261110\short-form-aliases`。

r4 上线后经正式会话接口重跑古月博全流程（会话 `2a293afc-cabe-4724-b3b9-0dc806c85f0e`）：57 处命中、3 页，保存并回读 `cap_26ad60422bde4e97ab3458f14233ae19`，0 次网关错误，未应用、未出图。

## r5：自动补检「姓 + 称谓」

r5 在 r4（`sha256:449eee408e6e82242d2b6d63f02e332adc4a62409892ef87aeaac246899d42a2`）上覆盖 `evidence.py`、`server/agent_toolset/character_appearance.py` 和分析 skill。采集时把原文里出现的「本体名的姓 + 常见两字称谓」（如「林医生」，标 `surname_title`）加入检索；已登记给其他角色的不借用，同姓他人仍可能命中，由 Agent 按上下文甄别。称谓表在 `SURNAME_TITLES`，不含单字称谓。

断网临时容器用另一部小说（两个时期）跑通 collect → read → save → get → apply：省称与「姓 + 称谓」句均送达，本体与衍生应用成功，重复应用返回 `already_applied`，其他角色不变。该检查不调用模型。当前项目四个角色的检索词与 r4 相同。r5 未重跑内置 Agent 全流程。构建目录：`D:\AI\_tmp\arcreel-character-evidence-20261110\surname-titles`。
