# Windows 安装与启动

## 1. 准备环境

安装 Python 3.12 x64、Git 和较新的 NVIDIA 显卡驱动。建议 8GB 显存、16GB 内存、至少 15GB 可用磁盘空间。只验证了 Windows + NVIDIA；当前程序会在没有可用 CUDA GPU 时提示错误。

下载或克隆仓库后，在仓库目录运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

如果 Python 没有注册到 `py` 启动器，指定 Python 3.12 的可执行文件：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -Python "你的 Python 3.12 可执行文件路径"
```

安装脚本只使用本仓库的 `.venv`，安装 CUDA 12.8 版 PyTorch、记录的依赖版本和本地 WhisperLiveKit 快照，不改全局 Python。首次准备需联网，耗时取决于下载速度。

## 2. 下载与转换模型

阅读 [第三方声明](../THIRD_PARTY_NOTICES.md)、[Whisper MIT 许可](../licenses/Whisper-MIT.txt) 和 [Tencent HY Community License](../licenses/Tencent-HY-Community.txt)。同意适用条款后运行：

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_models.py --accept-model-licenses
```

脚本将完成以下工作：

1. 下载 OpenAI 官方 `large-v3-turbo.pt`，校验 SHA-256。
2. 用固定版本的官方模型元数据将原权重转为 float16 CTranslate2；逐项核对张量名称和形状，记录转换来源，不重新训练。
3. 下载腾讯官方 `HY-MT1.5-1.8B-Q4_K_M.gguf`，校验 SHA-256。
4. 下载固定的 llama.cpp `b11146` Windows Vulkan 运行包，校验并解压。

模型不在 GitHub 源码中。脚本不会读取已有课堂历史，也不会绕过模型授权。官方下载不可达时，可以手动从声明中链接的官方来源准备文件；请勿用来历不明的同名文件替代。

只查看下载来源、不下载：

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_models.py --plan
```

准备完成后应有：

```text
models/large-v3-turbo.pt
models/large-v3-turbo-ct2/model.bin
models/large-v3-turbo-ct2/tokenizer.json
models/large-v3-turbo-ct2/conversion-provenance.json
models/HY-MT1.5-1.8B-Q4_K_M.gguf
runtime/llama/llama-server.exe  （或其解压子目录）
```

所有模型、运行包与数据目录均被忽略，不应提交到 GitHub。

## 3. 启动与结束

双击 **开始课堂翻译.cmd**，浏览器打开 `http://127.0.0.1:8766`。等待本地模型就绪，再点击 **＋** 开始收音。推荐 Edge 或 Chrome。

点击 **结束并保存** 完成本堂录音；等待中文处理完成后导出对照。点击 **下载录音** 保存 WAV。停止服务前先结束录音并等待队列完成，然后双击 **停止课堂翻译.cmd**。

## 4. 常见问题

| 情况 | 检查方法 |
|---|---|
| 未检测到 NVIDIA GPU | 更新显卡驱动；在 `.venv` 中确认 CUDA 版 PyTorch，安装脚本结尾会检查 |
| 缺少英文模型或中文进程退出 | 检查以上文件是否齐全、校验是否通过；查看本机 `runtime/app-error.log` 与 `runtime/translation.log` |
| 下载中断 | 再次运行准备脚本；完整文件校验通过会跳过，未完成下载会重新下载 |
| 转换中断留下 `.preparing` | 先检查 `models/large-v3-turbo-ct2.preparing`，确认是不完整转换后自行移除该目录，再重试；不要删除课堂历史 |
| 8766 端口被占用 | 停止旧的课堂服务，或关闭占用该端口的其他程序后启动 |
| 没有麦克风声音 | 检查浏览器权限、Windows 麦克风权限、选中的输入设备和距离 |
| 英文缺词或中文不准确 | 改善麦克风位置，填写术语和课程背景；结合原录音核对，字幕不能保证完全正确 |

提交问题前请先去除日志中的个人信息，不上传真实课堂录音或数据库。

## 发布验证范围

本次源码整理在现有 Python 3.12 环境验证了隔离测试、源码打包、安装脚本语法和发布内容检查；尚未在另一台全新电脑完成全部依赖及多 GB 模型下载。GPU/模型推理效果来自发布前用户已验收的本机应用，自动测试不等于新的课堂性能保证。
