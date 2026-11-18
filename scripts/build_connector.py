"""Apply our pinned v2.7.4 login compatibility fix and build a candidate binary.
Source lives in data/connector/build/source; Go binary is given as argv[1].
The running binary is deliberately never replaced by this script.
"""
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / 'data/connector/build/source'
PATCH = ROOT / 'integrations/xiaohongshu'
if len(sys.argv) != 2:
    raise SystemExit('Usage: python scripts/build_connector.py /absolute/path/to/go')
if not SOURCE.is_dir():
    raise SystemExit('Run python scripts/fetch_connector.py first to fetch the pinned source.')
if (SOURCE / '.git').exists():
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=SOURCE, text=True).strip()
    if revision != 'bb6fa2e208719ee634fec37881be29d3aa4699b3':
        raise SystemExit('Unexpected source revision; refusing to patch another version.')
for name in ('creator_session.go', 'creator_session_test.go'):
    shutil.copy2(PATCH / name, SOURCE / 'xiaohongshu' / name)
shutil.copy2(PATCH / 'workbench_creator.go', SOURCE / 'workbench_creator.go')
routes = SOURCE / 'routes.go'
text = routes.read_text()
anchor = 'api.GET("/login/status", appServer.checkLoginStatusHandler)'
addition = 'api.GET("/login/creator-status", appServer.workbenchCreatorStatus)'
if addition not in text:
    if anchor not in text:
        raise SystemExit('Pinned source route anchor missing; refusing to patch another version.')
    routes.write_text(text.replace(anchor, anchor + '\n\t\t' + addition))
go = str(Path(sys.argv[1]).resolve())
subprocess.run([str(Path(go).with_name('gofmt')), '-w', './xiaohongshu/creator_session.go', './xiaohongshu/creator_session_test.go', './workbench_creator.go'], cwd=SOURCE, check=True)
subprocess.run([go, 'test', './xiaohongshu', '-run', '^TestCreatorSessionReadyWithoutLegacyCookie$', '-count=1'], cwd=SOURCE, check=True)
subprocess.run([go, 'build', '-trimpath', '-o', str(SOURCE.parent / 'xiaohongshu-mcp-candidate'), '.'], cwd=SOURCE, check=True)
