# IOMap

本地电气图阅读与 IO 点位核对工具：上传 PDF，提取 IO 地址、模块、Pin、现场设备编号和描述，对照原图修改，再导出 Excel。

当前版本 **v0.2**，适合生成工作初稿并进行人工 double check。PDF、OCR 和编辑数据在本机处理；可选翻译模型下载后也在本机运行。

## 功能

- 上传 PDF（最多 100MB、1000 页），选择要提取的 PDF 页码范围。
- 自动选择文字提取或 Tesseract OCR，也支持强制 OCR。
- 提取五列 I/O LIST，以及 ROMACO/Schneider SLOT 电路图中的通道信息。
- 用同一 PDF 中的 I/O LIST 交叉校验通道地址、Pin 和描述，记录证据来源。
- 点击记录定位原图高亮，缩放查看，编辑字段、补充遗漏、删除误识别项。
- 保存核对状态和人工修改；程序重启后可以继续打开已完成项目。
- 导出双语表头的 **IO总表、待核对项、模块汇总**，按当前数据重新计算。
- 可选英文→中文本地翻译，支持术语表、缓存，保留原文和已有译文。

## 快速开始：Windows + Anaconda

建议使用 Python 3.12。在 Anaconda Prompt 或已初始化 Conda 的 PowerShell 中运行：

```powershell
conda create -n IOMAP python=3.12 -y
conda activate IOMAP
git clone https://github.com/XJSCREAM/IOMap.git
cd IOMap
python -m pip install -r requirements.lock.txt
conda install -c conda-forge tesseract -y
```

检查 OCR 引擎及语言数据：

```powershell
tesseract --version
tesseract --list-langs
```

语言列表需要包含 `eng`。如果没有，在 PowerShell 下载官方英语语言数据并为当前 Conda 环境设置目录：

```powershell
$tessDir = Join-Path $env:CONDA_PREFIX "tessdata"
New-Item -ItemType Directory -Force -Path $tessDir | Out-Null
Invoke-WebRequest -Uri "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata" -OutFile (Join-Path $tessDir "eng.traineddata")
conda env config vars set "TESSDATA_PREFIX=$tessDir"
conda deactivate
conda activate IOMAP
tesseract --list-langs
```

启动网页应用：

```powershell
$env:IOMAP_PORT = "0"
python app.py
```

在本机浏览器打开终端 `Running on ...` 显示的地址。端口设为 `0` 时由系统选择可用端口，避免 Windows 端口占用或保留范围问题。保持终端运行；按 Ctrl+C 关闭服务。应用默认只绑定本机回环地址，适用于本机测试和工作辅助。

使用 Anaconda 时直接执行上述命令；`install.bat` 和 `start.bat` 是另一种使用 `.venv` 的安装方式，不需要混用。

## 其他安装方式

### Windows 普通 Python

安装 Python 和 Tesseract 5，将 Tesseract 加入 PATH，并确保英语语言数据可用。运行 `install.bat`，然后运行 `start.bat`；默认端口为 5000。

### Linux / macOS

先安装 Tesseract 与所需语言数据。Ubuntu/Debian 示例：

```bash
sudo apt-get install tesseract-ocr tesseract-ocr-eng
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock.txt
./start.sh
```

macOS 可通过 `brew install tesseract` 安装 OCR 引擎。Windows 和 macOS 安装说明尚未完成实机验证；当前自动化验证在 Linux 上执行。

## 工作流程

1. 上传 PDF，输入可选范围，例如 `59-100`；这是 **PDF 页码**，不是图纸标注的页号。
2. OCR语言默认 `eng`。其他语言需先安装对应 Tesseract 数据，再填写 `eng+ita` 等组合。
3. 等待处理结束，检查页面提取报告中的失败页和没有检出候选的页。
4. 点击记录，对照原图核对地址、模块、Pin、设备和描述。填写“使用状态”与“核对状态”，保存修改。
5. 使用“补充本页记录”和“删除误识别项”修正遗漏及误检。
6. 导出 Excel，继续在表格中核对。Excel 中的后续修改不会自动回写网页项目。

