# 新增 ML 算法指南

本文档详细说明如何在 Robochem-Flex 平台中新增一个自定义机器学习优化算法，并使其集成到前端 GUI 中供用户选择。

---

## 1. 架构概览

新增算法需要理解的核心继承链：

```
baseMLBackend                          ← robrains/communication_module/communication_module.py
│   提供：ML_prime(), _to_df(), _from_df(), _generate_check_dict() 等基础方法
│
├── ML_Platform                        ← robrains/communication_module/ml_platform.py
│   提供：run(), out_data(), in_data(), com_prime(), _run() 等平台通信方法
│
├── ToandFromMachine                   ← ml_backends.py
│   提供：_to_machine(), _from_machine(), calculate_metrics() 等硬件数据转换方法
│
└── YourCustomBackend                  ← robrains/ml_modules/your_backend.py
    你需要实现：validate_and_update(), first_run(), update()
```

最终注册到前端的组合类通过**多重继承**将上述层组合在一起：

```python
class YourCustomML(ML_Platform_omni, YourCustomBackend):
    pass
```

其中 `ML_Platform_omni = ToandFromMachine + ML_Platform`，提供了硬件通信能力。

---

## 2. 涉及的文件

| 序号 | 文件路径 | 操作 | 说明 |
|------|---------|------|------|
| ① | `backend/Robochem_ML/robrains/ml_modules/your_backend.py` | **新建** | ML 算法核心逻辑 |
| ② | `backend/Robochem_ML/robrains/ml_modules/__init__.py` | 修改 | 导出新类 |
| ③ | `backend/ml_backends.py` | 修改 | 创建组合类 + import |
| ④ | `backend/platform_backend.py` | 修改 | 注册到 `ML_classes` 字典 |
| ⑤ | `pages/06_Machine_Learning.py` | 修改（可选） | 添加新的目标函数或前端 UI |

---

## 3. 逐步操作

### 步骤 ① — 创建算法核心类

在 `backend/Robochem_ML/robrains/ml_modules/` 目录下新建文件（如 `my_custom_backend.py`）。

#### 类定义模板

