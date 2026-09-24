# Robochem-Flex 项目导读

## 1. 项目概述

Robochem-Flex 是阿姆斯特丹大学 Noël Research Group (NRG) 开发的**自动化化学反应优化平台**。它将**机器学习（贝叶斯优化）**、**硬件自动化控制**和 **Streamlit GUI** 整合为一体，实现化学反应条件的自主探索与优化。

核心理念：ML 提出实验条件 → 硬件自动执行 → 分析仪器测产率 → 结果反馈给 ML → 循环迭代直到收敛。

---

## 2. 系统架构

项目由三个核心模块组成，各司其职：

```
┌─────────────────────────────────────────────────────────┐
│                  Streamlit GUI (前端)                   │
│  用户配置实验参数、监控运行状态、手动输入结果 (HITL)        │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼──────────────────────────────────┐
│              PlatformBackend (中间层)                     │
│  翻译用户操作为硬件指令，协调 ML 与硬件的通信                │
└──────────┬───────────────────────────────┬───────────────┘
           │                               │
┌──────────▼───────────┐     ┌─────────────▼──────────────┐
│   RoBrains (ML 层)   │     │  OmniPlatypus (硬件层)      │
│  贝叶斯优化、多任务   │     │  控制泵/阀门/光源/传感器等    │
│  优化、进化算法等     │     │  管理试剂/样品/分析流程       │
└──────────────────────┘     └─────────────────────────────┘
```

### 2.1 OmniPlatypus — 硬件抽象层

路径：`Control Software/OmniPlatypus/`

负责与物理设备的通信和控制，定义了统一的设备接口。支持 4 种通信协议：

| 协议 | 设备 | 说明 |
|------|------|------|
| **串口 (Serial)** | 注射泵、采样器、LED 光源、加热板、相传感器、GPIO | Arduino 设备，9600 baud，USB 连接 |
| **Modbus RTU** | Omron E5_C 温控器 | RS-485 串口 Modbus |
| **TCP Socket** | HPLC 泵、NMR 光谱仪、拉曼光谱仪 | 以太网连接 |
| **SSH** | 树莓派 (UV/拉曼) | paramiko 远程命令执行 |

关键设备类：

- `SyringePump` — NRG 自研注射泵（Arduino + Grbl 固件）
- `Sampler` — 三轴 Cartesian 采样器（Grbl CNC 控制）
- `LightSource / LightArray` — LED 光源阵列（控制波长/强度）
- `HeatingPlate` — IKA 加热板（温度/搅拌控制）
- `HPLCClient` — HPLC 泵/autosampler（TCP socket）
- `SpinsolveClient` — Magritek Spinsolve NMR（TCP socket）
- `PhaseSensor` — 相传感器（检测液段/气泡）

设备配置文件：`OmniPlatypus/OmniPlatypus/omniplatypus/config/platform_config.json`
定义了平台 "Perry" 的所有设备、串口/IP 地址、物理常量（管路体积、清洗参数等）。

### 2.2 RoBrains — 机器学习层

路径：`Control Software/backend/Robochem_ML/robrains/`

提供 7 种优化策略：

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `SingleBayesianOpti` | 单目标贝叶斯优化（全自动） | 有分析仪器，全自动闭环 |
| `SingleBayesianOptiHITL` | 单目标贝叶斯 + 人在回路 | 无分析仪器，人手动输入结果 |
| `EfficientBatchedBO_HITL` | 高效批量贝叶斯 + HITL | 需要批量实验的场景 |
| `MultiTaskScope` | 多任务优化 | 同时优化多个反应范围 |
| `MultiTaskScope_HITL` | 多任务 + HITL | 多任务 + 手动输入 |
| `EnantioExtravaganza` | 手性优化 | 对映/非对映选择性优化 |
| `ScopeAcceleratorTask` | 加速范围探索 | 快速扫描大范围条件空间 |

