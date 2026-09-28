# U3900H UV-Vis 光谱仪与 Robochem-Flex 集成文档

> 日立 U-3900H 分光光度计在 Robochem-Flex 自驱动实验室平台中的集成架构、运行流程与已知问题。

---

## 1. 架构总览

### 1.1 模块关系

```
Robochem_Flex/
├── U3900H/                              ← 协议开发/测试工具集
│   ├── virtual_spectrometer_server.py   ← 虚拟光谱仪服务端 (TCP:9100 + HTTP:4090)
│   ├── spectrometer_client.py           ← 独立调试客户端 (TCP:9100 + HTTP:5001)
│   ├── U3900H_协议文档.md               ← 协议帧格式与命令手册
│   ├── test_driver_basic.py             ← 驱动基础闭环测试
│   ├── test_bo_u3900h.py               ← 贝叶斯优化驱动设备样例
│   ├── simulate_frontend_flow.py        ← 前端分析页面模拟
│   ├── verify_frontend.py               ← Streamlit 后端验证
│   ├── check_uv_registration.py         ← UV 注册检查
│   └── templates/                       ← Web 仪表盘模板
│       ├── server_dashboard.html
│       └── client_dashboard.html
│
├── Control Software/
│   ├── robochem_flex.py                 ← Streamlit 主入口
│   ├── backend/
│   │   └── platform_backend.py          ← 平台后端 (自动启动虚拟光谱仪)
│   └── OmniPlatypus/
│       └── omniplatypus/
│           ├── devices/nrg/
│           │   └── u3900h_spectrometer.py   ← 生产设备驱动 (继承 BaseDevice)
│           ├── procedures/analytics/
│           │   └── u3900h_analytics.py      ← UV-Vis 分析逻辑 (产率计算)
│           ├── procedures/experiments/
│           │   ├── photochemistry.py        ← 光化学实验 (注册 UV 分析)
│           │   └── chemistry.py             ← 化学实验基类 (注册 UV 分析)
│           ├── devices/platform.py          ← 设备注册表 (device_constructors)
│           └── config/platform_config.json  ← 平台配置 (UV_Spectrometer 设备)
│
└── Examples/
    └── CS0_UV_optimisation/             ← UV 优化示例会话
        ├── session.json
        ├── StockSolutionDF.csv
        └── VialDF.csv
```

### 1.2 三层架构

| 层次 | 组件 | 职责 |
|---|---|---|
| **协议层** | `virtual_spectrometer_server.py` + `U3900HSpectrometer` 驱动 | TCP 通信、协议帧编解码、设备状态管理 |
| **分析层** | `AnalyticsU3900H` | 光谱采集、积分计算、Beer-Lambert 浓度/产率 |
| **编排层** | `PlatformBackend` + `ExperimentAnalysisCoupler` + `SingleBayesianOpti` | 实验调度、ML 优化、闭环控制 |

---

## 2. 数据流与调用链

### 2.1 完整调用链