```python
"""
Custom ML Backend
Descr: 在此描述你的算法
"""

import time
from typing import Any, Optional, Tuple

import pandas as pd
import torch

from robrains.communication_module import baseMLBackend
from robrains.utils import ColumnNormalizer


class MyCustomBackend(baseMLBackend):
    """
    自定义 ML 算法后端。

    必须实现的方法：
    - validate_and_update(): 验证前端传来的参数
    - first_run():          生成初始实验点
    - update():             核心优化循环
    """

    # ── 前端可配置参数 ──────────────────────────────────
    # 值可以是列表（下拉选择）、或类型字符串（"int"/"float"/"bool"）
    input_parameters = {
        "Number of initial points": "int",
        "Number of total points": "int",
        "Number of Experiments per batch": "int",
        "Explorative Factor": "float",
        "Termination criterion": ["max_iter", "performance"],
        "Resubmission of Failed N": "int",
        # ↓↓↓ 在这里添加你的算法特有参数 ↓↓↓
    }

    # ── 参数默认值 ──────────────────────────────────────
    input_defaults = {
        "Number of initial points": 10,
        "Number of total points": 100,
        "Number of Experiments per batch": 1,
        "Explorative Factor": 0.1,
        "Termination criterion": "max_iter",
        "Resubmission of Failed N": 0,
    }

    # ── 边界调整方法 ────────────────────────────────────
    # "None" = 默认, "RemoveTask" = 多任务场景, "RemoveFidelity" = 多保真度场景
    _bound_adjustment_method = "None"

    def __init__(self):
        super().__init__()

    # ── 参数验证 ────────────────────────────────────────
    def validate_and_update(self, key: str, value: Any) -> None:
        """验证并更新从前端接收到的参数。"""
        if key not in self.input_parameters:
            self.log_mssg(f"Unknown parameter: {key}", level="warning")
            return

        # 根据参数类型进行验证
        match key:
            case "Number of initial points" | "Number of total points":
                if not isinstance(value, int) or value < 1:
                    self.log_mssg(f"{key} must be a positive integer", level="warning")
                    return
            # ... 添加更多验证规则 ...

        self.parameters[key] = value
        self.log_mssg(f"Parameter {key} updated to {value}", level="ok")

    # ── 首次运行：生成初始实验点 ────────────────────────
    def first_run(self) -> pd.DataFrame:
        """
        生成初始实验点并发送给硬件执行。

        关键 API：
        - self.bounds:           torch.Tensor, shape (2, n_features), 参数边界
        - self.out_data(points): 将实验点提交给硬件平台
        - self.out_data("stop"): 发送停止信号
        """
        self.run_index = 0
        n_initial = self.parameters["Number of initial points"]

        # 如果有历史数据，减少需要生成的初始点数量
        if hasattr(self, "results_df") and not self.results_df.empty:
            self.run_index = max(self.results_df["run_index"]) + 1
            n_finished = len(self.results_df[self.results_df["status"] == "finished"])
            n_initial = max(0, n_initial - n_finished)
            if n_initial == 0:
                return self.results_df.copy()

        # 生成初始点（示例：Sobol 采样）
        from botorch.utils import draw_sobol_samples
        initial_points = draw_sobol_samples(bounds=self.bounds, n=n_initial, q=1).squeeze(1)

        return self.out_data(initial_points)

    # ── 核心优化循环 ────────────────────────────────────
    def update(self) -> None:
        """
        每次收到一批实验结果后调用。

        典型流程：
        1. self._process_data() → 获取训练张量 (x, y, y_var)
        2. 训练你的模型
        3. 用你的算法提出下一批实验点
        4. self.out_data(next_points) 提交新实验点
        5. 检查终止条件 → self.out_data("stop")
        """
        # 1. 处理数据
        x, y, y_var = self._process_data()
        if x.numel() == 0:
            self.out_data("failures")
            return

        # 2. 检查终止条件
        if self.run_index >= self.parameters["Number of total points"]:
            self.out_data("stop")
            return

        # 3. 归一化训练数据
        n_finished = len(self.results_df[self.results_df["status"] == "finished"])
        train_x = x.reshape(n_finished, -1)
        train_y = y.reshape(n_finished, -1)
        normalizer = ColumnNormalizer(train_y)
        train_y_norm = normalizer.normalize(train_y)

        # 4. ↓↓↓ 在这里实现你的算法核心逻辑 ↓↓↓
        #    - 训练模型
        #    - 提出下一批实验点
        #    next_points = your_algorithm(train_x, train_y_norm, ...)

        # 5. 提交新实验点
        # self.out_data(next_points, predicted_y=(mean, var))
        pass

    # ── 辅助方法 ────────────────────────────────────────
    def _process_data(self) -> Tuple[torch.Tensor, torch.Tensor, Optional[torch.Tensor]]:
        """从 results_df 提取训练张量。"""
        x, y, y_var = self._from_df(self.results_df)
        return x, y, y_var
```

#### 必须实现的方法

| 方法 | 作用 | 调用时机 |
|------|------|----------|
| `validate_and_update(key, value)` | 验证前端传入的参数是否合法 | 用户在前端修改参数时 |
| `first_run()` | 生成初始实验点，调用 `self.out_data()` 提交 | `run()` 首次调用时 |
| `update()` | 核心优化循环：处理数据 → 训练模型 → 提出新点 | 每批实验完成后 |

#### 可直接使用的基类方法

| 方法 | 来源 | 作用 |
|------|------|------|
| `ML_prime(ML_parameters, targets, save_path)` | `baseMLBackend` | 初始化 ML 参数、目标、保存路径 |
| `com_prime(**kwargs)` | `ML_Platform` | 初始化通信队列、实验对象、常量 |
| `out_data(next_points, predicted_y)` | `ML_Platform` | 向硬件提交新实验点 |
| `in_data(run_index, x, y, y_var, vial_idx)` | `ML_Platform` | 接收硬件返回的实验结果 |
| `_to_machine(tensor)` | `ToandFromMachine` | 将 ML 张量翻译为硬件配方 |
| `_from_machine(run_result)` | `ToandFromMachine` | 将硬件结果翻译为 ML 张量 |
| `_from_df(df)` | `baseMLBackend` | 从 DataFrame 提取训练张量 |
| `_to_df(tensor, run_idx)` | `baseMLBackend` | 将张量写入 results_df |
| `_generate_check_dict()` | `baseMLBackend` | 生成参数名到张量索引的映射 |
| `calculate_metrics(targets, recipe)` | `ToandFromMachine` | 计算优化目标值（yield/cost 等） |
| `get_data_to_save()` | `baseMLBackend` | 收集需要持久化的数据 |

