# RXPC 커널·화면 진단 (2026-09-09)

## 결론

논문의 CSI 처리·학습 알고리즘 자체가 Linux 4.15를 요구하는 것은 아니다.
이 프로젝트에 설치된 Intel 5300 CSI Tool 드라이버가 4.15용이다.
현재 환경은 Ubuntu 18.04.6 LTS / Linux 5.4.0-150-generic이며 최신 Ubuntu가 아니다.
수집된 파일의 파싱·전처리·CPU 학습은 5.4에서도 진행할 수 있다.
5.4에서 새 CSI를 수집하려면 해당 커널에 맞는 CSI 드라이버 이식과 실제 수집 검증이 필요하다.
4.15용 모듈을 5.4에 강제로 로드하거나 설치 스크립트의 버전 검사만 제거하면 안 된다.

## 확인한 증거

- GPU: NVIDIA GTX 1050 (GP107), nouveau 사용.
- 이전 4.15 부팅 로그: `MMIO ... FAULT`, `Cannot find any crtc or sizes`,
  `DDC responded, but no EDID for HDMI-A-1` 기록. 3840x2160 프레임버퍼 사용.
- 현재 5.4 로그에서도 `gr: init failed, -16` 발생.
- 현재 HDMI-A-1 연결 상태는 connected이며 1920x1080 지원.
- 화면 문제는 nouveau/HDMI 경로가 유력하지만 원인은 아직 확정하지 못했다.
- 샌드박스 밖에서도 Intel 5300이 PCI 목록에 없고 `iw dev`가 비어 있다.
  카드 장착·접촉·슬롯 상태를 확인해야 하며 소프트웨어만으로 원인을 확정할 수 없다.
- 5.4의 iwlwifi에는 `connector_log`가 없고, 기존 CSI 모듈의 vermagic은
  `4.15.0-213-generic`이다.

## 준비한 화면 복구 시험

4.15에서 EDID가 비어 있어 Xorg가 1024x768만 선택하는 현상을 확인했다.
1920x1080 reduced-blanking 모드를 실행 중인 화면에 적용해 1920x1080 전환을 확인했다.
설치 스크립트는 같은 모드를 Xorg 설정에도 저장한다.
관리자 비밀번호 없이 유지하기 위해 사용자 자동 시작에도 같은 설정을 설치했다.
4.15 사용자 로그인 후 자동 적용되며 다른 커널에서는 아무 작업도 하지 않는다.

로컬 터미널에서 실행:

```bash
cd '/home/mh/바탕화면/project'
sudo bash tools/install_csi_display_test.sh
```

이 스크립트는 기존 설정을 `/var/backups/csi-display.*`에 백업한 다음,
기본 부팅 선택을 유지하면서 다음 두 항목과 10초 부팅 메뉴를 추가한다.
이 PC의 루트 UUID와 4.15 커널 파일을 확인하므로 다른 PC용으로 사용하지 않는다.

1. `CSI Linux 4.15 - HDMI 1080p (no GPU acceleration)`:
   HDMI 1080p/60Hz 출력을 요청하고 nouveau GPU 가속을 끈다.
   GUI는 소프트웨어 렌더링으로 느려질 수 있다. 화면 복구는 아직 검증되지 않았다.
2. `CSI Linux 4.15 - text console (nomodeset)`:
   첫 항목이 실패했을 때 시험할 텍스트 로그인 항목이다. GUI는 시작하지 않는다.

작업 저장 후 사용자가 재부팅하여 첫 항목을 선택한다.
실패하면 기존 `Ubuntu` 항목을 선택해 5.4로 돌아온다.
로그인 후 `uname -r` 및 `bash tools/verify_csitool.sh`로 확인한다.
Intel 5300이 인식되고 실제 `0xBB` CSI 레코드가 생성되어야 수집 성공이다.

설치 후 시험 항목만 제거하려면:

```bash
sudo rm /etc/grub.d/42_csi_display_test /etc/default/grub.d/99_csi_display_test.cfg /etc/X11/xorg.conf.d/20-csi-monitor.conf
sudo update-grub
```

## 근거

- [사용 중인 CSI 드라이버의 설치 요구사항](https://github.com/spanev/linux-80211n-csitool): 4.15 커널을 대상으로 함.
- [Intel CSI Tool 설명](https://dhalperi.github.io/linux-80211n-csitool/): Intel 5300, 수정 펌웨어 및 무선 드라이버 사용.
- [Nouveau 모듈 옵션](https://nouveau.freedesktop.org/KernelModuleParameters.html)
- [Linux video 모드 옵션](https://www.kernel.org/doc/html/v5.10/fb/modedb.html)
- 프로젝트의 4.15 소스에서도 `nouveau.noaccel` 및 video 모드 문법 확인.
