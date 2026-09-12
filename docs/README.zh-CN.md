# TracePair

**两次 Codex 运行，变化在哪里？**

指定两份已有的 Codex JSONL 日志，在本机生成 HTML 对比报告、JSON 摘要和 SVG 分享卡。无需 API key、hook、服务器或运行时第三方包。

## 先运行演示

需要 Python 3.10 或更新版本。

```sh
git clone https://github.com/mnb-zxc-920/TracePair.git
cd TracePair
python tracepair.py demo --out my-demo
```

双击 `my-demo/report.html`。演示数字全部是合成数据，用于展示界面，不代表真实提升。部分 macOS/Linux 系统需把命令里的 `python` 换成 `python3`。

然后比较自己的两份日志：

```powershell
python tracepair.py compare "C:\my logs\run-a.jsonl" "C:\my logs\run-b.jsonl" --out my-comparison
```

输出目录必须是新目录。TracePair 不覆盖已有报告，不修改输入文件，也不自动扫描你的历史会话。为得到稳定快照，优先选择已结束写入的日志。

## 报告怎样读

| 内容 | 含义 |
| --- | --- |
| Input / Cached / Uncached | 原生输入、其中缓存输入、两者之差 |
| Output / Reasoning | 原生输出及其中推理输出，不能相加重复计数 |
| Tool activity | 日志里观察到的工具调用，按固定类别归组 |
| Recorded span | 选中记录的时间跨度，包含等待，不等于有效工作时长 |
| Accounting notes | 重复快照、起点缺口、计数重置、缺字段等说明 |

改了 prompt、AGENTS.md 或操作方式后，可以用它看看两次记录有什么差异。是否完成同样的任务、结果是否同样好，需要另行检查。较少 token 不自动等于效率更高，更不等于节省相同比例的周额度或费用。

遇到缺字段会显示 `Unknown`。累计计数重置或必要字段不一致时会暂扣总量。时间窗支持 `--a-start`、`--a-end`、`--b-start`、`--b-end`，必须带时区；窗口起点可能只能近似归属，详见 [英文计数说明](accounting.md)。

## 分享边界

导出仅保留聚合数字和固定说明，不带原文、路径、会话 ID、原始模型名或自定义工具名。聚合数字本身仍可能敏感，分享前请检查。工具不会联网、发送遥测、分析任务质量或给出费用估计。

第一版只支持 Codex 原生 JSONL。编排工具里面嵌套的调用不会展开。它不是 OpenAI 官方产品，也不能作为账单凭据。

反馈请带版本、警告代码和合成复现案例，不要上传原始对话日志。项目由 Codex、Grok 等 AI 辅助开发；源码、测试和局限公开，欢迎指出问题。

[返回英文 README](../README.md) · [隐私说明](privacy.md) · [MIT 许可](../LICENSE)