可优化的目标函数：yield（产率）、conversion（转化率）、selectivity（选择性）、enantiomeric excess（对映体过量）、cost（成本）、throughput（通量）等 13 种。

ML 后端基于 BoTorch / GPyTorch，使用高斯过程 (GP) 模型 + 采集函数 (UCB/EI) 进行贝叶斯优化。支持连续变量（浓度、时间、温度）和离散变量（催化剂种类、溶剂种类，通过 Embedding 编码）。

### 2.3 LAMAS — 光谱分析层

路径：`Control Software/Lamas/`

提供光谱去卷积和分析功能，支持 NMR、LCMS、拉曼等分析数据的处理。

---

## 3. 安装指南（Linux）

### 3.1 注意事项

- `robochem_flex.yml` 是从 **Windows** 环境导出的，包含 `pywin32`、`ucrt`、`m2w64-*` 等 Windows 专用包，**在 Linux 上无法使用**。
- 应使用 `robochem_flex_alt.yml` 的依赖列表安装。
- conda 在收集元数据时可能卡住（网络原因），建议用 `uv` 替代。

### 3.2 推荐安装方式

```bash
# 1. 用 uv 创建 Python 3.12 虚拟环境
uv venv --python 3.12 "Control Software/.venv"

# 2. 安装所有依赖
VIRTUAL_ENV="Control Software/.venv" uv pip install \
    python-dotenv numpy pandas "streamlit==1.38" seaborn openpyxl \
    pillow pymoo colorama pre-commit torch botorch gpytorch black \
    paramiko fastapi pyDOE "uvicorn[standard]" \
    "bronkhorst-propar==1.2.0" "nmrglue==0.11" "pause==0.3"

# 3. 安装 pip（venv 默认没有）
VIRTUAL_ENV="Control Software/.venv" uv pip install pip

# 4. 安装项目子模块（editable 模式）
cd "Control Software"
.venv/bin/pip install -e backend/Robochem_ML/
.venv/bin/pip install -e Lamas/
.venv/bin/pip install -e OmniPlatypus/OmniPlatypus/
```

### 3.3 路径修复

在 Linux 上运行需要修复 `backend/platform_backend.py` 中的硬编码相对路径：

```python
# 原始（Windows 相对路径，仅从特定目录运行时有效）：
platform_config_path = os.path.join("omniplatypus", "omniplatypus", "omniplatypus", "config", "platform_config.json")

# 修复后（基于 __file__ 的绝对路径）：
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
platform_config_path = os.path.join(_base_dir, "OmniPlatypus", "OmniPlatypus", "omniplatypus", "config", "platform_config.json")
```

---

## 4. 运行方式

### 4.1 启动

```bash
source "Control Software/.venv/bin/activate"

conda activate roboche_lt
cd "Control Software"
streamlit run robochem_flex.py
```

启动后会打开两个浏览器标签：
- `http://localhost:8501` — 主 GUI 界面
- ML 日志面板 — 实时显示优化后端状态

### 4.2 两种运行模式

#### 模式 A：无硬件模拟 (Dry Run)

适用于：验证软件流程、演示、开发调试。

```
ML 提条件 → 显示在 GUI → 人手动填 yield → 点 "Push Results" → ML 继续
```

- 使用 `Examples/CS0_dryrun/session.json` 定义的是参数的搜索空间和配置
- `platform_experiment` 为 `"PhotochemicalReaction - dry run"`，跳过硬件连接
- `analysis_type` 为 `"Human"`，由人代替分析仪器输入产率
- 填入的 yield 值应有策略（如用虚拟目标函数），而非随机数，才能观察到有意义的优化趋势

#### 模式 B：全自动闭环（需物理设备）

适用于：真实化学反应优化。

```
ML 提条件 → 泵自动配液 → 光化学反应 → NMR/LCMS 自动分析 → 自动算 yield → ML 继续
```

- 使用 `Examples/CS0/` 或其他 session
- `platform_experiment` 为 `"PhotochemicalReaction"`，启动时连接所有硬件
- 分析仪器自动输出产率，无需人工干预
- 人只需装好试剂、开机、点 Start

