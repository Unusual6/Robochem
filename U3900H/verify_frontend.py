"""
模拟 Streamlit session 完整验证:
1. 初始化 PlatformBackend (如同首页 robochem_flex.py)
2. 设置 experiment_type / platform_experiment (如同用户设置页)
3. 调用 get_analytics() 验证下拉选项
4. 选择 "UV" 后验证 get_analytic_parameters() 返回
"""
import sys, os, json

CONTROL_SOFTWARE = os.path.join("e:\\workspace\\Robochem", "Control Software")
OMNIPLATYPUS = os.path.join(CONTROL_SOFTWARE, "OmniPlatypus", "OmniPlatypus")
BACKEND = os.path.join(CONTROL_SOFTWARE, "backend")
sys.path.insert(0, OMNIPLATYPUS)
sys.path.insert(0, CONTROL_SOFTWARE)  # 父目录, 让 `import backend` 可用
os.chdir(BACKEND)

# 让 robrains 日志不抛异常 (sandbox 保护)
import robrains.base_classes.base_classes as _bc
_orig_log = _bc.BaseLoggedClass.log_mssg
_bad_paths = ["C:\\Users\\issuser\\Robochem\\Guest\\kk"]
def _safe_log(self, *a, **kw):
    try: _orig_log(self, *a, **kw)
    except (PermissionError, OSError): pass
_bc.BaseLoggedClass.log_mssg = _safe_log

from backend.platform_backend import PlatformBackend

# 模拟一个 dict-like session_state
class FakeSessionState(dict):
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: return None

session = FakeSessionState()
backend = PlatformBackend(session)

# ---- 模拟用户设置页的选择 ----
session["platform_experiment"] = "PhotochemicalReaction"
session["experiment_type"] = "BO"   # non-HITL → 走正常分析路径
session["ML_task"] = "BO_optimisation"

print("=" * 60)
print("STEP 1 — get_analytics() 返回的下拉选项")
print("=" * 60)
analytics_list = backend.get_analytics()
print(f"  下拉选项 ({len(analytics_list)} 项): {list(analytics_list)}")
print()

# ---- 遍历所有选项, 看 get_analytic_parameters 是否正常 ----
print("=" * 60)
print("STEP 2 — 逐个验证 get_analytic_parameters()")
print("=" * 60)
for opt in analytics_list:
    session["analysis_type"] = opt
    result = backend.get_analytic_parameters()
    if result is None:
        print(f"  [{opt:15s}] → None (分析类为 None 或 experiment_type 是 HITL)")
    elif result == []:
        print(f"  [{opt:15s}] → [] (HITL 类型)")
    else:
        req, opt_params, maths = result
        print(f"  [{opt:15s}] → ✅ req={len(req):2d}  opt={len(opt_params):2d}  maths={maths}")

print()

# ---- 重点看 UV ----
print("=" * 60)
print("STEP 3 — 重点查看 UV-Vis 参数详情")
print("=" * 60)
session["analysis_type"] = "UV"
result = backend.get_analytic_parameters()
if result and result != []:
    req, opt_params, maths = result
    print(f"\n  UV 分析可用数学方法: {maths}")
    print(f"\n  必需参数 (前端可见, tag != None):")
    for p in req:
        print(f"    • {p.name:30s}  value={p.value}  range=[{p.min_value},{p.max_value}]  units={p.units}  tag={p.tag}")
    print(f"\n  可选参数:")
    for p in opt_params:
        print(f"    • {p.name:30s}  value={p.value}  range=[{p.min_value},{p.max_value}]  units={p.units}  tag={p.tag}")

    # 模拟选择一个 maths 方法
    for m in maths:
        print(f"\n  — 选择 maths='{m}' 后的参数可见性 —")
        visible_req = [p.name for p in req if p.tag in (m, "all")]
        visible_opt = [p.name for p in opt_params if p.tag in (m, "all")]
        hidden_opt = [p.name for p in opt_params if p.tag not in (m, "all")]
        print(f"    可见必需: {visible_req}")
        print(f"    可见可选: {visible_opt}")
        if hidden_opt:
            print(f"    隐藏可选: {hidden_opt}")
else:
    print(f"  UV 返回: {result}")

# ---- 对比 Raman ----
print()
print("=" * 60)
print("STEP 4 — 对比 Raman 参数 (参照)")
print("=" * 60)
session["analysis_type"] = "Raman"
result = backend.get_analytic_parameters()
if result and result != []:
    req, opt_params, maths = result
    print(f"\n  Raman 分析可用数学方法: {maths}")
    print(f"\n  必需参数 ({len(req)} 项):")
    for p in req:
        print(f"    • {p.name:30s}  value={p.value}  units={p.units}  tag={p.tag}")
    print(f"\n  可选参数 ({len(opt_params)} 项):")
    for p in opt_params:
        print(f"    • {p.name:30s}  value={p.value}  units={p.units}  tag={p.tag}")

print()
print("=" * 60)
print("✅ 验证完成")
print("=" * 60)
