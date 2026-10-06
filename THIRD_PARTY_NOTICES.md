# Third-party components and license boundaries

The root LICENSE covers original application files, classroom_web/, tests/,
scripts/ and project documentation. It does not relicense independent
third-party components or model weights.

| Component | Location/use | Original license |
|---|---|---|
| [WhisperLiveKit](https://github.com/QuentinFuxa/WhisperLiveKit) | `vendor/whisperlivekit/`; local snapshot version 0.2.26 | [Apache-2.0](vendor/whisperlivekit/LICENSE) |
| [OpenAI Whisper](https://github.com/openai/whisper) | Upstream vendored Whisper implementation/tokenizers; separately downloaded English model | [MIT](licenses/Whisper-MIT.txt) |
| [Whisper Streaming](https://github.com/ufal/whisper_streaming) | Upstream LocalAgreement implementation | [MIT](licenses/Whisper-Streaming-MIT.txt) |
| [SimulStreaming](https://github.com/ufal/SimulStreaming) | Optional upstream streaming implementation | [MIT](licenses/SimulStreaming.txt) |
| [Silero VAD](https://github.com/snakers4/silero-vad) | Upstream detector code and small packaged VAD resources | [MIT](licenses/Silero-VAD-MIT.txt) |
| [llama.cpp](https://github.com/ggml-org/llama.cpp) | Separately downloaded Vulkan executable, not bundled | [MIT](licenses/llama.cpp-MIT.txt) |
| [Tencent HY-MT1.5](https://github.com/Tencent-Hunyuan/Hy-MT) | Separately downloaded translation model, not bundled | [Tencent HY Community License](licenses/Tencent-HY-Community.txt) |

WhisperLiveKit is authored by Quentin Fuxa and its contributors. Upstream
copyright and source notices are retained. The vendor comparison baseline is
recorded in [PROVENANCE.json](vendor/whisperlivekit/PROVENANCE.json). Files that
differ from that reference are listed there; a difference may include later
upstream changes and is not a claim that this project authored the entire file.
Classroom changes include preservation of unstable ASR text and propagation of
processing failures. All code inside this vendored package, including local
adaptations to Apache-licensed files, remains under its applicable upstream
license. Packaging changes and excluded unrelated files are recorded there too.

Python dependencies (including faster-whisper, CTranslate2, PyTorch, FastAPI,
NumPy and Transformers) are installed separately, not redistributed as wheels
in this repository. Their installed license files and upstream terms continue
to apply.

## Model terms

The root personal non-commercial license does not grant rights to model
weights. Model preparation requires the user to accept the applicable model
licenses. The Tencent license has territorial and other use restrictions;
in particular its stated Territory excludes the European Union, United Kingdom
and South Korea. Read its full terms before downloading or using the model.
The script's flag records your acknowledgment, not permission from Tencent.

Tencent HY is licensed under the Tencent HY Community License Agreement,
Copyright © 2025 Tencent. All Rights Reserved. The trademark rights of
“Tencent HY” are owned by Tencent or its affiliate.

This project is provided and maintained by He-Zixuan (an individual GitHub
maintainer). It is not an official product of Tencent, OpenAI or the upstream
projects. Tencent is not affiliated with, associated with, sponsoring or
endorsing this project. No third-party trademark rights are granted.

When using Tencent HY Works, you must comply with Sections 5(a) and 5(b) of
the included Tencent license and its Acceptable Use Policy. Nothing in this
repository permits circumvention of those restrictions. Models, recordings,
local databases, logs and runtime binaries are excluded from this publication.
