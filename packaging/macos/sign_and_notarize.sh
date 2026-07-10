#!/usr/bin/env bash
#
# Codesign, notarize, and staple the macOS build — a deliberate NO-OP unless the
# signing secrets are present in the environment. Unsigned CI builds (the
# default for this OSS project) therefore keep working byte-for-byte unchanged;
# signing switches on the day the repo owner adds an Apple Developer ID.
#
# Two subcommands, called at two points in the release job:
#   sign_and_notarize.sh sign     <path/to/Abax.app>   # BEFORE building the .dmg
#   sign_and_notarize.sh notarize <path/to/foo.dmg>    # AFTER  building the .dmg
#
# Enable by defining these repository secrets and mapping them to env in
# release.yml (the job already wires them):
#   MACOS_CERTIFICATE_P12       base64 of a "Developer ID Application" .p12 bundle
#   MACOS_CERTIFICATE_PASSWORD  the .p12 export password
#   MACOS_SIGN_IDENTITY         e.g. "Developer ID Application: Jane Doe (TEAMID1234)"
#   MACOS_NOTARY_APPLE_ID       Apple ID e-mail used for notarytool
#   MACOS_NOTARY_TEAM_ID        10-character Apple Developer Team ID
#   MACOS_NOTARY_PASSWORD       an app-specific password for that Apple ID
#
# With any of those unset/empty the script prints why it is skipping and exits 0,
# so it can sit unconditionally in the pipeline.
set -euo pipefail

mode="${1:-}"
target="${2:-}"

if [[ -z "$mode" || -z "$target" ]]; then
  echo "usage: sign_and_notarize.sh {sign|notarize} <path>" >&2
  exit 2
fi

# The whole feature is gated on having a certificate to sign with. Absent it,
# there is nothing meaningful to do in either mode — bail out cleanly.
if [[ -z "${MACOS_CERTIFICATE_P12:-}" || -z "${MACOS_SIGN_IDENTITY:-}" ]]; then
  echo "→ macOS signing secrets absent; skipping '$mode' (build stays unsigned)."
  exit 0
fi

# --------------------------------------------------------------------------- #
# sign — import the cert into an ephemeral keychain and deep-sign the .app with
# the hardened runtime (a notarization prerequisite).
# --------------------------------------------------------------------------- #
sign_app() {
  local app="$1"
  if [[ ! -d "$app" ]]; then
    echo "sign: no such .app: $app" >&2
    exit 1
  fi

  local keychain="$RUNNER_TEMP/abax-signing.keychain-db"
  local kc_pass
  kc_pass="ci-$RANDOM$RANDOM"
  local p12="$RUNNER_TEMP/abax-cert.p12"

  echo "$MACOS_CERTIFICATE_P12" | base64 --decode > "$p12"

  security create-keychain -p "$kc_pass" "$keychain"
  security set-keychain-settings -lut 21600 "$keychain"
  security unlock-keychain -p "$kc_pass" "$keychain"
  security import "$p12" -k "$keychain" \
    -P "${MACOS_CERTIFICATE_PASSWORD:-}" \
    -T /usr/bin/codesign
  # Let codesign use the key non-interactively.
  security set-key-partition-list -S apple-tool:,apple:,codesign: \
    -k "$kc_pass" "$keychain" >/dev/null
  # Put our keychain first on the search list so the identity resolves.
  security list-keychains -d user -s "$keychain" login.keychain-db

  rm -f "$p12"

  echo "→ codesigning $app with '$MACOS_SIGN_IDENTITY' (hardened runtime)"
  codesign --force --deep --timestamp --options runtime \
    --sign "$MACOS_SIGN_IDENTITY" "$app"
  codesign --verify --deep --strict --verbose=2 "$app"
  echo "→ app signed."
}

# --------------------------------------------------------------------------- #
# notarize — submit the .dmg to Apple's notary service, wait for the verdict,
# and staple the ticket so the app validates offline.
# --------------------------------------------------------------------------- #
notarize_dmg() {
  local dmg="$1"
  if [[ ! -f "$dmg" ]]; then
    echo "notarize: no such .dmg: $dmg" >&2
    exit 1
  fi
  if [[ -z "${MACOS_NOTARY_APPLE_ID:-}" || -z "${MACOS_NOTARY_TEAM_ID:-}" \
        || -z "${MACOS_NOTARY_PASSWORD:-}" ]]; then
    echo "→ notary credentials absent; signed but NOT notarizing '$dmg'."
    exit 0
  fi

  echo "→ submitting $dmg to the Apple notary service (this can take minutes)…"
  xcrun notarytool submit "$dmg" \
    --apple-id "$MACOS_NOTARY_APPLE_ID" \
    --team-id "$MACOS_NOTARY_TEAM_ID" \
    --password "$MACOS_NOTARY_PASSWORD" \
    --wait
  echo "→ stapling the notarization ticket to $dmg"
  xcrun stapler staple "$dmg"
  xcrun stapler validate "$dmg"
  echo "→ dmg notarized + stapled."
}

case "$mode" in
  sign)     sign_app "$target" ;;
  notarize) notarize_dmg "$target" ;;
  *)
    echo "unknown mode '$mode' (want: sign | notarize)" >&2
    exit 2
    ;;
esac
