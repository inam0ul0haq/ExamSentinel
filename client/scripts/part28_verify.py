"""Part 28 — Build Pipeline DoD Verification.

Checks all build artifacts exist and are correctly configured.
Does NOT launch the exe (would trigger UAC).
"""

import os
import sys
import struct

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

BUILD_DIR = os.path.join(os.path.dirname(__file__), "..", "build")
pass_count = 0
fail_count = 0


def ok(msg):
    global pass_count
    pass_count += 1
    print(f"  [PASS] {msg}")


def fail(msg):
    global fail_count
    fail_count += 1
    print(f"  [FAIL] {msg}")


def check(cond, msg):
    if cond:
        ok(msg)
    else:
        fail(msg)


def section(title):
    print(f"\n{'='*60}\n{title}\n{'='*60}")


def main():
    print("=" * 60)
    print("  Part 28 — Build Pipeline DoD Verification")
    print("=" * 60)

    # ================================================================
    section("1. Build artifacts exist")
    # ================================================================
    exe_path = os.path.join(BUILD_DIR, "dist", "ExamSentinel.exe")
    ico_path = os.path.join(BUILD_DIR, "icon.ico")
    manifest_path = os.path.join(BUILD_DIR, "examsentinel.manifest")
    spec_path = os.path.join(BUILD_DIR, "ExamSentinel.spec")
    bat_path = os.path.join(BUILD_DIR, "build.bat")
    gen_icon_path = os.path.join(BUILD_DIR, "gen_icon.py")

    check(os.path.isfile(exe_path), f"ExamSentinel.exe exists")
    check(os.path.isfile(ico_path), f"icon.ico exists")
    check(os.path.isfile(manifest_path), f"examsentinel.manifest exists")
    check(os.path.isfile(spec_path), f"ExamSentinel.spec exists")
    check(os.path.isfile(bat_path), f"build.bat exists")
    check(os.path.isfile(gen_icon_path), f"gen_icon.py exists")

    # ================================================================
    section("2. Exe size and basic validity")
    # ================================================================
    size = os.path.getsize(exe_path)
    size_mb = size / (1024 * 1024)
    check(size > 5_000_000, f"Exe size: {size_mb:.1f} MB (> 5 MB)")
    check(size < 200_000_000, f"Exe size: {size_mb:.1f} MB (< 200 MB)")

    # Check PE header
    with open(exe_path, "rb") as f:
        dos_header = f.read(2)
        check(dos_header == b"MZ", "Valid PE header (MZ)")

    # ================================================================
    section("3. Manifest — requireAdministrator embedded")
    # ================================================================
    with open(exe_path, "rb") as f:
        data = f.read()

    check(b"requireAdministrator" in data,
          "requireAdministrator in exe manifest")
    check(b"uiAccess" in data,
          "uiAccess in exe manifest")

    # Check manifest file contents
    with open(manifest_path, "r") as f:
        manifest = f.read()
    check('requireAdministrator' in manifest,
          "Manifest file: requireAdministrator")
    check('8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a' in manifest,
          "Manifest file: Windows 10/11 GUID")
    check('dpiAware' in manifest,
          "Manifest file: DPI awareness")

    # ================================================================
    section("4. Icon — multi-resolution ICO")
    # ================================================================
    ico_size = os.path.getsize(ico_path)
    check(ico_size > 500, f"Icon size: {ico_size} bytes")

    with open(ico_path, "rb") as f:
        header = f.read(6)
        reserved, ico_type, count = struct.unpack("<HHH", header)
    check(reserved == 0 and ico_type == 1, "Valid ICO header")
    check(count >= 4, f"Icon has {count} resolutions (>= 4)")

    # ================================================================
    section("5. PyInstaller spec — key settings")
    # ================================================================
    with open(spec_path, "r") as f:
        spec = f.read()

    check("console=False" in spec, "Spec: windowed mode (console=False)")
    check("uac_admin=True" in spec, "Spec: uac_admin=True")
    check("win32clipboard" in spec, "Spec: win32clipboard hidden import")
    check("psutil._psutil_windows" in spec, "Spec: psutil._psutil_windows hidden import")
    check("screeninfo" in spec, "Spec: screeninfo hidden import")
    check("charset_normalizer" in spec, "Spec: charset_normalizer hidden import")
    check("certifi" in spec, "Spec: certifi hidden import")
    check("tkinter" in spec, "Spec: tkinter hidden import")

    # ================================================================
    section("6. build.bat — key steps")
    # ================================================================
    with open(bat_path, "r") as f:
        bat = f.read()

    check("activate" in bat.lower(), "build.bat: activates venv")
    check("requirements.txt" in bat, "build.bat: installs requirements")
    check("pyinstaller" in bat.lower(), "build.bat: runs PyInstaller")
    check("release" in bat, "build.bat: copies to release folder")
    check("ISO" in bat or "date" in bat.lower(), "build.bat: ISO date in filename")
    check("UAC" in bat or "admin" in bat.lower(), "build.bat: mentions UAC")
    check("Defender" in bat or "Unblock" in bat, "build.bat: AV workaround docs")

    # ================================================================
    section("7. .gitignore — build artifacts excluded")
    # ================================================================
    gitignore_path = os.path.join(BUILD_DIR, "..", "..", ".gitignore")
    with open(gitignore_path, "r") as f:
        gi = f.read()

    check("client/build/dist/" in gi or "build/dist" in gi,
          ".gitignore: dist/ excluded")
    check("client/build/build/" in gi or "build/build" in gi,
          ".gitignore: build/ (PyInstaller work) excluded")
    check("client/build/release/" in gi or "release" in gi,
          ".gitignore: release/ excluded")

    # ================================================================
    section("8. .env.example — documented")
    # ================================================================
    env_example = os.path.join(BUILD_DIR, "..", ".env.example")
    with open(env_example, "r") as f:
        env = f.read()

    check("SKIP_LOCKDOWN" in env, ".env.example: SKIP_LOCKDOWN documented")
    check("SKIP_VM_CHECK" in env, ".env.example: SKIP_VM_CHECK documented")
    check("API_BASE_URL" in env, ".env.example: API_BASE_URL documented")

    # ================================================================
    section("9. LOCKDOWN_RUNBOOK.md exists")
    # ================================================================
    runbook = os.path.join(BUILD_DIR, "..", "..", "docs", "LOCKDOWN_RUNBOOK.md")
    check(os.path.isfile(runbook), "docs/LOCKDOWN_RUNBOOK.md exists")

    with open(runbook, "r") as f:
        rb = f.read()
    check("SKIP_LOCKDOWN" in rb, "Runbook: SKIP_LOCKDOWN documented")
    check("FullscreenSubsystem" in rb, "Runbook: FullscreenSubsystem documented")
    check("MouseBoundarySubsystem" in rb, "Runbook: MouseBoundarySubsystem documented")

    # ================================================================
    print(f"\n{'='*60}")
    print(f"  RESULTS: {pass_count} PASSED, {fail_count} FAILED")
    if fail_count == 0:
        print("  ALL PART 28 DOD CHECKS PASSED ✓")
    else:
        print("  SOME CHECKS FAILED")
    print("=" * 60)

    sys.exit(0 if fail_count == 0 else 1)


if __name__ == "__main__":
    main()