### 4.3 全自动闭环的数据流（连接真实设备时）

当连接真实设备且分析方法不是 `"Human"` 时，系统实现完全自动的"反应→分析→优化"闭环。核心流程在 `chemistry.py` 的 `_procedure_experiment()` 中：反应结束后，泵将 slug 推送到分析仪器，仪器自动测量并计算产率，结果存入 `RunResult` 放入结果队列；`ml_platform.py` 的主循环持续从队列取结果，通过 `_from_machine()` 转为 ML 张量，批次完成时触发 GP 模型更新，提出新条件提交下一轮实验。

#### 完整闭环一图流

```
ML (RoBrains)                    OmniPlatypus (硬件层)
     │                                  │
     │  ① submit_run(conditions)        │
     │ ──────────────────────────────→  │
     │                                  │  ② 泵配液 → 反应器 → 反应
     │                                  │
     │                                  │  ③ 分析仪器自动测量
     │                                  │     NMR: SpinsolveClient → 谱图
     │                                  │     → 寻峰 → 积分 → 浓度 → yield
     │                                  │
     │  ④ get_result() ← RunResult      │
     │ ←──────────────────────────────  │     result = {"yield": 72.5}
     │                                  │
     │  ⑤ _from_machine() → y=tensor    │
     │  ⑥ update() → GP 模型更新         │
     │  ⑦ out_data() → 新条件            │
     │ ──────────────────────────────→  │  ⑧ 下一轮实验...
     │                                  │
     └────── 自动循环直到收敛 ────────────┘
```

#### 涉及的关键文件

| 文件 | 职责 |
|------|------|
| `OmniPlatypus/.../experiments/chemistry.py` | 反应流程控制，调用分析仪器 |
| `OmniPlatypus/.../analytics/` | NMR / Raman / HPLC 分析：谱图处理 → 产率计算 |
| `backend/ml_backends.py` | 硬件结果 ↔ ML 张量转换 |
| `robrains/.../ml_platform.py` | ML 主循环：取结果 → 更新模型 → 提新条件 |

---

### 4.4 GUI 操作流程

左侧导航栏共 6 个页面，按顺序操作：

| 页面 | 功能 |
|------|------|
| **Home** | 上传 `session.json` 恢复实验，或从零开始 |
| **User Settings** | 设置用户名、实验名、选择平台 (Perry) 和实验类型、选择 ML 策略 |
| **Physical Parameters** | 配置物理参数范围（停留时间、光照强度等） |
| **Reagents** | 定义试剂（底物/催化剂/溶剂）、配置 stock solution、映射 vial 位置 |
| **Analysis** | 设置分析方法（NMR 峰位、LCMS 保留时间、或 Human 手动模式） |
| **Machine Learning** | 设定优化变量范围、选择目标函数、配置 GP 模型参数 |
| **Run Platform** | Save Session → Start → 监控运行 → 查看实时结果和图表 |

---

## 5. 数据文件结构

每个实验 session 由三个文件组成：

```
Session_Folder/
├── session.json          # 核心配置：ML 模型、参数、试剂、分析设置
├── StockSolutionDF.csv   # 试剂库存：每种 stock 的溶剂和浓度
└── VialDF.csv            # Vial 映射：试剂在物理托盘上的位置
```

- `session.json` 由 GUI 自动生成，不建议手动编辑
- 三个文件必须放在同一目录下，它们相互引用、不可分离

### 5.1 session.json 核心字段

