# Fumbler releases

Installers and authenticated update feeds for Fumbler. The Windows and macOS
source repositories remain private. No application source or account tokens are
published here.

Get the matching installer from [Releases](https://github.com/SaqibZafar/Fumbler-releases/releases).
Install the first updater-enabled release once. Later updates download in the
background and install on normal exit. Settings includes automatic updates,
Check for updates, and Restart to update.

## Releasing

Keep both source repositories on the same next `0.7.X` version. Update `VERSION`,
app metadata, display strings and documentation together. Push both to `master`.
The scheduled workflow checks once a day, at 06:17 UTC (GitHub may delay or drop
scheduled jobs). It builds Windows and both Mac architectures, runs their local
checks, signs the update metadata/packages, and publishes one release only after
all jobs pass. Already published versions are never replaced. Use a new patch for
fixes.

The workflow can also be run manually, and manual dispatch is the normal way to
ship: it does not wait for the daily window. Leave **publish** unchecked for
build-only verification. `RELEASE_ENABLED=true` enables scheduled publishing, and
a scheduled run publishes without asking — leave the variable unset to keep
publishing a deliberate manual act.

GitHub disables scheduled workflows in a public repository after 60 days with no
repository activity, and emails the owner. Between infrequent releases this will
happen; re-enable the workflow from the Actions tab, or push any commit here to
reset the timer. Manual dispatch is unaffected.

## Trust and credentials

Read-only deploy keys grant the release builder access to each private source
repository. Its own short-lived `GITHUB_TOKEN` publishes the release. No personal
GitHub access token is stored in an app or required on a customer's computer.

`WINDOWS_UPDATE_PRIVATE_KEY` signs the Windows feed with RSA/SHA-256. The app
contains only its public key and verifies the feed before downloading packages;
Velopack checks the signed package hashes. `SPARKLE_PRIVATE_KEY` signs Mac update
archives with Ed25519; Sparkle verifies them before extraction.

These update signatures are separate from Windows Authenticode and Apple
Developer ID/notarization. The workflow signs for the operating systems only
when the publisher credentials exist as secrets, and none of them do yet:

| Secret | Used by | Effect |
| --- | --- | --- |
| `WINDOWS_CODESIGN_PFX_BASE64`, `WINDOWS_CODESIGN_PASSWORD` | `package-release.ps1` in the Windows source | Authenticode-signs `Fumbler.exe`, the launch stub, Velopack's `Update.exe` and `Setup.exe`, and fails the build if any executable comes out unsigned |
| `MACOS_CERTIFICATE_P12_BASE64`, `MACOS_CERTIFICATE_PASSWORD` | `import-signing-identity.sh` in the Mac source | Signs both bundles with the Developer ID Application identity and a secure timestamp |
| `APPLE_ID`, `APPLE_TEAM_ID`, `APPLE_APP_PASSWORD` | `notarize.sh` in the Mac source | Notarizes each bundle and disk image with Apple and staples the ticket |

The optional repository variable `RELEASE_REQUIRE_SIGNING=true` makes a build
without those secrets fail instead of shipping unsigned; set it once the
certificates are in place, not before. `WINDOWS_CODESIGN_TIMESTAMP_URL` overrides
the RFC 3161 timestamp server (DigiCert's by default). The release notes say
which of the two was actually done for that release, from the build jobs'
own report, never from an assumption.

Until then every published installer is unsigned. First installation requires
OS approval, ad-hoc Mac updates may require renewed Accessibility/Microphone
permission, and antivirus heuristics can quarantine Velopack's `Update.exe`
(Avira did, on 19 September 2026, as `Drop.Win32.RegStartupSelfDel.523`; the
Windows source's `UPDATES.md` records what that is). Do not advertise
warning-free installation.

Keep signing-key backups secure. Replacing the keys without a transition release
breaks updates for installed users. Never print keys, upload source archives, or
put private credentials into public release assets.
