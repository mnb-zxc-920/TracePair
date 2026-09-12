# 第一次使用 TracePair

[English](getting-started.md) · [中文说明](README.zh-CN.md) · [在线合成演示](https://mnb-zxc-920.github.io/TracePair/)

先运行内置演示，无需 Codex 账号、API key 或个人日志。本机需要已安装 Python 3.10+；若命令叫 `python3`，相应替换下方命令。

## 获取项目并运行演示

任选一种获取源码的方式：

- 已有 Git：运行 `git clone https://github.com/mnb-zxc-920/TracePair.git`，然后 `cd TracePair`。
- 没有 Git：在 [下载页](https://github.com/mnb-zxc-920/TracePair/releases/tag/v0.1.0) 下载 `tracepair-v0.1.0-source.zip`，解压后，在其中的 `TracePair-0.1.0` 文件夹打开终端。确认这里有 `tracepair.py`，不要在未解压的 ZIP 或上级下载目录里运行。

```sh
python tracepair.py demo --out my-demo
```

用浏览器打开 `my-demo/report.html`。同目录还有 `summary.json` 和 `share.svg`。这是合成样例，数字不代表真实改善。

## 找到两份日志

Codex 会话记录位于 `CODEX_HOME/sessions`，归档会话位于 `CODEX_HOME/archived_sessions`；默认 Codex 主目录为 `~/.codex`。[官方日志位置](https://learn.chatgpt.com/docs/reference/troubleshooting#feedback-and-logs) · [Codex 主目录说明](https://learn.chatgpt.com/docs/config-file/config-advanced#config-and-state-locations)。

- Windows 默认位置：在文件资源管理器地址栏粘贴 `%USERPROFILE%\.codex\sessions`。归档目录是 `%USERPROFILE%\.codex\archived_sessions`。
- macOS / Linux 默认位置：用文件管理器打开 `~/.codex/sessions` 或 `~/.codex/archived_sessions`。
- 自定义过 `CODEX_HOME`：到该目录中的对应子文件夹查找。Codex 在 WSL 或另一台机器上运行时，到那个环境的 Codex 主目录查找。

在这些目录及其子文件夹中，手动选出自己要比较的两份会话 `.jsonl` 文件。不要传入文件夹、`history.jsonl`、导出的聊天文本或 App 诊断日志。如果没有本地运行日志，这一版 TracePair 不能从云服务替你获取。

优先选择已经停止写入的会话。同一文件可以包含很多轮对话；比较整个文件时，看到的是这段会话的可观察用量。只想比较其中两个时段时，使用 [明确的时间窗参数](../README.md#compare-windows-in-longer-sessions)。两份日志出现相同模型，也不能证明任务难度或验收标准相同。

## 比较自己选出的文件

把示例路径换成刚才选择的两个文件，带空格的路径保留引号：

```powershell
python tracepair.py compare "C:\my logs\run-a.jsonl" "C:\my logs\run-b.jsonl" --out my-comparison
```

macOS / Linux 使用对应的完整路径，例如：

```sh
python3 tracepair.py compare "/path/to/run-a.jsonl" "/path/to/run-b.jsonl" --out my-comparison
```

打开 `my-comparison/report.html`。日志在本机读取；聚合统计仍可能敏感，分享前请自行检查。

## 卡在哪一步，就检查哪里

| 提示或现象 | 下一步 |
| --- | --- |
| Python 找不到 `tracepair.py` | 在包含这个文件的源码目录重新打开终端。 |
| `TracePair: unreadable input` | 检查两个文件路径及读取权限，不能传文件夹。 |
| `Output directory already exists` | 换一个名称，例如 `--out my-comparison-2`；已有报告会保留。 |
| `invalid time window` | 使用带时区的 ISO 8601 时间，例如 `2026-01-01T09:00:00Z` 或 `2026-01-01T17:00:00+08:00`；同时设置起止值时，结束必须晚于开始。 |
| `Accounting gaps detected` 或 `Unknown` | 展开报告的 **Accounting notes**；缺字段不等于测量值为零。 |
| `NO_TOKEN_DATA` | 核对是否选中了 Codex 会话运行日志。文件可能没有可用计数快照，也可能格式尚不支持。 |
| `COUNTER_RESET` 或 `INVALID_COUNTER` | 计数证据不足以得到可靠总量，因此被暂扣；参阅[计数说明](accounting.md)。 |

报问题时记录 `python tracepair.py --version`、`python --version`、操作系统、固定警告代码和一个编造的小例子，使用[问题模板](https://github.com/mnb-zxc-920/TracePair/issues/new?template=bug_report.md)。不要附原始日志、凭据或私人截图。暂时不会写合成复现时，先提交版本和警告代码即可。