| 字段 | 说明 |
|------|------|
| `platform_name` | 硬件平台标识（如 `"Perry"`） |
| `platform_experiment` | 实验类型（`PhotochemicalReaction` / `ThermochemicalReaction`） |
| `experiment_type` | ML 策略（`BO_optimisation` / `BO_optimisation_HITL` 等） |
| `experiment_class` | ML 模型配置：采集函数、迭代次数、批量大小、目标函数等 |
| `*_ml` 字段 | **待优化的工艺参数**（`ML_parameter` 类型），见 5.2 节 |
| `PhysicalParameter` 字段 | 设备物理参数（提供硬约束边界） |
| `Chemical` 字段 | 化学品定义（名称、CAS 号、角色） |
| `AnalyParameter` 字段 | 分析仪器参数（目标峰位、积分方法等） |
| `StockDF` | 指向 `StockSolutionDF.csv` 的引用 |
| `VialDF` | 指向 `VialDF.csv` 的引用 |

### 5.2 待优化工艺参数（`*_ml` 字段）

session.json 中所有以 `_ml` 结尾、`class` 为 `"ML_parameter"` 的字段就是**待优化的工艺参数**。它们是 ML 引擎实际搜索的变量。

以 CS1 为例，共有 6 个 ML 参数：

| 字段名 | 含义 | 范围 (`min_value` ~ `max_value`) | 类型 |
|--------|------|----------------------------------|------|
| `Limiting Reagent_ml` | 限量试剂浓度 | 100 ~ 200 mM | 连续 |
| `Catalyst_ml` | 催化剂选择 | 5 种候选（离散） | 分类（Embedding 维度 3） |
| `Excess Reagent_ml` | 过量试剂当量 | 0.9 ~ 3.5 eq | 连续 |
| `Other Reagent_ml` | 添加剂选择 | 2 种候选（离散） | 分类（Embedding 维度 1） |
| `residence_time_ml` | 停留时间 | 120 ~ 1800 S | 连续 |
| `light_intensity_ml` | 光照强度 | 0 ~ 100 % | 连续 |

**ML 参数与物理设备的对应关系**：

6 个 ML 参数中，4 个为物料/化学参数，2 个直接控制物理设备：

| ML 参数 | 分类 | 对应硬件设备 | 控制链路 |
|---------|------|------------|----------|
| `Limiting Reagent_ml` | 物料 | 采样器 + 注射泵（间接） | 浓度 → 采样器选储液瓶 + 计算吸取体积 |
| `Catalyst_ml` | 物料 | 采样器（间接） | 选择对应催化剂储液瓶 |
| `Excess Reagent_ml` | 物料 | 采样器 + 注射泵（间接） | 当量 → 计算吸取体积 |
| `Other Reagent_ml` | 物料 | 采样器（间接） | 选择对应添加剂储液瓶 |
| **`residence_time_ml`** | **设备** | **注射泵 (Main_Pump_1)** | **停留时间 = 反应器体积 / 流速 → 控制泵流速** |
| **`light_intensity_ml`** | **设备** | **LED 光源 (Light_Array)** | **直接设定光源功率百分比** |

所有参数最终都会驱动物理设备，但物料参数通过 `_to_machine()` 转化为采样器的选瓶和吸液操作（间接驱动），而 `residence_time` 和 `light_intensity` 则直接控制设备的运行状态。若接入康宁反应器等新设备，`residence_time_ml` 的控制链路将从 NRG 注射泵变为康宁反应器的流量控制接口。

每个 `ML_parameter` 的核心字段：

- `min_value` / `max_value` — 用户设定的优化搜索上下界
- `default_min` / `default_max` — 设备硬约束（来自 PhysicalParameter），用户范围不可超出
- `discrete` — 分类参数的所有候选项
- `phy_chem` — `"Chemical"`（化学参数）或 `"Physical"`（物理参数）
- `discrete_embed_dim` — 离散变量的 Embedding 维度

参与优化的参数列表记录在 `experiment_class.ML_parameters` 中：

```json
"experiment_class": {
    "ML_parameters": [
        "Limiting Reagent_ml",
        "Catalyst_ml",
        "residence_time_ml",
        "light_intensity_ml"
    ],
    "targets": ["yield"]
}
```

### 5.3 参数体系：设备参数与工艺参数的关系

系统采用三层参数架构，设备参数定义物理极限，工艺参数在其内划定优化范围：

