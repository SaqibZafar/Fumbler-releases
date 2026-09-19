"""Sign immutable packages, upload to a draft, then expose one complete release."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
import plistlib
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, padding

repo = 'SaqibZafar/Fumbler-releases'
version = os.environ['VERSION']
if not re.fullmatch(r'0\.7\.(0|[1-9][0-9]*)', version):
    raise ValueError('Invalid version')
folder = Path('release-assets')
base = f'https://github.com/{repo}/releases/download/v{version}/'
feed_path = folder / 'releases.win.json'
feed = json.loads(feed_path.read_text())
assets = feed['Assets']
if not assets:
    raise ValueError('Windows feed is empty')
for asset in assets:
    name = asset['FileName']
    if Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Invalid package name')
    # Must match Brand.UpdatePackageId in the Windows app and the --packId that
    # package-release.ps1 reads from it. It is deliberately not "Fumbler": that
    # is the user's data folder, and Velopack empties its own install directory
    # on every update, which is how 0.7.5 deleted people's settings and media.
    if asset['Version'] != version or asset['PackageId'] != 'FumblerApp':
        raise ValueError('Windows package version mismatch')
    data = (folder / name).read_bytes()
    if hashlib.sha256(data).hexdigest().lower() != asset['SHA256'].lower():
        raise ValueError('Windows package checksum mismatch')
    asset['FileName'] = base + name
payload = json.dumps(feed, separators=(',', ':')).encode()
key = serialization.load_pem_private_key(os.environ['WINDOWS_UPDATE_PRIVATE_KEY'].encode(), password=None)
signature = key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
(folder / 'releases.win.signed.json').write_text(json.dumps({'payload': base64.b64encode(payload).decode(), 'signature': base64.b64encode(signature).decode()}))
# The unsigned Velopack index is retained for diagnostics only. The app never consumes it.
feed_path.write_bytes(payload)
sparkle_key = ed25519.Ed25519PrivateKey.from_private_bytes(base64.b64decode(os.environ['SPARKLE_PRIVATE_KEY']))
sparkle_public = base64.b64encode(sparkle_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
namespace = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
ET.register_namespace('sparkle', namespace)
for arch, label in [('arm64', 'apple-silicon'), ('x86_64', 'intel')]:
    name = f'Fumbler-{version}-mac-{label}.zip'
    path = folder / name
    # The archive holds Fumbler.app (the arch is in the file name only), so an
    # installed app is Fumbler.app whichever slice it is.
    with zipfile.ZipFile(path) as archive:
        plist = plistlib.loads(archive.read('Fumbler.app/Contents/Info.plist'))
        if plist['CFBundleVersion'] != version or plist['SUPublicEDKey'] != sparkle_public:
            raise ValueError('Mac version or embedded signing key mismatch')
        if plist['LSArchitecturePriority'] != [arch]:
            raise ValueError('Mac architecture mismatch')
    data = path.read_bytes()
    if not (folder / f'Fumbler-{version}-mac-{label}.dmg').is_file():
        raise ValueError('Missing Mac disk image for ' + label)
    root = ET.Element('rss', {'version': '2.0'})
    channel = ET.SubElement(root, 'channel')
    ET.SubElement(channel, 'title').text = f'Fumbler for macOS ({arch})'
    item = ET.SubElement(channel, 'item')
    ET.SubElement(item, 'title').text = f'Fumbler {version}'
    ET.SubElement(item, f'{{{namespace}}}version').text = version
    ET.SubElement(item, f'{{{namespace}}}shortVersionString').text = version
    ET.SubElement(item, f'{{{namespace}}}minimumSystemVersion').text = '13.0'
    ET.SubElement(item, 'enclosure', {'url': base + name, 'length': str(len(data)), 'type': 'application/octet-stream', f'{{{namespace}}}edSignature': base64.b64encode(sparkle_key.sign(data)).decode()})
    ET.ElementTree(root).write(folder / f'appcast-{arch}.xml', encoding='utf-8', xml_declaration=True)
setups = list(folder.glob('*Setup.exe'))
if len(setups) != 1:
    raise ValueError('Expected one Windows installer')
setups[0].rename(folder / f'Fumbler-{version}-windows-Setup.exe')
files = sorted(p for p in folder.iterdir() if p.is_file())
(folder / 'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in files))
# The build jobs report whether a publisher certificate was configured. The
# notes must say what was actually done; "signed" is never assumed.
windows_signed = os.environ.get('WINDOWS_SIGNED') == 'true'
mac_notarized = os.environ.get('MAC_NOTARIZED') == 'true'
windows_note = ('The Windows installer, updater and application are Authenticode-signed.' if windows_signed
                else 'The Windows installer is not signed with a publisher certificate: SmartScreen asks for "More info → Run anyway" on the first install, and some antivirus products quarantine the updater (Update.exe) as a heuristic false positive. Fumbler keeps working without it; only automatic updates stop until it is restored.')
mac_note = ('The Mac apps are signed with a Developer ID and notarized by Apple.' if mac_notarized
            else 'The Mac apps are signed ad hoc, not notarized: the first launch needs right-click → Open, and Accessibility or Microphone permission may need to be granted again after an update.')
signing_note = 'Update packages are cryptographically authenticated. ' + windows_note + ' ' + mac_note
notes = f'''Fumbler {version} for Windows, Mac Intel, and Mac Apple silicon.

Install this version once to enable future automatic updates. Updates download in the background and install when you quit Fumbler; Settings also offers Restart to update.

Windows: run the Setup.exe installer; Fumbler installs for your account, adds Start Menu and desktop shortcuts, and starts with Windows (change that in Settings → General). Mac: open the .dmg for your chip (Apple silicon or Intel), drag Fumbler into the Applications shortcut beside it, then open it from Applications; it opens at login unless you turn that off in Settings. The .zip files are what the apps update themselves from.

{signing_note}

Both architectures were built and ran the local self-tests in GitHub Actions. Real WhatsApp/Slack voice-note compatibility and an installed old-to-new update cycle still need device verification.

Source revisions: Windows {os.environ['WINDOWS_SHA']}; macOS {os.environ['MAC_SHA']}.
'''
notes_path = Path('release-notes.md')
notes_path.write_text(notes)
existing = subprocess.run(['gh', 'release', 'view', 'v' + version, '--repo', repo, '--json', 'isDraft'], capture_output=True, text=True)
if existing.returncode == 0:
    if not json.loads(existing.stdout)['isDraft']:
        raise ValueError('Refusing to overwrite a published version')
    # A failed upload can be resumed only for this still-private draft.
else:
    subprocess.run(['gh', 'release', 'create', 'v' + version, '--repo', repo, '--draft', '--title', 'Fumbler ' + version, '--notes-file', str(notes_path)], check=True)
subprocess.run(['gh', 'release', 'upload', 'v' + version, '--repo', repo, '--clobber'] + [str(p) for p in folder.iterdir() if p.is_file()], check=True)
subprocess.run(['gh', 'release', 'edit', 'v' + version, '--repo', repo, '--draft=false', '--latest', '--notes-file', str(notes_path)], check=True)
