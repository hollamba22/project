# GitHub 저장소 사용

저장소 주소: https://github.com/hollamba22/project

저장소는 비공개(Private)로 관리한다. GitHub 계정 소유자와 저장소에 초대한 협업자만 접근할 수 있다. Google Drive의 공유 대상은 GitHub로 자동 이전되지 않는다. 협업자는 저장소의 Settings → Collaborators에서 GitHub 계정으로 초대한다.

## 내려받기

원시 CSI 데이터, 웹캠 영상, 소스 압축파일과 모델 바이너리는 Git LFS를 사용한다. Git과 Git LFS를 설치한 뒤 실행한다.

```bash
git lfs install
git clone https://github.com/hollamba22/project.git
cd project
git lfs pull
```

비공개 저장소에 접근할 수 있는 GitHub 계정으로 인증해야 한다. GitHub의 Download ZIP 대신 Git LFS를 이용해 복제하면 대용량 원본 파일을 함께 받을 수 있다.

## 포함 범위

코드, 문서, 안테나 설계, 실험 데이터·영상·메타데이터, 분석 결과·모델, third_party 소스와 원본 압축파일을 포함한다. 수집 PC에서 사용하던 CSI 드라이버의 `.ko` 파일도 보존한다. 드라이버 재설치는 기존 `tools/install_csitool.sh`와 관련 수집 문서를 따른다.

설치된 Python 패키지 폴더(`outputs/csi_analysis_env`), Python 캐시, Windows 관리 파일, 로컬 비밀 설정은 제외한다. 외부 소스 안의 기존 `.gitignore`가 지정한 중간 빌드 파일도 제외한다. 원래 작업 폴더의 제외 파일은 삭제하지 않는다.

분석 패키지는 필요할 때 다음과 같이 설치한다. 패키지 버전 및 Python 호환성은 `RESEARCH_HANDOVER.md`의 분석 환경 설명을 먼저 확인한다.

```bash
python3 -m pip install --target outputs/csi_analysis_env -r scripts/evaluate/requirements-csi-analysis.txt
```

Git LFS 저장공간과 다운로드 사용량은 GitHub 계정의 한도를 공유한다. 영상·원시 데이터 변경분도 LFS 용량에 포함되므로 업로드 전에 `git status`와 `git lfs status`를 확인한다.

## 외부 Linux 소스 보존

Windows/Drive 복사본에서는 Linux의 심볼릭 링크나 대소문자가 다른 파일 이름이 변환되어 있을 수 있다. 원래 Linux 소스 경로·링크·권한이 필요하면 third_party의 원본 tar.gz를 Linux에서 풀어 사용한다. 저장소에는 두 ZIP에서 합친 현재 파일과 원본 압축파일을 함께 보존한다.