```
┌─────────────────────────────────────────────────────────┐
│  第 1 层：设备硬约束（OmniPlatypus 实验类定义）            │
│  PhysicalParameter._required / _optional_parameters     │
│  由实验类型（光化学/热化学）决定，代表设备物理极限           │
├─────────────────────────────────────────────────────────┤
│  第 2 层：用户优化范围（session.json 中 *_ml 字段）        │
│  ML_parameter.min_value ~ ML_parameter.max_value         │
│  必须在设备硬约束之内，是 ML 实际搜索的空间                 │
├─────────────────────────────────────────────────────────┤
│  第 3 层：ML 内部归一化                                   │
│  translation_continuous: 用户范围 → [0, 1] 归一化         │
│  back_translation_continuous: [0, 1] → 实际值            │
└─────────────────────────────────────────────────────────┘
```

**设备参数**（`class: "PhysicalParameter"`）由 OmniPlatypus 的实验类定义硬约束：

| 参数 | 所属实验类型 | 设备硬约束范围 | 单位 |
|------|------------|---------------|------|
| `residence_time` | 通用（ChemicalReaction） | 30 ~ 100000 | S |
| `slug_volume` | 通用（可选） | 100 ~ 1000 | uL |
| `flowrate_sampling` | 通用（可选） | 0.1 ~ 10.0 | mL/min |
| `light_intensity` | 光化学 (PhotochemicalReaction) | 0 ~ 100 | % |
| `temperature` | 热化学 (ThermochemicalReaction) | 15 ~ 100 | °C |
| `stirring` | 热化学（可选） | 0 ~ 1500 | rpm |

**工艺参数**（`class: "ML_parameter"`）在设备约束内由用户设定优化范围。例如：

- 设备允许停留时间 30 ~ 100000 S，用户在 session.json 中将 `residence_time_ml` 的范围设为 120 ~ 1800 S
- 设备允许光照强度 0 ~ 100%，用户可设为全范围或子范围

**`style` 字段决定参数是否参与优化**：

- `style = "variable"` — 参与优化，自动生成对应的 `*_ml` 参数
- `style = "constant"` — 固定值，不参与优化（如 CS1 的 `slug_volume` 固定 600 uL）

**参数流转**：设备 PhysicalParameter → 用户设定 ML_parameter 范围 → 归一化到 [0,1] → 贝叶斯搜索 → 反归一化 → 发送给硬件执行。

### 5.4 StockSolutionDF.csv — 储备液清单

每行代表一瓶物理配制的储备液：

| 列名 | 说明 |
|------|------|
| `StockID` | 唯一标识（Stock_0, Stock_1, ...） |
| `Solvent` | 溶剂名称（须与 session.json 中的 Chemical 对应） |
| `Conc_<化学名>` | 各溶质的浓度（mM），每个化学品一列 |

### 5.5 VialDF.csv — 样品瓶物理布局

每行代表一个机器人可访问的样品瓶：

| 列名 | 说明 |
|------|------|
| `VialID` | 唯一标识（如 0x001） |
| `VialName` | 可读名称（如 SM, catalyst, Sample_1） |
| `StockID` | 关联的储备液（引用 StockSolutionDF 中的 StockID） |
| `Volume` | 液体体积（µL） |
| `Sampler` | 交互的机器人模块（Sampler_cnc / Collector_cnc） |
| `Holder` | 所在托盘（holder_A ~ holder_F） |
| `Position` | 托盘内坐标（如 A1, B3） |
| `Type` | 类型（Stock / Solvent / Cleaning / Gas / Mixing / Sample） |
| `Viable` | 是否可用（TRUE / FALSE） |

---

## 6. 示例实验详解

`Examples/` 目录包含 9 个预配置的 session，涵盖了不同反应类型、分析手段和优化策略的组合。每个 session 包含 `session.json`、`StockSolutionDF.csv` 和 `VialDF.csv` 三个文件。

### 6.1 总览