---

### 步骤 ② — 导出新类

编辑 `backend/Robochem_ML/robrains/ml_modules/__init__.py`，添加导出：

```python
from .my_custom_backend import MyCustomBackend
```

---

### 步骤 ③ — 创建组合类

编辑 `backend/ml_backends.py`：

**3a. 添加 import**（文件顶部）：

```python
from robrains.ml_modules import (
    # ... 已有的 import ...
    MyCustomBackend,       # ← 新增
)
```

**3b. 创建组合类**（文件末尾）：

```python
# 不需要人在回路（HITL）的算法：
class MyCustomML(ML_Platform_omni, MyCustomBackend):
    """自定义 ML 算法，全自动模式。"""
    def __init__(self):
        super().__init__()

# 如果需要人在回路（HITL）：
class MyCustomML_HITL(ML_Platform_HITL_omni, MyCustomBackend):
    """自定义 ML 算法，人在回路模式。"""
    def __init__(self):
        super().__init__()
```

**继承选择指南**：

| 基类 | 适用场景 |
|------|----------|
| `ML_Platform_omni` | 全自动闭环（有分析仪器，如 NMR/UPLC/Raman） |
| `ML_Platform_HITL_omni` | 人在回路（无分析仪器，需人工输入结果） |

---

### 步骤 ④ — 注册到前端

编辑 `backend/platform_backend.py`：

**4a. 添加 import**（文件顶部）：

```python
from backend.ml_backends import (
    # ... 已有的 import ...
    MyCustomML,            # ← 新增
)
```

**4b. 注册到 `ML_classes` 字典**（`PlatformBackend` 类内）：

```python
ML_classes = {
    "BO_optimisation": SingleBayesianOpti,
    "BO_optimisation_HITL": SingleBayesianOptiHITL,
    # ... 已有的 ...
    "MyCustomML": MyCustomML,       # ← 新增
}
```

注册后，前端 `02_User_Settings.py` 页面的下拉菜单会自动出现 `"MyCustomML"` 选项。

---

### 步骤 ⑤ — （可选）添加新目标函数

如果你的算法需要新的优化目标：

**5a.** 在 `backend/ml_backends.py` 的 `ToandFromMachine.calculate_metrics()` 方法中添加新的 `case`：

```python
def calculate_metrics(self, targets, recipe):
    for target in self.targets:
        match target:
            # ... 已有的 case ...
            case "your_new_metric":
                metrics[target] = self._calculate_your_metric(targets)
```

**5b.** 在 `pages/06_Machine_Learning.py` 的 `objectives` 元组中添加名称：

```python
objectives = (
    "yield", "conversion", "cost",
    # ... 已有的 ...
    "your_new_metric",       # ← 新增
)
```

---

### 步骤 ⑥ — （可选）添加前端特殊 UI

如果你的算法有特殊的 UI 需求（如 MultiTaskScope 的 Task Settings），在 `pages/06_Machine_Learning.py` 中添加条件渲染：

```python
if backend.session_container["experiment_type"] == "MyCustomML":
    st.markdown("### My Custom Settings")
    # 你的自定义 UI 组件
```

---

## 4. 数据流全景

新增算法在系统中的完整数据流：

