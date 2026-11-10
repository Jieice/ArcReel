# 本地国风 3D 风格与前端版本兼容更新

现有 `ArcReel.bat` 和本目录的 `docker compose up -d` 会自动合并 `docker-compose.override.yml`，当前使用 `arcreel/arcreel:local-character-framing-20261110`。此镜像在本文已验收的 `local-pages-compat-20261109` 页面与风格版本上，依次叠加[文生图与参考生图分流](local-image-routing.md)和[角色全身构图](local-character-framing.md)，继续使用匹配的生产前后端。访问地址仍为 <http://127.0.0.1:1241>；当前增量的部署、回滚与验收见这两份说明。以下保留页面兼容与国风 3D 风格更新的历史证据。

本轮使用当前生产后端 0.35.0 对应的前端源码，固定 Git revision 为 `27c2a0401379f4d8d6ab07d09ad4b9e6232fa4d5`。此前主检出的更新版前端读取了旧后端未提供的模型生命周期字段，并访问了尚未部署的远程素材库与存储接口。前端与后端版本对齐后，页面按现有后端接口工作。全局设置采用该版本原有的 12 个区段，本地素材库仍位于 `/app/assets`。

前端只重放已有的四个国风 3D 预设、独立预览图和文字自定义风格。半写实、仙侠史诗、暗黑武侠、水墨动画分别使用独立预览图；文字风格可保存并重新加载，参考图片模式继续可用。原有 36 张风格预览图和其他原版公共资源均逐 Git blob 验证后保留，最终产物包含 40 张风格预览图。

新镜像继承 `arcreel/arcreel:local-model-page-fix-20261109`，仅替换 `/app/frontend/dist`，并继续使用 `uv run --no-sync uvicorn server.app:app --host 0.0.0.0 --port 1241` 启动。后端、数据库、命名卷 `arcreel-data` 和自定义端点配置保持原有版本；既有项目章节继续保留。回滚时将覆盖文件的镜像改回 `arcreel/arcreel:local-model-page-fix-20261109`，再运行 `docker compose up -d`。

本轮源码、定制补丁、依赖锁哈希、构建清单、检查日志和浏览器证据位于 `D:\AI\_tmp\arcreel-pages-compat-20261109`。构建使用 Node `24.22.1`、项目声明的 pnpm `10.33.2` 与该 revision 的原始 `pnpm-lock.yaml`；冻结安装后锁文件 SHA256 为 `37662c802087371f8ca6b71371dfad0f56119cc56ee212c373b81a99e1cd8530`。`frontend-build-manifest.json` 记录了全部 156 个构建文件、四张新预览图、补丁及锁文件的哈希；`compatible-asset-manifest.json` 记录了原版 51 个公共资源和 484 张截图基线的 Git blob 核对结果。

本轮验证已完成：完整 `pnpm check` 通过 298 个测试文件、3985 项测试，类型检查、lint、knip 全部通过；完整页面级套件通过 1486 项，部署前针对设置、供应商、端点及风格的 59 项检查也全部通过。部署后的真实 Edge 验收通过 42 项页面与操作检查，页面异常、控制台错误和 API HTTP 失败均为 0；项目、原文、剧本、配置、后端风格模板和预览图的部署前后基线核对通过。两条导航取消请求已核对为项目 SSE 和市场刷新在离开页面时的取消行为。页面级套件在 Windows Chromium 上运行，验证了行为、可达布局及 axe；容器截图比较未运行，原有 484 张截图基线保持原样。具体结果见 `pnpm-check.log`、`pnpm-e2e.log`、`focused-e2e-independent.log` 和 `verify-matched-*` 验收记录；从源码重现构建的完整步骤见证据目录中的 `reproduce-build.md`。

重新构建已准备的镜像：

```powershell
docker build --pull=false -t arcreel/arcreel:local-pages-compat-20261109 D:\AI\_tmp\arcreel-pages-compat-20261109\overlay
docker compose up -d
```

原始基础镜像仍保存在 `arcreel/arcreel:style-base-20261109`，ID 为 `sha256:5b3310ec1ecea2fc5749d2f0cdeaa48523afa671369be9cdc0e0061f82571b4a`。原风格功能证据位于 `D:\AI\_tmp\arcreel-style-20261109`，独立预览图证据位于 `D:\AI\_tmp\arcreel-cn3d-previews-20261109`，上一轮候选元数据兼容补丁证据位于 `D:\AI\_tmp\arcreel-model-page-fix-20261109`。需要退回更早的风格版本时可按这些目录中的原记录选择已有镜像；移开覆盖文件会恢复启动器的原默认镜像选择。