```
用户操作 (Streamlit 前端)
  │
  ├─ 上传 session.json → load_session() → 解析 AnalyParameter / ML_parameter / Chemical
  ├─ 选择分析类型 "UV"
  └─ 点击「启动」
       │
       ▼
  PlatformBackend.start()
       │
       ├── initialise_platform()
       │     ├── PhotochemicalReactionDryRun( analytical_method="UV" )
       │     │     └── 查找 _analytical_methods["UV"]
       │     │           → ExperimentAnalysisCoupler(
       │     │                 analysis_class = AnalyticsU3900H,
       │     │                 analytical_device = "UV_Spectrometer",
       │     │                 platform_constants_key = "UV" )
       │     │
       │     ├── _start_spectrometer_server_if_needed("UV")
       │     │     ├── 探测 TCP:9100 端口
       │     │     │   ├── 有服务 → 跳过（用户已手动启动）
       │     │     │   └── 无服务 → subprocess.Popen 启动 virtual_spectrometer_server.py
       │     │     └── 等待 2 秒
       │     │
       │     └── platform_experiment.start()
       │           └── Platform.build("Perry")
       │                 └── 从 platform_config.json 读取 UV_Spectrometer
       │                       → device_constructors["u3900h_spectrometer"]
       │                       → U3900HSpectrometer.open("localhost", 9100)
       │
       ├── initialise_ML()
       │     └── SingleBayesianOpti.ML_prime() + com_prime()
       │           └── _to_machine(): AnalyParameter → AnalyticalParameter 转换
       │
       └── 闭环循环（ML 线程）
             │
             ├── ML 建议下一组参数 (浓度/时间/光强)
             │
             ├── 实验执行 → AnalyticsU3900H.analyse()
             │     │
             │     ├── _set_parameters()
             │     │     device["start_wavelength"] = 534.0
             │     │     device["end_wavelength"]   = 200.0
             │     │     device["scan_speed"]        = 300.0
             │     │
             │     ├── _spectrometer_run()
             │     │     device["selftest"]          = True   → 协议帧 00010002→00010810→00010300→00010100
             │     │     device["baseline_calibrate"] = True  → 协议帧 00010323
             │     │     device["start_scan"]         = True  → 协议帧 00010500→循环 00010801→00010302
             │     │
             │     ├── _spectrometer_poll()
             │     │     轮询 device["scan_progress"] 直到 ≥ 100%
             │     │     data = device["data"]  → pd.DataFrame(wavelength, absorbance)
             │     │
             │     └── _process_analytics()
             │           ├── 积分 (200-600nm) → integrated_absorbance
             │           ├── Beer-Lambert: c = A / (ε × l)
             │           └── 产率 = pi_conc / reference_concentration
             │
             └── ML 更新模型 → 下一轮建议
```

### 2.2 协议帧通信示例

以一次完整扫描为例，TCP:9100 上的帧交互：

```
客户端 (驱动)                          服务端 (虚拟光谱仪)
    │                                       │
    │── 00010002 ──────────────────────────→ │  读取设备 ID
    │←─ 00000600 00010002 U-3900H-... ─────│
    │                                       │
    │── 00010810 ──────────────────────────→ │  初始化
    │←─ 00000600 00010810 01 00000A00 ─────│  (busy)
    │                                       │
    │── 00010300 ──────────────────────────→ │  模式初始化
    │←─ 00000600 00010300 00 00000000 ─────│  (就绪)
    │                                       │
    │── 00010100 17 3 0 0 1 300.0 ... ────→ │  设置方法参数
    │←─ 00000600 00010100 00 00000A00 ─────│
    │                                       │
    │── 00010323  1 ───────────────────────→ │  基线校准
    │←─ 00000600 00010323 02 00000A00 ─────│  (校准中)
    │←─ 00000600 00010323 00 00000200 ─────│  (校准完成)
    │                                       │
    │── 00010500 ──────────────────────────→ │  开始扫描
    │←─ 00000600 00010500 00 00000200 ─────│
    │                                       │
    │── 00010801   534.0000 ───────────────→ │  波长 534nm
    │←─ 00000600 00010801 00 00000200 ... ─│  (返回吸光度)
    │── 00010801   533.0000 ───────────────→ │  波长 533nm
    │←─ ...                                 │
    │── ... (逐波长步进) ...                 │
    │                                       │
    │── 00010302  0  0 ────────────────────→ │  结束扫描
    │←─ 00000600 00010302 00 00000000 ─────│
```

---

## 3. 运行流程

### 3.1 用户操作步骤

```
步骤 1 (可选): 启动虚拟光谱仪服务端
  $ python U3900H/virtual_spectrometer_server.py
  → TCP:9100 协议端口 + HTTP:4090 管理页面
  注: 平台会自动检测并启动，手动启动非必须

步骤 2: 启动 Streamlit 应用
  $ cd "Control Software" && streamlit run robochem_flex.py

步骤 3: 上传会话文件
  在首页上传 Examples/CS0_UV_optimisation/session.json
  → 自动加载: 平台 Perry、实验 DryRun、分析 UV、BO 优化参数

步骤 4: 导航到「运行平台」页面
  → 点击「启动」

步骤 5: 观察闭环优化
  → 前端实时显示产率变化
  → ML 模型迭代更新
  → 自动建议下一组实验参数
```