| 案例 | 反应类型 | 分析手段 | 优化策略 | ML 模型 | 目标 | 特色 |
|------|---------|---------|---------|---------|------|------|
| CS0 | 光化学 | Human | BO_HITL | SingleTaskGP | yield | 最简入门示例 |
| CS0_dryrun | 光化学（干运行） | Human | BO_HITL | SingleTaskGP | yield | 无硬件模拟测试 |
| CS1 | 光化学 | NMR | BO | SingleTaskGP | yield + residence_time | 5 种催化剂筛选，多目标加权 |
| CS2 | 光化学 | UPLC | BO | **RandomForest** | integral_product + integral_sideproduct | 随机森林模型，副产物控制 |
| CS3 | 光化学 | **Raman** | BO | **NoisySingleTaskGP** | yield + conversion | 同位素交换，含校准模型文件 |
| CS4 | **热化学** | Human | **EfficientBatchedBO_HITL** | SingleTaskGP | yield | 温度变量，高效分批优化 |
| CS5_1 | 热化学 | NMR | BO | SingleTaskGP | yield | 优化阶段 |
| CS5_2 | 热化学 | NMR | **ScopeAcceleratorTask** | — | yield | 底物范围拓展（多任务迁移学习） |
| CS6 | 光化学 | Human | BO_HITL | SingleTaskGP | yield + ee + dr | 三目标立体选择性优化 |

### 6.2 各案例详解

#### CS0 — 基础光化学反应（入门示例）

- **化学体系**：3 种试剂 — SM（限量试剂）、THF（过量试剂）、TBADT（催化剂），溶剂 MeCN
- **储备液**：3 瓶（SM 1000 mM、THF 8000 mM、TBADT 17 mM），共 43 个 vial
- **ML 优化参数**（5 个）：限量试剂浓度 (50–200 mM)、过量试剂当量 (1–18 eq)、催化剂当量 (0.005–0.03 eq)、停留时间 (60–1200 s)、光照强度 (0–100%)
- **ML 配置**：SingleTaskGP + UCB 采集函数，40 个总点数，每批 5 个实验
- **分析方式**：人工分析（HITL 模式），需手动输入产率
- **物理设备**：涉及 9 台设备（详见第 7 节）

#### CS0_dryrun — 干运行测试

与 CS0 化学体系完全相同，但 `platform_experiment` 标记为 `"PhotochemicalReaction - dry run"`，不连接任何硬件，用于模拟测试软件流程。

#### CS1 — 复杂光化学催化筛选（多催化剂 + NMR）

- **化学体系**：10 种试剂，显著更复杂
  - 1 种限量试剂 (SM)
  - **5 种候选催化剂**：Ru(bpy)Cl、Ru(bpy)PF6、Ir(ppy)、Ir(CF3)ppy、5CzBN（离散选择，Embedding 维度 3）
  - 1 种过量试剂 (TFAA)
  - **2 种候选添加剂**：PyNO、4-PhPyNO（离散选择，Embedding 维度 1）
- **储备液**：9 瓶（每种催化剂单独一瓶，浓度 3 mM），共 53 个 vial
- **分析方式**：**NMR**（氟谱 `1D FLUORINE HDEC`，中心频率 -60 ppm，目标峰 -57.94 ppm，校准系数 1654.9 mM/AU）
- **ML 配置**：SingleTaskGP + UCB，自适应策略，50 个总点数，每批 1 个
- **多目标优化**：产率 (yield) + 停留时间 (residence_time)，权重 [0.9, -0.1]（最大化产率、最小化停留时间）

#### CS2 — 光化学反应（UPLC 检测 + 随机森林模型）

- **化学体系**：9 种试剂，含 2 种催化剂 + 2 种共催化剂
- **分析方式**：**UPLC**（超高效液相色谱）
- **ML 配置**：**RandomForest**（随机森林，100 棵树）+ qEHVI 采集函数，80 个总点数
- **多目标优化**：`integral_product`（主产物积分）+ `integral_sideproduct`（副产物积分）
- **特点**：唯一使用随机森林模型（而非高斯过程）的案例，关注主产物/副产物平衡

