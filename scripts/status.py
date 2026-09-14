"""Read the optional Worker's recent successful heartbeat; never print secrets."""
import json
from pathlib import Path
import os
import time

path = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / 'lark-media-dl/worker-status.json'
if path.is_file():
    data = json.loads(path.read_text(encoding='utf-8'))
    data['online'] = time.time() - data['last_seen'] < 45
else:
    data = {'online': False, 'reason': 'No successful Worker heartbeat recorded; local CLI downloads remain available'}
print(json.dumps(data, ensure_ascii=False, indent=2))