### 3.2 session.json 关键配置

```json
{
  "platform_name": "Perry",
  "platform_experiment": "PhotochemicalReaction - dry run",
  "experiment_type": "BO_optimisation",
  "analysis_type": "UV",

  "analysis_maths": "simple_integration",
  "yield_calculation_chemical": { "value": "SM" },
  "start_wavelength": { "value": 534.0 },
  "end_wavelength": { "value": 200.0 },
  "scan_speed": { "value": 300.0 },
  "integration_lower_bound": { "value": 200 },
  "integration_upper_bound": { "value": 600 },

  "experiment_class": {
    "class": "SingleBayesianOpti",
    "parameters": {
      "Model": "SingleTaskGP",
      "Acquisition Function": "UCB",
      "Number of initial points": 10,
      "Number of total points": 40
    },
    "ML_parameters": [
      "Limiting Reagent_ml",
      "Excess Reagent_ml",
      "Catalyst_ml",
      "residence_time_ml",
      "light_intensity_ml"
    ],
    "targets": ["yield"]
  }
}
```

### 3.3 设备注册链路

```
platform_config.json
  "UV_Spectrometer" → class: "u3900h_spectrometer", IP: localhost:9100
       │
       ▼
platform.py → device_constructors["u3900h_spectrometer"] = U3900HSpectrometer
       │
       ▼
photochemistry.py / chemistry.py
  _analytical_methods["UV"] = ExperimentAnalysisCoupler(
      analysis_class    = AnalyticsU3900H,
      analytical_device = "UV_Spectrometer",     ← 匹配 platform_config 中的设备名
      platform_constants_key = "UV",
  )
```

---

## 4. 产率计算逻辑

### 4.1 计算流程

```
原始光谱数据 (wavelength, absorbance)
       │
       ▼
积分 (integration_lower_bound → integration_upper_bound)
  integrated_absorbance = ∫ absorbance(λ) dλ    (numpy.trapz)
       │
       ▼
Beer-Lambert 定律
  c = A_max / (ε × l)
  其中 ε = molar_extinction_coefficient (默认 1.0)
       l = 1 cm (光程，隐含)
       │
       ▼
归一化产率
  yield = c_product / c_reference
  其中 c_reference = get_reference_concentration(
      yield_calculation_chemical.value,  ← "SM"
      recipe                             ← 限量试剂浓度
  )
```

### 4.2 参数分类 (tag 机制)

| tag | 参数 | 用途 |
|---|---|---|
| `all` | start_wavelength, end_wavelength, scan_speed, baseline_calibrate, molar_extinction_coefficient, yield_calculation_chemical | 所有数学方法共用 |
| `simple_integration` | integration_lower_bound, integration_upper_bound | 仅积分方法使用 |
| `null` | sample_name, data_folder | 后端内部使用，前端不可见 |

---

## 5. 双参数系统

前端/ML 侧与分析侧使用不同的参数类，需要转换：

```
AnalyParameter (前端/ML)          AnalyticalParameter (分析/设备)
  unit                              units
  omni_tag                          tag
  value                             value
  min_value / max_value             min_value / max_value
```

转换位于 `ml_backends.py` 的 `_to_machine()` 方法。关键约束：
- `AnalyParameter.from_json()` 必须正确加载 `omni_tag` 字段
- `_to_machine()` 中 Chemical 类型参数用 `value_discrete` 比较（如 "SM"）
- `tag` 为 None 的参数在 `_split_parameters()` 中会被跳过

---

## 6. 已知问题与改进建议

### 6.1 协议编解码三重重复 (高优先级)

同一套 `STX/ETX/calc_bcc/encode_frame/decode_frame` 逻辑存在于三个文件：

