# 本地 Qwen 文生图与参考生图

生图分流已部署。镜像 `arcreel/arcreel:local-image-routing-20261110` 继承 `arcreel/arcreel:local-pages-compat-20261109`，只覆盖两份 ComfyUI 推断规则 JSON；当前健康运行的容器使用继续叠加[角色全身构图](local-character-framing.md)的 `arcreel/arcreel:local-character-framing-20261110`。前端与生产后端版本保持匹配；镜像、端点与回滚证据位于 `D:\AI\_tmp\arcreel-image-routing-20261110`，结果见[本轮验收记录](../../_tmp/arcreel-image-routing-20261110/verification.md)。

全局默认图片模型和文生图用途选择 `custom-2/qwen21-t2i-consist`，参考生图用途选择 `custom-2/qwen21-i2i`。项目可通过用途设置覆盖全局选择。无参考图的素材走 `ce-3`；有参考图的素材与分镜走 `ce-29`。

`ce-29` 四参考定义已通过 API 保存并复读核对，支持一到四张参考图，按输入列表顺序连接 GH 编码器的 `image_01` 至 `image_04`。只提供一张图时，其他三个读图节点和空输入会被移除。超过四张仍按平台已有能力限制处理。此端点仅支持参考生图，不能作为文生图用途选择。单参考和四图同时输入的真实出图均已通过；四个实际输入与上传文件的字节、像素完全一致，使用四个不同参考且无重复。这验证了端点实际使用四图，不构成所有生成结果完全锁脸的保证。

宽高绑定使用节点实际要求的 32 步长。默认 1536×864；其他项目比例由平台根据原生短边换算。保留 Qwen2.1 INT8、Qwen3VL INT8、纹理修复 VAE、16 步、CFG 1、一致性 LoRA 0.48、Turbo LoRA 0.6、现有 Cache/TESpeed 节点和自动参考图尺寸。文生图保留已有 `ce-3` 的 30 步、CFG 4 与一致性 LoRA。

首次部署采用以下构建与端点应用命令，随后已切换到包含角色全身构图的最终镜像。重建当前版本时，先构建这一层，再按[角色全身构图说明](local-character-framing.md)构建最终镜像。切换前确认 ArcReel 与 ComfyUI 的当前生成任务已结束。

```powershell
docker build --pull=false -t arcreel/arcreel:local-image-routing-20261110 D:\AI\_tmp\arcreel-image-routing-20261110\overlay
# 首次部署这一层时，在 deploy/ 执行；当前镜像以角色全身构图说明为准：
docker compose up -d --no-deps arcreel
node D:\AI\_tmp\arcreel-image-routing-20261110\apply-workflow-candidate.mjs apply
node D:\AI\_tmp\arcreel-image-routing-20261110\apply-workflow-candidate.mjs verify
```

端点应用脚本只通过现有 API 更新 `ce-29`，并检查旧定义仍与备份相同、推断正确识别四个消费者、保存复读与候选相同。登录凭据只留在内存，不写入证据。规则文件由进程缓存，镜像切换须重启容器。

整体回滚本层时，先运行端点脚本的 `rollback` 模式，再将覆盖文件镜像改回 `arcreel/arcreel:local-pages-compat-20261109` 并运行相同 compose 命令；这也会恢复旧角色构图。只回滚角色构图时按[角色全身构图说明](local-character-framing.md)操作，保留本层分流。脚本在发现端点已被另行修改时会停止，避免覆盖后续编辑。全局默认与用途选择可以在默认模型页恢复。

已完成验证：四个相关 pytest 文件通过 181 项，最终四参考回归文件 11 项通过；生产 0.35.0 Python 的真实 schema、推断与一至四张参考的请求构造通过；live ComfyUI 节点、连线类型、模型枚举与尺寸步长检查通过。这些静态和构造检查没有提交 GPU 任务。部署后，真实 Edge 文生图、单参考脸部端点试验、正式角色全身重生成和四参考端点试验均已成功，ArcReel 下载结果与对应 ComfyUI PNG 字节相同。四参考试验以 864×1536 生成完整单人全身，耗时 82.909 秒，无 OOM，原工作流定义未变，开始与结束队列为空。该样张仅用于验收，未回写项目；详情与视觉限制见[验收记录](../../_tmp/arcreel-image-routing-20261110/verification.md)。
