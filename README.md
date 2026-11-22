# Telegram 防骗证据复核

一个离线的截图和视频线索标记工具。可识别机器人与消息归因、外链提示、付款请求和授权相关文字。结果按证据来源展示，用于人工复核。

公开仓库中的演示素材是独立绘制的教学图。它没有 Telegram 登录、商铺、收款或钱包功能。使用真实材料时，把输入清单、素材和分析结果放在本地，由使用者自行保管。

## 玩本地防骗闯关

下载或克隆后，用浏览器打开 [training.html](training.html)。打开文件即可练习。页面不需要终端、服务器或联网。左侧选择「红包与提现」或「商铺与付款」路线，每条四关。先判断该核对哪份证据，再看反馈和下一关。点击一条检测结果，可以定位到对应的合成证据行。

每关的检测结果由现有的 \`rules.py\` 根据合成证据生成。证据缺失条目单列待核。页面使用独立的教学布局和固定假数据，所有点击只改变本地练习进度。

![授权关实测画面（合成教学数据）](training/sample-screen.png)

要改练习内容，在 \`training/lessons.json\` 编辑关卡。页面结构在 \`training/index.template.html\`。生成和复核命令如下：

\`\`\`sh
python3 -B build_training.py
python3 -B build_training.py --check
python3 -B -m unittest -v test_rules test_training
\`\`\`

## 运行教学样例

默认 OCR 需要 macOS Apple Vision、Swift 命令行工具和 Python 3.9+。视频额外需要 PATH 中的 FFmpeg 和 FFprobe。截图模式无需 FFmpeg。初次运行会在 `.build/` 编译本地 OCR 助手，不安装 Python 依赖。

```sh
python3 review.py --manifest demo.json --output .local/demo-01
```

在本机浏览器打开 `.local/demo-01/report.html`。点击一条结果可以查看原图位置，或跳到原视频时间码。也可以读取 `findings.json`。每次运行使用一个新输出目录。

```sh
python3 -B -m unittest -v test_rules
```

## 导入自己的材料

清单中的路径相对于清单文件。源文件需要在打开报告的机器上保持可读。视频默认每三秒取样，同时加上清单中的 `checkpoints` 和人工条目的时间点。`--interval 2` 可改为每两秒一次。

```json
{
  "title": "本地复核",
  "mode": "local",
  "sources": [
    {"id": "image1", "kind": "image", "path": "screenshot.png", "label": "原截图", "reference": "帖子 #1"},
    {"id": "video1", "kind": "video", "path": "recording.mp4", "label": "原视频", "reference": "帖子 #2", "checkpoints": [12.75]}
  ],
  "reviewed": [
    {
      "source_id": "video1", "category": "payment", "status": "pending", "grade": "E0",
      "timestamp": 12.75, "box": null, "title": "实际扣款待核",
      "summary": "仅见付款请求，需独立流水。"
    }
  ]
}
```

`box` 是原画面左上原点下归一化的 `[x, y, width, height]`，可省略。人工录入的 E2 表示复核过的可见内容，凭证缺失用 E0，待确认文字或声明用 E1。OCR 提取是 E1，不能证实账号归属、成功付款或实际授权。视频是取样；未命中不能证明未出现。相邻视频帧重复出现同一线索时，列表只留连续区间的起始线索。

## 数据与实现边界

- `review.py` 读取显式列出的本地文件，保存来源指纹、证据引用和结果。
- `ocr.swift` 使用 Apple Vision，原始 OCR 文字只经过本地进程管道。
- `rules.py` 静态处理 OCR 和链接字样，输出固定文字及定位。OCR 不会把原始域名、账号、交易编号放进报告。
- `report.py` 生成静态 HTML。证据在本机取阅，报告链接会引用本机源文件。
- MVP 没有收款、登录、钱包操作、链上查询和跟随外链模块。实际资金动作仍要看独立付款回执或链上记录。
- 需要换 OCR 引擎时，可通过 `--ocr-bin /absolute/path/to/helper` 使用本机兼容程序。其 stdin 逐行接收 `{"id":"…","data":"base64 图像"}`，stdout 逐行返回含 `id`、`width`、`height`、`lines` 的 JSON。每个 `lines` 元素含 `text`、归一化 `box` 与 `confidence`，坏图返回 `error`。

源码与合成样例使用 MIT 许可。Swift、macOS Vision 与 FFmpeg 来自运行环境，遵循各自许可。