#### CS3 — 同位素交换反应（Raman 检测 + 校准模型）

- **化学体系**：同位素交换反应
  - 限量试剂：4-Bromo-Benz
  - 过量试剂：D₂O（重水）
  - 2 种候选催化剂：BP_H、BP_F（Embedding 维度 1）
  - **4 种候选共催化剂**：thiol_1–thiol_4（Embedding 维度 2）
- **分析方式**：**Raman 光谱**（积分时间 38s，20 次平均，等吸收点法 `isosbestic_integral`）
- **独有文件**：`integral_models.linear_model` — Raman 积分校准模型
- **ML 配置**：**NoisySingleTaskGP**（适配高噪声 Raman 数据）+ qEHVI，36 个总点数
- **多目标优化**：产率 (yield) + 转化率 (conversion)

#### CS4 — 热化学反应（高效分批 HITL）

- **反应类型**：**热化学反应** (`ThermochemicalReaction`) — 唯一的热化学案例，使用温度而非光照
- **分析方式**：人工分析（HITL 模式）
- **ML 配置**：`EfficientBatchedBO_HITL`，使用双采集函数策略（UCB 开发 + MaxVariance 探索），100 个总点数，每批 2 个
- **ML 优化参数**（7 个）：限量试剂、**温度**、过量试剂、添加剂、共催化剂、催化剂、停留时间

#### CS5_1 / CS5_2 — 热化学反应（优化 + 范围拓展）

这两个案例使用相同化学体系，代表优化流程的两个阶段：

- **CS5_1**（优化阶段）：使用 `SingleBayesianOpti` + NMR 分析，全自动优化寻找最优条件
- **CS5_2**（范围拓展阶段）：使用 `ScopeAcceleratorTask`（多任务迁移学习），在 CS5_1 优化结果基础上探索反应的底物适用范围 (scope)

#### CS6 — 不对称光化学反应（三目标 HITL）

- **化学体系**：最复杂的体系之一，含 **8 个 ML 参数**
  - 限量试剂、过量试剂、催化剂、共催化剂、**配体 (Ligand)**、**共溶剂 (Co-Solvent)**、光照强度、停留时间
- **分析方式**：人工分析（HITL 模式）
- **ML 配置**：SingleTaskGP + qEHVI，32 个总点数
- **三目标优化**：产率 (yield) + **对映体过量 (enantiomeric excess)** + **非对映体比 (diastereomeric ratio)**
- **特点**：唯一涉及立体选择性优化的案例

### 6.3 分析手段与迭代模式的关系

分析手段决定了优化循环的**通信模式**：

| 分析手段 | 对应的 experiment_type | ML 通信模块 | 迭代方式 |
|---------|----------------------|-------------|----------|
| NMR / UPLC / Raman | `BO_optimisation` | `ML_Platform` | **全自动闭环**：仪器自动返回数据 → 自动触发 `update()` → 自动提议下一组条件 |
| Human | `*_HITL` | `ML_Platform_HITL` | **半自动**：硬件执行完一批后等待人工审核/输入结果 → 才触发 `update()` → 继续下一批 |

- **仪器分析**（NMR/UPLC/Raman）：分析结果由仪器自动计算并返回产率，系统在 `ML_Platform._run()` 循环中持续从硬件取结果、更新模型、提出新条件，实现完全闭环
- **人工分析**（Human）：系统在 `ML_Platform_HITL._process_visual_queue()` 中阻塞等待，直到用户通过 GUI 前端提交审核后的数据

**规律**：非人工分析手段 → 全自动迭代；人工分析 → 每批需人工确认后才继续。

---

## 7. 液滴流化学：设备与物质流

