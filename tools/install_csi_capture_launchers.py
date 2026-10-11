#!/usr/bin/env python3
"""Per-user, explicit-role installation; no sudo or guessed Desktop creation."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def desktop_folder():
    home = Path.home().resolve()
    candidates = []
    if shutil.which("xdg-user-dir"):
        result = subprocess.run(["xdg-user-dir", "DESKTOP"], stdout=subprocess.PIPE,
                                universal_newlines=True, timeout=5)
        if result.returncode == 0:
            candidates.append(Path(result.stdout.strip()))
    candidates += [home / "바탕화면", home / "Desktop"]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved != home and home in resolved.parents and candidate.is_dir():
            return resolved
    raise RuntimeError("존재하는 사용자 바탕화면을 찾지 못했습니다. 바탕화면 폴더를 OS에서 설정하세요.")


def desktop_text(role, root):
    root = str(root.resolve())
    if any(c in root for c in "\n\r\0"):
        raise RuntimeError("프로젝트 경로에 제어 문자를 사용할 수 없습니다.")
    # Exec uses Desktop Entry quoting, not shell quoting. Percent escapes field codes.
    executable = root + "/tools/csi_capture_" + role + "_launcher.py"
    quoted = executable.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    quoted = quoted.replace("%", "%%")
    # The desktop string layer also consumes backslash escapes.
    quoted = quoted.replace("\\", "\\\\")
    lines = (ROOT / "tools" / ("csi-capture-" + role + ".desktop")).read_text().splitlines()
    return "\n".join('Exec=/usr/bin/python3 "' + quoted + '"' if line.startswith("Exec=") else
                     "Path=" + root.replace("\\", "\\\\") if line.startswith("Path=") else line
                     for line in lines) + "\n"


def install(role, destination, root=ROOT, trust=False):
    for chosen in (["rx", "tx"] if role == "both" else [role]):
        launcher = root / "tools" / ("csi_capture_" + chosen + "_launcher.py")
        if not launcher.is_file():
            raise RuntimeError("실행기 파일 없음: " + str(launcher))
        target = destination / ("csi-capture-" + chosen + ".desktop")
        if target.is_symlink() or (target.exists() and
                "X-CSI-Launcher=true" not in target.read_text()):
            raise RuntimeError("기존 사용자 파일을 덮어쓰지 않습니다: " + str(target))
        text = desktop_text(chosen, root)
        if not target.exists() or target.read_text() != text:
            with target.open("w", encoding="utf-8") as handle:
                handle.write(text)
        target.chmod(0o755)
        if trust and shutil.which("gio"):
            try:
                result = subprocess.run(["gio", "set", str(target), "metadata::trusted", "true"],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                if result.returncode != 0:
                    print("[경고] 자동 Trust 설정 불가. 아이콘 우클릭 → 실행 허용이 필요합니다.")
            except (OSError, subprocess.TimeoutExpired):
                print("[경고] Trust 설정을 데스크톱에서 확인하세요.")
        print("[통과] 설치: " + str(target))


def main():
    parser = argparse.ArgumentParser(description="현재 사용자 바탕화면에 CSI 역할 버튼 설치")
    parser.add_argument("role", choices=["rx", "tx", "both"])
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error("sudo/root로 설치하지 마세요.")
    install(args.role, desktop_folder(), trust=True)
    print("아이콘 우클릭 → ‘실행 허용’을 선택하세요. Desktop 환경에 따라 Trust 확인이 필요합니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
