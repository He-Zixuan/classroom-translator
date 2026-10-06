# 课堂翻译 · Classroom Translator

为线下全英授课准备的本地课堂助手：**先看英文，稍后看完整中文，课后保留双语文字与录音。**

Windows + NVIDIA GPU。应用源码公开，允许个人使用、修改和免费分享，须保留署名及许可证，**禁止商用**。详见 [LICENSE](LICENSE) 和 [中文说明](docs/LICENSE.zh-CN.md)。第三方代码保留原有许可。

## 能做什么

- 电脑麦克风收音；英文初稿即时更新，稳定后保存。
- 本地英译中，原文和译文逐段配对；中文处理不阻塞英文。
- 对较轻的声音做有上限的音量增强，课程背景和术语可配置。
- 点击 **＋** 新建课堂并直接录音；之后可改名。
- **结束并保存**，保存双语字幕和独立 WAV；历史回看、导出对照、下载录音。
- 确认后永久删除选中的课堂、待翻译任务和本机录音。
- 自适应界面、短过渡动画、减少动态效果支持。

模型和依赖准备好后，课堂识别与翻译在本机运行，不需要 API 密钥。当前发行版没有云 API 切换功能。

## 环境与准备

目前验证的平台为 Windows 11、Python 3.12、RTX 5060 Laptop 8GB、16GB 内存。需要较新的 NVIDIA 驱动，中文翻译使用 Vulkan。其他平台和显卡尚未验证。

首次安装要联网下载依赖与模型，建议至少预留 **15GB** 空间。英文初稿约 1–2 秒是目标，不是延迟保证；麦克风位置、环境噪声、讲话方式和电脑负载都会影响效果。中文可以延后，优先保留完整句意。

```powershell
git clone https://github.com/He-Zixuan/classroom-translator.git
cd classroom-translator
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

上面的步骤安装 Python 依赖。先阅读 [模型和第三方许可](THIRD_PARTY_NOTICES.md)，同意适用模型许可后准备模型：

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_models.py --accept-model-licenses
```

然后双击 **开始课堂翻译.cmd**。详细步骤、手动准备方法和问题定位见 [安装说明](docs/INSTALL.md)。这次发布是源码版本，不是包含模型的一键 EXE 安装包。

## 上课时

1. 等待“本地模型已就绪”，选好麦克风，可填写课程背景和术语。
2. 点击左侧 **＋**；首次使用允许浏览器访问麦克风。
3. 看英文初稿和逐段中文；点击标题旁的铅笔改名。
4. 点击 **结束并保存**；等待中文无积压，再导出完整对照。
5. 点击 **下载录音** 保存 WAV，或从历史列表回看。
6. 再按 **＋** 开始另一堂课。退出时双击 **停止课堂翻译.cmd** 释放资源。

录音为浏览器转换后的 16kHz、16位单声道，后端音量增强前保存，约 115MB/小时。它不是硬件原采样率的高保真备份。删除应用内课堂不会删除你已经另存到其他位置的副本。

## 项目结构

```text
classroom_app.py         本机服务、英文识别与中文队列
classroom_core.py        分句、课堂存储与翻译提示
classroom_audio.py       音量增强和语音检测适配
classroom_recording.py   增量 WAV 录音与删除
classroom_web/          网页界面
tests/                  合成数据与隔离数据库测试
scripts/                安装、模型准备和发布检查
docs/                   安装、架构和许可说明
vendor/whisperlivekit/   已适配的上游源码快照及原许可证
licenses/               第三方许可证
```

`history/`、`runtime/`、`models/` 在运行时本地生成，不在仓库中。发布不含真实录音、字幕、课堂数据库、私钥、日志或大型模型。

## 复用与维护

识别基于 [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit)、[Whisper](https://github.com/openai/whisper) 和 faster-whisper/CTranslate2；翻译使用 [腾讯 HY-MT1.5](https://github.com/Tencent-Hunyuan/Hy-MT) 与 [llama.cpp](https://github.com/ggml-org/llama.cpp)。这是在现有底座上做课堂适配，未从零开发识别模型。

上游代码与修改范围见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。本项目由 He-Zixuan 维护，并非任何第三方厂商的官方产品；腾讯与本项目不存在关联、赞助或背书。

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest tests -q
```

这些测试使用合成输入和临时目录，不需要真实课堂录音，也不证明识别准确率或端到端延迟。欢迎提交复现步骤和代码修改，贡献须遵守 [贡献说明](CONTRIBUTING.md)。

**许可边界：**禁止商用的条款覆盖本项目原创应用部分，不能撤销 Apache/MIT 上游本来授予的商业使用权。本项目因此属于公开源码的非商用软件，不宣称符合 OSI 的开源定义。