Robochem-Flex 采用 **Slug Flow Chemistry（液滴流化学）** 架构：以液滴（slug）为离散反应单元，各试剂通过采样器按顺序吸入主流路，以 N₂ 气泡间隔分隔，在管路中形成连续的 slug 序列，依次流经混合、反应、分析、收集各模块。

### 7.1 CS0 涉及的物理设备

以 CS0（`PhotochemicalReaction`）为例，共涉及 **9 台物理设备**（不含分析仪器时）：

| # | 设备名 | 类型 | 功能 |
|---|--------|------|------|
| 1 | **Main_Pump_1** | 注射泵 | 驱动主流路液体流动（N₂ + 试剂 slug） |
| 2 | **Sampler_pump** | 注射泵 | 为采样器提供负压吸液 |
| 3 | **Sampler_cnc** | 三轴采样器 | 精确定位到试剂瓶，按体积吸取试剂注入主流路 |
| 4 | **Collector_cnc** | 三轴收集器 | 反应完成后收集产物液滴到样品管 |
| 5 | **Gpio_Array_1** | GPIO 阀阵列 | 控制气路通断（N₂ 鼓泡间隔、流路切换） |
| 6 | **Phase_Sensor_Array_1** | 相传感器组 | 检测主流路前端液滴/气泡到达（注入前定位） |
| 7 | **Phase_Sensor_Array_2** | 相传感器组 | 检测反应后液滴到达收集器位置 |
| 8 | **Light_Array** | LED 光源阵列 | 提供可调波长/强度的光照（光化学反应核心） |
| 9 | **heating_plate_IKA** | 加热板 | 温度控制（CS0 未使用，但属于基础设备池） |

此外，根据 `analysis_type` 配置，还可能接入 **NMR**（SpinsolveClient）、**UPLC**（HPLCClient）或 **Raman**（RamaBerry）分析仪器。

设备配置定义在 `platform_config.json` 中，实验类型通过 `_required_devices` 列表声明所需设备。

### 7.2 新增设备的可行性

若需将一台未注册的新设备加入 CS0，根据接入方式分为两种场景：

**场景 A：旁路设备（中等难度）**

新设备不在 slug 主流路中，而是作为辅助模块（如额外的在线检测器、pH 传感器等）。

- 在 `platform_config.json` 中注册设备（串口/IP、类型等）
- 编写设备驱动类（继承 OmniPlatypus 基类）
- 修改实验类的 `_required_devices` 添加新设备
- 无需修改反应流程逻辑

**场景 B：串联设备（高难度）**

新设备需要插入 slug 主流路中（如在反应器和分析仪器之间增加一个萃取模块）。

- 除场景 A 的所有步骤外，还需修改 `_procedure_experiment()` 中的反应流程拓扑
- 需要更新管路体积、流速等物理参数
- 需要验证时序兼容性（slug 在不同设备间的传输时间）
- 本质上是在重新设计反应流程，需要深入理解 slug flow 的时序控制

---

## 8. 关键目录结构

```
Robochem_Flex/
├── Control Software/
│   ├── robochem_flex.py              # Streamlit 入口
│   ├── backend/
│   │   ├── platform_backend.py       # 中间层：协调 ML 与硬件
│   │   ├── ml_backends.py            # ML 策略的封装层
│   │   ├── frontend_functions.py     # GUI 辅助函数
│   │   ├── frontend_results.py       # 结果展示与 HITL 输入
│   │   └── Robochem_ML/robrains/     # ML 核心算法
│   ├── OmniPlatypus/                 # 硬件抽象层
│   │   └── OmniPlatypus/omniplatypus/
│   │       ├── devices/              # 设备驱动（串口/Modbus/TCP/SSH）
│   │       ├── config/               # 平台配置文件
│   │       └── procedures/           # 实验流程模板
│   ├── Lamas/                        # 光谱分析层
│   └── pages/                        # Streamlit 多页面
├── Examples/                         # 预配置实验 session
├── Data Analysis/                    # 数据分析与可视化
└── Devices/                          # 硬件设计文档（3D 模型、固件、PCB）
```
