# 개발 문서

## 프로젝트 구조

- `merge_pdfs_app.py`: Tkinter UI, 폴더 스캔, 파일명 생성, PDF 병합 로직을 포함합니다.
- `tests/test_merge_pdfs_app.py`: 병합 규칙과 파일명 생성 규칙을 검증하는 단위 테스트입니다.
- `requirements.txt`: 실행에 필요한 Python 패키지 목록입니다.
- `README.md`: 설치와 사용 방법을 설명하는 사용자 문서입니다.

## 주요 설계

앱은 GUI와 병합 로직을 같은 파일에 두되, 핵심 기능은 테스트 가능한 함수로 분리합니다.

- `build_output_filename(root, folder)`: 선택 루트부터 대상 폴더까지의 경로 조각으로 `{root}_{child}_merged.pdf` 형식 파일명을 만듭니다.
- `scan_merge_tasks(root)`: 루트와 하위 폴더를 재귀 검색해 PDF가 있는 폴더별 `MergeTask`를 생성합니다.
- `find_pdf_files(folder)`: 폴더에 직접 들어있는 PDF만 찾고 `*_merged.pdf`는 제외합니다.
- `merge_pdf_files(input_pdfs, output_path)`: `pypdf.PdfWriter`로 입력 PDF를 순서대로 병합합니다.
- `run_merge_tasks(tasks, overwrite, log)`: 기존 파일 처리, 오류 격리, 요약 집계를 담당합니다.

## 병합 알고리즘

1. 사용자가 루트 폴더를 선택합니다.
2. 루트 폴더 자신과 모든 하위 폴더를 순회합니다.
3. 각 폴더에서 직접 포함된 `.pdf` 파일만 수집합니다.
4. 앱 생성 결과물인 `*_merged.pdf`는 입력에서 제외합니다.
5. PDF 목록을 파일명 기준 오름차순으로 정렬합니다.
6. 폴더별 출력 파일명을 생성합니다.
7. 각 폴더의 PDF들을 하나의 결과 PDF로 병합합니다.

## 출력 파일명 생성 알고리즘

선택 루트가 `A`이고 대상 폴더가 `A/B/C`이면 경로 조각은 `A`, `B`, `C`입니다. 이를 `_`로 연결하고 `_merged.pdf`를 붙여 `A_B_C_merged.pdf`를 만듭니다.

Windows 파일명에 사용할 수 없는 문자는 `_`로 치환합니다.

## 오류 처리 정책

- 루트 폴더가 없거나 디렉터리가 아니면 스캔 단계에서 사용자에게 오류를 표시합니다.
- PDF가 없는 폴더는 병합 대상에서 제외합니다.
- 특정 PDF를 읽을 수 없으면 해당 폴더 병합만 실패 처리하고 다음 폴더로 진행합니다.
- 기존 결과 파일이 있고 덮어쓰기가 꺼져 있으면 실패가 아니라 건너뜀으로 처리합니다.
- 결과 파일 작성은 임시 파일에 먼저 쓴 뒤 교체해 부분 파일이 남을 위험을 줄입니다.

## 테스트 방법

단위 테스트:

```powershell
python -m unittest discover -s tests
```

샘플 데이터 수동 테스트:

1. `python merge_pdfs_app.py`로 앱을 실행합니다.
2. `data\分野別難度別問題` 폴더를 선택합니다.
3. `미리보기/스캔`으로 병합 대상 폴더를 확인합니다.
4. `병합 실행`으로 결과 PDF를 생성합니다.
5. 각 난도 폴더에 `分野別難度別問題_분야명_난도명_merged.pdf` 형식 결과물이 생겼는지 확인합니다.

## 향후 EXE 패키징

이번 범위는 소스 실행까지입니다. EXE가 필요해지면 PyInstaller를 추가해 다음 형태로 확장할 수 있습니다.

```powershell
python -m pip install pyinstaller
python -m PyInstaller --onefile --windowed merge_pdfs_app.py
```

패키징 시에는 Windows SmartScreen 경고, 백신 오탐, 파일 크기 증가 가능성을 별도로 검증해야 합니다.
