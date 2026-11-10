# 角色资产图全身构图

镜像 `arcreel/arcreel:local-character-framing-20261110` 已部署，`deploy-arcreel-1` 容器健康运行。它继承已部署的[图片分流镜像](local-image-routing.md)，只覆盖角色资产图的 `layout/character.md` 和 `exclusions/character.md` 两个提示词片段；两份推断规则和这两个片段均已在运行容器中核对。文生图、四参考生图端点与既有页面版本沿用上一镜像。

正常角色资产图的正面、90° 侧面与背面现在都明确要求完整全身：头部顶端至足部或尾端完整入画，三面比例与自然姿态一致，平视远景，四周及上下留安全边距，使用均匀中性光照明。动物与非人类角色按自身身体结构完整展示。角色资产图的负向约束增加半身、胸像、面部特写及头足裁切。

古月方源已先使用端点测试里的独立头像提示词生成脸部参考，再上传为角色原图，通过真实 Edge 的正式角色重生成操作制作全身三视图。上传后的参考图与原始脸部 PNG 字节相同。正常角色资产生成以原图为参考，使用全身三视图布局；角色衍生仍继承已生成的本体资产图。个人外貌由项目角色描述指定。

生产模版 API 为只读，内置模版直接从镜像中的包目录加载；没有数据库模版覆盖层。`PromptTemplates` 在进程启动时编译片段，本轮已通过镜像切换和容器重启使新布局生效。以下命令用于重现部署，构建和切换前确认当前生成任务已结束。

```powershell
docker build --pull=false -t arcreel/arcreel:local-character-framing-20261110 D:\AI\_tmp\arcreel-image-routing-20261110\character-framing-overlay
# 将 docker-compose.override.yml 的镜像改为上述 tag 后，在 deploy/ 执行：
docker compose up -d --no-deps arcreel
```

回滚时将覆盖文件镜像改回 `arcreel/arcreel:local-image-routing-20261110`，运行相同 compose 命令即可恢复旧角色构图；上一轮生图分流及四参考端点继续可用。

证据目录 `D:\AI\_tmp\arcreel-image-routing-20261110` 保存生产片段基线、`character-framing-manifest.json`、生产引擎拼接结果 `production-character-framing.json` 及测试日志。相关提示词测试 74 项通过，生产引擎验证了完整全身要求和原一致性约束同时出现在角色提示词中；场景、道具、商品和角色衍生的提示词与部署前逐字相同。

2026-11-10 的正式网页验收已通过：1536×864、实际使用一张脸部参考的角色资产图成功回填；正、侧、背三面都包含头顶、完整腿脚与鞋底，网页显示新图、已过期数量为 0，未发现控制台错误。脸型和长发延续参考；全身肤色仍较脸部参考偏冷偏灰，正面脸略偏转。脸部参考的发顶轻微裁切，可用于面部身份参考，完整发型轮廓尚未完全满足。原文、脚本和草稿共七份文本文件的最终哈希核对通过。另外完成了脸部加正、侧、背四图的真实端点试验，生成完整单人全身样张；该样张只用于验证，未回写项目，本轮正式角色资产仍使用一张参考图。四图使用正确不代表每次生成都能完全锁脸；详见[验收记录](../../_tmp/arcreel-image-routing-20261110/verification.md)和[交付图](../../_tmp/arcreel-image-routing-20261110/result-summary.webp)。
