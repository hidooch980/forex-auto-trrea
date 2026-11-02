# Forex AI Android APK

Native Android WebView shell for the Forex AI control center. The app asks for the HTTPS URL of the deployed control center and opens its authenticated /app workspace. It does not contain broker credentials.

## Build

GitHub Actions builds a debug APK on pushes and pull requests. Tag a release as v1.0.1 (or a higher semantic version) to build and publish a signed release APK.

## Release signing

Create one Android release keystore locally and store its Base64 representation and passwords only in GitHub Actions secrets:

- ANDROID_KEYSTORE_BASE64
- ANDROID_KEYSTORE_PASSWORD
- ANDROID_KEY_ALIAS
- ANDROID_KEY_PASSWORD

Never commit the keystore or print secrets in logs. Keep a secure offline backup: losing the signing key prevents in-place updates signed with that key. Rotating it requires Android's supported signing-key upgrade process or a new application ID.

The release workflow refuses to publish a release APK if signing secrets are missing. Android's package installer verifies that an update is signed by the same certificate as the installed app. The app updater downloads the official GitHub Release asset and leaves final installation to Android.

## Update behavior

The app checks the latest GitHub Release on launch and on demand. It offers the user an update when the release version is newer, downloads forex-ai-release.apk, then asks Android to install it. Android may require the user to allow installs from this app. This is a user-approved APK update, not silent background installation.

## Website hosting

Set the deployed website HTTPS URL on first launch. Until the FastAPI control center is deployed behind HTTPS, the APK can be built but cannot display a live remote dashboard. The WebView rejects cleartext HTTP and external domains open in the browser.

## Safety

Live trading stays disabled. This Android client does not execute trades or store MT5 passwords.