| 文件 | 角色 |
|---|---|
| `U3900H/virtual_spectrometer_server.py` | 虚拟服务端 |
| `U3900H/spectrometer_client.py` | 独立客户端 |
| `OmniPlatypus/.../u3900h_spectrometer.py` | 生产驱动 |

**建议**: 提取为共享模块 `u3900h_protocol.py`，三处统一引用。

### 6.2 `_spectrometer_run()` 硬编码等待 (高优先级)

```python
# 当前代码 (u3900h_analytics.py)
self._device["selftest"] = True
time.sleep(2)      # 虚拟服务端自检需 ~6 秒，2 秒不够

self._device["baseline_calibrate"] = True
time.sleep(2)      # 基线校准可能需更久
```

**建议**: 改为轮询 `device["status"]` 的 field3/field4 状态，等待设备就绪后再继续。

### 6.3 `_spectrometer_poll()` 超时静默 (中优先级)

```python
# 当前代码: 60 秒超时后不报错，直接取可能不完整的数据
while waited < max_wait:
    if self._device["scan_progress"] >= 100.0:
        break
    time.sleep(0.5)
    waited += 0.5
# 超时后无警告
```

**建议**: 超时后抛出 `AnalysisError` 或至少记录 warning 日志。

### 6.4 `platform_backend.py` 双重 `__del__` (中优先级)

文件中第 149 行和第 900 行各定义了一个 `__del__` 方法，Python 只使用最后一个。第一个负责停止平台和光谱仪服务端的 `__del__` 被覆盖，永远不会执行。

**建议**: 合并两个 `__del__` 为一个。

### 6.5 测试脚本硬编码 Windows 路径 (低优先级)

`U3900H/` 下的测试文件全部使用 `e:\workspace\Robochem\...` 路径，在 Linux 环境无法运行。

**建议**: 改用 `os.path.dirname(__file__)` 相对路径或环境变量。

### 6.6 虚拟光谱仪每次扫描生成不同随机光谱

`_generate_spectrum()` 在每次扫描时重新生成随机峰位置和强度。这意味着同一参数组合的多次测量结果不同，BO 模型看到的是高噪声目标值。

**影响**: 不影响管线验证，但优化收敛性较差。如需更真实的模拟，可考虑固定种子或基于参数确定性生成光谱。

---

## 7. 端口与服务一览

| 服务 | 端口 | 协议 | 启动方式 |
|---|---|---|---|
| 虚拟光谱仪 TCP 协议 | 9100 | U3900H 二进制帧 | 手动或平台自动 |
| 虚拟光谱仪管理页面 | 4090 | HTTP (Flask) | 随虚拟服务端启动 |
| 独立调试客户端 | 5001 | HTTP (Flask) | 手动启动 |
| Streamlit 主应用 | 8501 | HTTP (Streamlit) | `streamlit run robochem_flex.py` |

---

## 8. 关键文件索引

| 文件 | 行数 | 职责 |
|---|---|---|
| `U3900H/virtual_spectrometer_server.py` | 608 | 虚拟光谱仪 (TCP 服务端 + Flask 管理) |
| `U3900H/spectrometer_client.py` | 638 | 独立调试客户端 (TCP 客户端 + Flask 仪表盘) |
| `U3900H/U3900H_协议文档.md` | 376 | 协议帧格式、命令码、状态字段完整文档 |
| `OmniPlatypus/.../u3900h_spectrometer.py` | 558 | 生产设备驱动 (BaseDevice 子类) |
| `OmniPlatypus/.../u3900h_analytics.py` | 457 | UV-Vis 分析逻辑 (积分 + Beer-Lambert) |
| `backend/platform_backend.py` | 903 | 平台后端 (初始化、ML、虚拟光谱仪管理) |
| `OmniPlatypus/.../platform_config.json` | 400 | 平台配置 (设备注册、分析常量) |
| `Examples/CS0_UV_optimisation/session.json` | 751 | UV 优化示例会话 |
