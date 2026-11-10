# 人物外观描述规则

资产规划提示词与创作 Agent 现在共用一份外观规则：本体 `description` 是自足、稳定、可直接绘制的短段落。人类角色需要具体脸型、眉眼、鼻口、体态、肤色、毛发与服饰鞋履；原文不足时作少量相容的制作补全，在规划 `reason` 或候选说明里注明依据。已有角色的比较关系先展开为具体可见特征。性格、隐藏情绪和临时动作留在外观段落之外，永久残疾与用户明确造型保留。衍生描述继续只写相对本体的变化。

规则用于新的规划与获准的描述编辑，已有资产不会被自动改写。商品保真、布局、画风、光照与生成通道沿用当前行为。

## 本地镜像与配置

镜像已部署，`deploy-arcreel-1` 容器健康运行，`docker-compose.override.yml` 已指向它。镜像继承[角色全身构图镜像](local-character-framing.md)，只覆盖 12 个提示、profile 与字段说明源文件，保持兼容的生产前后端版本。

| 内容 | 值 |
|---|---|
| 镜像 tag | `arcreel/arcreel:local-asset-descriptions-20261110` |
| Docker 镜像与 manifest list 摘要 | `sha256:daac5ee48fac86b6da22a449971bc3d345013e6c60a32e4fca4481a347695038` |
| image config 摘要 | `sha256:1de06130ef9e52d088f3e631e7457784e9cb9c451e9dc93c84066d4f53128118` |
| 共用规则 SHA256 | `604478aebd97fedf610fb625bbcc6625ff84a595663a4cafbbf81f0cb3cf2425` |
| 前一运行镜像 | `arcreel/arcreel:local-character-framing-20261110` |

## 检查与启用

检查脚本和证据在 `D:\AI\_tmp\arcreel-asset-descriptions-20261110`。镜像使用实际的 `uv run --no-sync` 运行时。断网检查只挂载只读脚本，数据落在容器内临时目录，检查三份真实 schema、五条规划路径和 narration/drama/ad 的正常 profile 物化，不调用模型，也不挂生产数据卷或发布端口。

部署脚本默认只输出计划。下面第一条命令检查当前容器、候选镜像与原有 compose 文件；第二条命令执行相同计划，先断网验证，再重建 `arcreel` 服务、等待健康，并对指定项目做保留手工内容的普通 profile 同步。

```powershell
& D:\AI\ArcReel\.venv\Scripts\python.exe D:\AI\_tmp\arcreel-asset-descriptions-20261110\deploy-description-overlay.py --expected-candidate-id sha256:daac5ee48fac86b6da22a449971bc3d345013e6c60a32e4fca4481a347695038
& D:\AI\ArcReel\.venv\Scripts\python.exe D:\AI\_tmp\arcreel-asset-descriptions-20261110\deploy-description-overlay.py --expected-candidate-id sha256:daac5ee48fac86b6da22a449971bc3d345013e6c60a32e4fca4481a347695038 --apply
```

`project-profile-check-and-sync.py` 默认只读；传 `--apply` 才调用 `sync_profile_to_project`。它要求已有 manifest 与项目内容模式匹配，保留手工修改、主动删除和项目自有说明，并核对项目 JSON、原文、剧本与资产字节。缺少可信 manifest 时拒绝应用，避免落入完整重置分支。当前目标项目为 `/app/projects/projects/proj-e85dd4ae`。

回退服务镜像时，将本地覆盖文件的 image 改回 `arcreel/arcreel:local-character-framing-20261110`，在 `deploy/` 执行 `docker compose up -d --no-deps arcreel`。数据继续使用 `arcreel-data` 命名卷。

## 验证范围

最终相关测试 **163 项通过**，包括实际规划渲染、三模式 profile 物化、现有字段与作者原句保留，以及附加指令的单空行契约。私有夹具确认普通同步保留手工内容、主动删除与项目自有说明。断网镜像检查是 schema、render 与 profile 检查，不是 Agent SDK 模型执行证明。

完整后端测试尝试在 **72%** 因工作进程的缓存测试超时提前终止；终端记录为 `489 failed / 12179 passed / 41 skipped / 940 errors`，不能视为完整执行。高频问题包括 Windows 软链权限、`realpath/os.getcwd` 的阻塞护栏、日志文件写入和缺失时区数据库。保存的原始源文件在隔离目录中复现了 11 个代表失败；1 个日志案例依赖大套件上下文，少量基线中未复现。本次文案末句变化影响的 1 条旧测试已按实际基础 prompt 的空行契约修正。新增描述测试由最终相关测试覆盖。

`backend-failure-attribution.json` 保存原始与改后运行的分组和代表归因，`production-overlay-manifest.json` 保存最小覆盖内容及生产区域保留检查。原始测试日志、改动前源文件、v1 覆盖文件与 v2 共用规则均保留。

部署后启动流程已正常物化新 profile，显式的保留性普通同步检查为 `unchanged=26`、`errors=0`，未再额外同步。项目中的共用规则、`CLAUDE.md` 和两份 skill 与镜像源文件哈希一致。生产保护比较覆盖 327 份当前及历史项目文件；原文、剧本、草稿与资产图保持原字节。主任务在网页获准保存三条角色描述，`project.json` 的相应变化与正常更新的 profile manifest 单独记入授权变化，见 `production-protection-comparison.json`。
