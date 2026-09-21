"""Test both session files."""
import json, os, sys, traceback, io

control_software = os.path.join(os.path.dirname(__file__), 'Control Software')
sys.path.insert(0, control_software)
sys.path.insert(0, os.path.join(control_software, 'backend'))
sys.path.insert(0, os.path.join(control_software, 'backend', 'Robochem_ML'))
sys.path.insert(0, os.path.join(control_software, 'OmniPlatypus', 'OmniPlatypus'))

from robrains.session_management import SessionContainer

for label, path in [
    ("CS0_dryrun", r'e:\workspace\Robochem\Examples\CS0_dryrun\session.json'),
    ("CS0_UV_optimisation", r'e:\workspace\Robochem\Examples\CS0_UV_optimisation\session.json'),
]:
    print(f"\n=== Testing {label} ===")
    with open(path, 'rb') as f:
        uploaded_bytes = f.read()
    uploaded_file = io.BytesIO(uploaded_bytes)
    sc = SessionContainer(session_init=None)
    try:
        ret, error_msg = sc.load_session(file=uploaded_file)
        print(f"Result: {ret}")
        print(f"Msg: {error_msg}")
    except Exception as e:
        print(f"UNCAUGHT: {type(e).__name__}: {e}")
        traceback.print_exc()