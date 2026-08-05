import json,subprocess,sys
from pathlib import Path

def test_cross_platform_verifier_accepts_identical_results(tmp_path:Path)->None:
 value={"format":"storyteller.contract-results.v2","scenarios":{"complete":{"outcome":"accepted","issue_codes":[]}}}
 paths=[]
 for name in ("python","android","ios"):
  path=tmp_path/f"{name}.json";path.write_text(json.dumps(value));paths.append(path)
 result=subprocess.run([sys.executable,"scripts/verify_cross_platform_scenarios.py",
  "--python-results",str(paths[0]),"--android-results",str(paths[1]),"--ios-results",str(paths[2])],capture_output=True,text=True)
 assert result.returncode==0 and '"parity": true' in result.stdout
