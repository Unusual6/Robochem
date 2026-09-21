"""最简验证: 打印 PhotochemicalReaction 和 ThermochemicalReaction 的分析方法"""
import sys, os

CONTROL_SOFTWARE = r"e:\workspace\Robochem\Control Software"
sys.path.insert(0, os.path.join(CONTROL_SOFTWARE, "OmniPlatypus", "OmniPlatypus"))
sys.path.insert(0, CONTROL_SOFTWARE)  # 让 `import backend` 可用
sys.path.insert(0, os.path.join(CONTROL_SOFTWARE, "backend"))

from omniplatypus.procedures.experiments.photochemistry import PhotochemicalReaction
from omniplatypus.procedures.experiments.thermochemistry import ThermochemicalReaction
from omniplatypus.procedures.experiments.chemistry import ChemicalReaction

for name, cls in [
    ("ChemicalReaction", ChemicalReaction),
    ("PhotochemicalReaction", PhotochemicalReaction),
    ("ThermochemicalReaction", ThermochemicalReaction),
]:
    methods = cls.get_analytical_methods()
    print(f"{name}:")
    for k, v in methods.items():
        ac = v.analysis_class
        ac_name = ac.__name__ if ac else "None"
        print(f"  {k:15s} → {ac_name}")
    print()