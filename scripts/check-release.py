"""Choose immutable source commits; never release one platform ahead of another."""
import json
import os
from pathlib import Path
import re
import subprocess

def version(value):
    if not re.fullmatch(r"0\.7\.(0|[1-9][0-9]*)", value):
        raise ValueError("Release versions must use the 0.7.X series")
    return tuple(map(int, value.split('.')))

windows = Path('windows-source/VERSION').read_text().strip()
mac = Path('mac-source/VERSION').read_text().strip()
version(windows)
version(mac)
releases = json.loads(subprocess.check_output(['gh', 'api', 'repos/SaqibZafar/Fumbler-releases/releases?per_page=100']))
published = [r['tag_name'].removeprefix('v') for r in releases if not r['draft'] and not r['prerelease']]
latest = max((version(v) for v in published), default=(0, 7, 4))
needed = windows == mac and version(windows) > latest
if needed and version(windows)[2] != latest[2] + 1:
    raise ValueError('Increment the latest released patch by exactly one')
with open(os.environ['GITHUB_OUTPUT'], 'a') as output:
    print('needed=' + str(needed).lower(), file=output)
    print('version=' + windows, file=output)
    for key, folder in [('windows', 'windows-source'), ('mac', 'mac-source')]:
        sha = subprocess.check_output(['git', '-C', folder, 'rev-parse', 'HEAD'], text=True).strip()
        print(key + '=' + sha, file=output)
print('Both platforms are ready to build.' if needed else 'No matching unreleased version. Nothing will be published.')