提取结果与人工编辑保存在 `data/`。备份该目录即可保存本机项目。提取中断后需要重新上传；软件不会把中断任务报告为已完成。

## 提取规则与边界

- 普通 SLOT 电路图按通道列匹配信息，不把相邻通道的地址和 Pin 当成描述。
- 即使只输出部分页，也会读取同一 PDF 其他页的 I/O LIST 作交叉校验。备注记录列表来源页与图纸引用。
- 模块和地址的列表匹配必须唯一；Pin 冲突、描述差异会标注待核对。
- `AO5.11` 等标记在当前支持的图纸中是物理连接器 Pin，缺少 PLC 地址时地址列留空；0V 标为公共端子。
- DEVICE 来自同列设备标签或交叉引用端点；端点可能是中间设备，不能据此认定最终现场设备。
- 未关联设备候选保留在待核对项，不计入 IO 总表或模块汇总。
- 通用文字/OCR候选无法可靠关联描述时留空，附近文字只放在备注中作为核对证据。
- 表格记录可能包含备用、电源和公共端子，记录数量不等于物理 IO 通道数量。
- 当前针对一种图纸版式优化；其他厂商版式可能只能提取候选，需后续扩展。
- OCR 可能混淆 `I`、`1`、`l`、下划线。自动数字纠正保留提取原文并标注备注。自动结果均默认待核对。

## 可选：本地翻译

使用 Argos Open Tech 英中模型，通过 CTranslate2 在 CPU 上推理，无需 API Key。首次下载需要访问 `argos-net.com`；模型许可证以下载包和发布来源为准。

```bash
python download_model.py
```

下载后可在网页点击“本地翻译中文”，或翻译导出的 B 方案 Excel：

```bash
python translate_excel.py input.xlsx translated.xlsx
```

默认输入是意大利语/英语双行描述，使用第二行英语；纯英文工作簿添加 `--source-layout en`。语言边界不明确的多行描述不自动猜测。已有译文不会覆盖；输出必须使用新文件名。

`glossary.en-zh.json` 保存完整短句术语表；`.cache/` 缓存原文和译文，可逐步加入人工认可的翻译。当前只准备英文→中文语言对。译文仍需人工核对。

模型下载在开发云环境中遇到网络代理 HTTP 403，**真实模型推理尚未验证**。未安装模型不影响 PDF 上传、OCR、编辑和 Excel 导出。

## 验证

在安装了依赖的环境中运行：

```bash
python -m unittest discover -s tests -v
```

当前 Linux 环境通过 8 项测试，覆盖扫描 PDF OCR、上传、编辑持久化、Excel 导出、通道列提取、模拟量 Pin 分类、候选分离和翻译文件处理。OCR 测试需要 Tesseract 与测试字体，缺少时明确跳过；翻译测试使用替身验证表格行为，不验证模型质量。

代表性图纸验证：

| 范围 | 结果 |
| --- | --- |
| PDF 第151–185页 I/O LIST | 451 条表格记录，含辅助端子 |
| PDF 第59–100页电路图 | 204 条数字 IO、12 条模拟量/公共端子记录 |
| 数字 IO 交叉校验 | 204 条地址、Pin 和描述与同文档 I/O LIST 对应一致 |
| 浏览器流程 | 上传、原图高亮、缩放、保存修改、下载 Excel 通过 |

上述校验不代表现场设备关联或电气连通关系准确率。用户图纸和导出数据没有作为测试资产包含在源码中。

## 升级与配置

关闭程序、备份项目，再更新代码。保留 `data/`、`.cache/`、`models/` 和环境目录。旧项目不会自动重算，提取规则更新后重新上传 PDF 创建新项目。

| 设置 | 用途 |
| --- | --- |
| `IOMAP_PORT` | 服务端口，默认 5000；0 表示自动选择 |
| `IOMAP_DATA_DIR` | 可选的数据目录，默认项目下的 `data/` |
| `TESSDATA_PREFIX` | Tesseract 语言数据目录 |

用户图纸、导出表格、虚拟环境、缓存及模型权重由 `.gitignore` 排除。首次安装依赖、OCR语言数据及可选翻译模型需要联网；文档处理在本机执行。