```
┌─────────────────────────────────────────────────────────────────────┐
│                         初始化阶段                                   │
│                                                                     │
│  前端选择 "MyCustomML"                                               │
│       │                                                             │
│       ▼                                                             │
│  backend.ml_experiment_class = MyCustomML()                         │
│       │                                                             │
│       ▼                                                             │
│  platform_backend.initialise_ML()                                   │
│       │                                                             │
│       ├── ml_experiment_class.ML_prime(ML_parameters, targets, path)│
│       │       → 初始化参数、生成 check_dict、设置边界                 │
│       │                                                             │
│       └── ml_experiment_class.com_prime(experiment, constants, ...) │
│               → 初始化通信队列、绑定实验对象                          │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         运行阶段                                     │
│                                                                     │
│  platform_backend.start() → ml_experiment_class.run()               │
│       │                                                             │
│       ▼                                                             │
│  first_run()                                                        │
│       │                                                             │
│       └── 生成初始点 → out_data(points) → 硬件执行                    │
│                                                                     │
│       ▼                                                             │
│  _run() 主循环 ───────────────────────────────────────────────┐       │
│       │                                                       │      │
│       ├── get_result() ← 硬件返回 RunResult                    │      │
│       │                                                       │      │
│       ├── _from_machine(result) → (run_index, x, y, y_var)    │      │
│       │                                                       │      │
│       ├── in_data(run_index, x, y, y_var) → 更新 results_df   │      │
│       │                                                       │      │
│       ├── check_batch() → 本批是否全部完成？                    │      │
│       │     │                                                 │      │
│       │     └── 是 → update()                                 │      │
│       │              │                                        │      │
│       │              ├── _process_data() → x, y, y_var        │      │
│       │              ├── 训练你的模型                          │      │
│       │              ├── 提出 next_points                     │      │
│       │              └── out_data(next_points) → 硬件执行      │      │
│       │                                                       │      │
│       └── 循环直到 out_data("stop") ←─────────────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

---
## 6. 检查清单

完成所有步骤后，逐项确认：

- [ ] `my_custom_backend.py` 已创建，类继承自 `baseMLBackend`
- [ ] 实现了 `validate_and_update()`、`first_run()`、`update()` 三个方法
- [ ] 定义了 `input_parameters` 和 `input_defaults`
- [ ] 设置了 `_bound_adjustment_method`（通常为 `"None"`）
- [ ] `robrains/ml_modules/__init__.py` 已添加导出
- [ ] `ml_backends.py` 已添加 import 和组合类定义
- [ ] `platform_backend.py` 已添加 import 和 `ML_classes` 注册
- [ ] （如有新目标函数）`calculate_metrics()` 和 `06_Machine_Learning.py` 已更新
- [ ] 启动 Streamlit 后，下拉菜单中能看到新算法名称
- [ ] 使用 dry run 模式测试通过

---

## 7. 调试建议

1. **先用 dry run 模式测试**：使用 `Examples/CS0_dryrun/` session，选择你的新算法，手动输入 yield 值验证流程
2. **查看日志**：ML 日志实时输出在终端，关注 `level="error"` 和 `level="warning"` 的消息
3. **检查 `results_df`**：在 `update()` 中打印 `self.results_df` 确认数据格式正确
4. **检查张量维度**：`self.tensor_shape` 告诉你预期的张量形状，确保 `_process_data()` 返回的维度匹配
5. **单元测试**：参考 `backend/Robochem_ML/tests/` 下的测试文件编写单元测试

## 8. Dragonfly、Botorch 差异

DragonflyBackend 特点：
    实现简洁，易于理解，快速原型验证，需要极简实现的场景
    使用 ask/tell 接口，逻辑清晰
    支持采集函数：TS、UCB、EI
    仅支持连续参数空间（EuclideanDomain）
    不支持：离散/混合参数、多目标优化、批量优化

SingleBayesianOptiBackend 特点：
    功能全面，高度可配置
    支持多种代理模型（GP、RF、NN、BNN、SVR）
    支持采集函数：EI、PI、UCB、qEHVI（多目标）、qLogNEHVI 等
    支持混合参数空间（连续 + 离散/分类）
    支持多目标优化（加权、Pareto）
    支持批量优化（q 前缀采集函数）
    支持自适应策略（exploration/exploitation 平衡）
    支持 Fidelity/Task 特征
    支持 LHS/Random 初始化