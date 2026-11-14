# Install Yomu Note — Windows, Mac or Linux

**Important:** v0.8.2 is the next public-preview release candidate. Until its draft is tested and published, the existing public installer is **v0.8.1b-rc4**. The workflow creates a draft containing the Windows/macOS installers only after all builds succeed. A maintainer must test and publish it before the new binaries appear publicly.

## Find the Windows or macOS download

1. Go to the project's GitHub page.
2. Choose **Releases** in the right sidebar, then the latest **published** release.
3. Expand **Assets** and choose the download for your operating system. **Do not choose “Source code (zip)” unless you intend to build with Python.**

## Windows (x64)

Download the Windows Setup EXE from the latest *published* release (currently `YomuNote_Setup_v0.8.1b.exe`; the upcoming v0.8.2 build will be `YomuNote_Setup_v0.8.2.exe`). Close an older running Yomu Note, run the installer and launch it from the Start menu. Updates should use the same application ID as previous releases. If SmartScreen warns about an unsigned preview build, only proceed if you trust the repository and have verified the release source. The first installer is not code-signed.

## macOS (Apple Silicon or Intel)

Choose `macOS-arm64` for an M-series Mac, or `macOS-x86_64` for an Intel Mac. Open the `.dmg` and drag **Yomu Note.app** into **Applications**. These preview disk images are **unsigned and not notarised**; Gatekeeper may block them. Review the project and release before using the system-provided **Open Anyway** controls for a build you trust. The longer-term goal is properly signed/notarised releases.

## Linux — run or build from source (Ubuntu / Debian)

Linux does **not** have a prebuilt AppImage in this release. Yomu Note runs locally from its GitHub source, without a server or account. On Ubuntu or Debian, install the system dependencies:

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip \
  tesseract-ocr tesseract-ocr-eng \
  libegl1 libopengl0 libgl1 libglib2.0-0 \
  libdbus-1-3 libxcb-cursor0 libxkbcommon-x11-0
```

Clone the source and launch it:

```bash
git clone https://github.com/alteredwavestudios/Yomu-Note.git
cd Yomu-Note
sh run-linux.sh
```

The launcher creates a local Python virtual environment and installs Python dependencies on first run. Subsequent launches use `sh run-linux.sh` from the same folder. Tesseract and its English model are installed **on your Linux machine** for source-based OCR.

If you want to build your **own standalone application directory** rather than run the Python source, use `bash build-linux.sh` after the initial setup. It produces `dist/Yomu Note/Yomu Note`, including bundled OCR. This is **not** an AppImage or system installer.

Package names here target Ubuntu/Debian. Fedora, Arch and other distributions need equivalent Qt, Python and Tesseract dependencies. Once release tags are published, you may wish to check out a particular tag instead of following the newest `main` source.

## Does OCR need installing?

Windows and macOS release installers bundle Tesseract and English recognition data, subject to bundled-OCR verification. Linux **source users** need Tesseract installed locally as described above; a locally built Linux standalone directory bundles OCR.

## Will my notes survive updates?

Notebooks are regular `.yomunote` files in the location you saved them. Keep them **outside application installation folders**, and back them up before installing a preview build. Before a major update, make a copy using **Save Copy As…** if available.

## If the download isn't there

If Releases says no published release, the automation may still be building, a build may have failed, or the release may still be in draft review. **There are no downloadable native Windows/macOS installers until a maintainer has published them.** Linux users can follow the source installation steps above.
