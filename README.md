<a id="readme-top"></a>

<div align="center">

  <h1 align="center">video2md</h1>

  <p align="center">
    강의 비디오를 Markdown으로 전사 (자막/STT + OCR). LLM 불필요.
  </p>

</div>

<!-- TABLE OF CONTENTS -->
<details>
  <summary>목차</summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a></li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#요구-사항">요구 사항</a></li>
        <li><a href="#설치">설치</a></li>
      </ul>
    </li>
    <li>
      <a href="#사용-법">사용 법</a>
      <ul>
        <li><a href="#입력과-출력">입력과 출력</a></li>
        <li><a href="#파라미터">파라미터</a></li>
        <li><a href="#유효성-규칙">유효성 규칙</a></li>
        <li><a href="#예제">예제</a></li>
      </ul>
    </li>
    <li><a href="#outputs">Outputs</a></li>
    <li><a href="#caching">Caching</a></li>
    <li><a href="#exit-codes">Exit codes</a></li>
    <li><a href="#license">License</a></li>
  </ol>
</details>

## About The Project

강의 비디오 파일의 음성과 화면 텍스트를 Markdown으로 전사하는 CLI입니다. 사람이 직접
읽기보다 LLM에 넣고 강의 내용을 다루는 용도를 염두에 두고 만들었습니다.

- **음성**: 영상 옆에 `.vtt` / `.srt` 자막이 있으면 그대로 사용하고, 없으면
  Apple Silicon용 [mlx-whisper](https://github.com/ml-explore/mlx-examples)로
  STT를 수행합니다.
- **화면**: ffmpeg 장면 전환 감지 + perceptual hash로 중복 프레임을 제거하고,
  남은 프레임에서 Apple Vision으로 텍스트(슬라이드/코드)를 OCR합니다.
- **LLM 없음**: 요약이나 재작성 없이, 인식된 텍스트를 있는 그대로 구조화합니다.
  모든 처리가 로컬에서 이뤄지며 네트워크는 Whisper 모델 최초 다운로드에만 사용됩니다.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Getting Started

### 요구 사항

- Apple Silicon macOS
- `PATH`에서 사용 가능한 ffmpeg (`brew install ffmpeg`)
- [uv](https://docs.astral.sh/uv/)로 관리되는 Python 3.14

### 설치

```sh
uv sync
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## 사용 법

```sh
uv run video2md [options] inputs [inputs ...]
```

`inputs`는 비디오 파일(`.mp4`, `.mov`, `.mkv`, `.m4v`) 또는 비디오가 담긴 디렉터리를
1개 이상 받습니다. 디렉터리 수집 시 확장자는 대소문자를 구분하지 않고, 이름이 `.`으로
시작하는 파일은 건너뜁니다.

### 입력과 출력

- **기본 출력**: 입력 비디오 옆의 동일한 stem을 가진 `.md`
  (예: `lecture.mp4` → `lecture.md`)
- **자막 자동 감지**: 같은 위치에 `lecture.vtt` / `lecture.srt`가 있으면 사용하고,
  없으면 mlx-whisper로 STT를 수행합니다.
- **`--out` 모드**:
  - 단일 비디오 → 출력 Markdown **파일** 경로
  - 여러 비디오 / 디렉터리 입력 → 출력 **디렉터리**
    - 디렉터리 입력의 영상은 상대 경로 구조를 그대로 유지합니다.
    - 디렉터리를 2개 이상 넣으면 폴더명을 접두사로 붙여 서로 다른 폴더의
      같은 이름 영상(`01.mp4`)이 충돌하지 않게 합니다.
    - 동일한 출력 경로가 중복되면 오류로 중단합니다.
- **배치 모드**: 여러 job을 순차 실행하며 한 job의 실패는 나머지에 영향을 주지
  않습니다. 마지막에 `Done: <성공> succeeded, <실패> failed` 요약을 출력합니다.

### 파라미터

#### Positional

| Parameter | Description |
| --- | --- |
| `inputs` | 비디오 파일 및/또는 비디오가 담긴 디렉터리. 1개 이상 필수. 지원 확장자: `.mp4`, `.mov`, `.mkv`, `.m4v` (디렉터리 수집 시 대소문자 무시) |

#### Input / output

| Parameter | Default | Description |
| --- | --- | --- |
| `--out PATH` | `<input>.md` | 단일 비디오 입력 시 출력 Markdown 파일 경로, 디렉터리·복수 비디오 입력 시 출력 디렉터리 (입력 구조를 유지하며 `<out>/<폴더명>/<상대경로>.md`로 저장) |
| `--captions PATH` | auto | 기존 자막 파일(`.vtt`/`.srt`)을 직접 지정. **단일 비디오 전용** |
| `--work-dir PATH` | `~/Library/Caches/video2md/<hash>` | 중간 산출물(프레임, STT 결과, manifest)을 저장하는 작업 디렉터리 |
| `--recursive` | off | 디렉터리 입력 시 하위 디렉터리까지 재귀 탐색 |
| `--fail-fast` | off | 배치 모드에서 첫 실패 job에서 중단하고 해당 exit code 반환 |

#### Language / STT

| Parameter | Default | Description |
| --- | --- | --- |
| `--language LANG` | auto-detect | 발화 언어 힌트 (예: `ko`, `en`). OCR 언어 preference에도 사용됨 |
| `--whisper-model NAME` | `turbo` | Whisper 모델. 별칭 `tiny` / `base` / `small` / `medium` / `large` / `turbo` 또는 로컬 모델 디렉터리 경로 |
| `--force-stt` | off | 자막 파일이 있어도 무시하고 항상 Whisper STT 수행 |

#### Frame selection

| Parameter | Default | Description |
| --- | --- | --- |
| `--scene-threshold FLOAT` | `0.30` | ffmpeg 장면 전환 감지 임계값 (낮을수록 민감) |
| `--min-scene-interval FLOAT` | `1.5` | 유지할 프레임 사이 최소 간격(초) |
| `--frame-every FLOAT` | `5.0` | 장면 감지 외에 N초마다 추가 프레임 추출. `0`이면 비활성화 |
| `--max-frames INT` | `500` | 유지 프레임 상한. 초과 시 균등 샘플링으로 축소 |
| `--hash-threshold INT` | `8` | perceptual hash 거리 임계값. 이하면 직전 프레임과 유사한 것으로 간주해 제거 |

#### OCR

| Parameter | Default | Description |
| --- | --- | --- |
| `--ocr-confidence FLOAT` | `0.30` | Apple Vision OCR 신뢰도 하한 |
| `--ocr-min-chars INT` | `12` | 프레임별 최소 영숫자 수. 이하면 해당 프레임 버림 |
| `--skip-ocr` | off | OCR 생략 (음성/자막만으로 Markdown 생성) |

#### Modes / maintenance

| Parameter | Default | Description |
| --- | --- | --- |
| `--skip-speech` | off | 음성/자막 처리 생략 (OCR만 사용). `--skip-ocr`과 동시 사용 불가 |
| `--force` | off | 캐시를 무시하고 모든 단계 재실행 |
| `--clean` | off | 성공 후 작업 디렉터리 삭제 (기본 캐시 라이프사이클에서 기본으로 수행되지만, 명시적으로 요청하는 기능으로 유지) |
| `--keep-cache` | off | 변환이 성공해도 작업 캐시를 삭제하지 않음 (디버깅/반복 재생성용) |
| `--hash-source` | off | 입력 비디오의 SHA-256을 Markdown 메타데이터에 포함 |
| `--verbose`, `-v` | off | DEBUG 로그 출력 |
| `--version` | — | 버전 출력 |

### 유효성 규칙

- `--frame-every`는 `0` 이상이어야 합니다.
- `--skip-ocr`과 `--skip-speech`는 함께 사용할 수 없습니다.
- `--captions`는 단일 비디오 입력에서만 유효합니다.
- 디렉터리·복수 비디오 입력에서 `--out`은 디렉터리여야 합니다
  (파일 경로를 주면 오류).
- 단일 비디오 입력에서 `--out`은 입력 비디오와 같은 경로일 수 없습니다.
- `--out` 디렉터리 모드에서 서로 다른 job의 출력 경로가 겹치면 오류로 중단합니다.

### 예제

```sh
# 기본: 자막 자동 감지, 없으면 Whisper STT
uv run video2md lecture.mp4

# 한국어 힌트 + 더 작은 모델
uv run video2md lecture.mp4 --language ko --whisper-model small

# 자막 직접 지정 + 출력 경로 지정
uv run video2md lecture.mp4 --captions subs/lecture.vtt --out notes/lecture.md

# 배치: 디렉터리 전체 (각 비디오 옆에 .md 생성)
uv run video2md lectures/ --recursive --fail-fast

# 배치: 폴더 여러 개 + 공통 출력 디렉터리 (구조 보존)
uv run video2md '강의1' '강의2' '강의3' --out ~/Desktop/new-output --recursive

# OCR만 (음성 처리 생략)
uv run video2md lecture.mp4 --skip-speech

# 캐시 무시하고 재실행 후 작업 디렉터리 정리
uv run video2md lecture.mp4 --force --clean

# 성공해도 작업 캐시 유지 (디버깅 / 반복 재생성)
uv run video2md lecture.mp4 --keep-cache

# 캐시 상태 확인 및 전체 정리
uv run video2md cache info
uv run video2md cache clear
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Outputs

단일 비디오 `lecture.mp4` 처리 시:

- `lecture.md` — 변환된 Markdown
- `lecture.transcript.json` — 발화 큐 타임스탬프 사이드카 (`start_s`, `end_s`, `text`)
- `lecture.frames/` — Markdown에 삽입된 프레임 이미지 (`0001_t12.345.jpg` 형식)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Caching

작업 캐시(중간 산출물)는 `--work-dir`(기본 `~/Library/Caches/video2md/<hash>`)에 저장되며,
입력/파라미터/모델 revision으로 계산한 fingerprint가 일치하면 해당 단계를 재사용합니다.
파라미터를 바꾸면 관련 단계만 다시 실행됩니다.

### 캐시 라이프사이클

- **변환 성공 시**: 해당 영상의 작업 캐시(`~/Library/Caches/video2md/<hash>/`)를
  전부 삭제합니다. WAV, 임시 frame, OCR/STT 결과 등을 종류별로 남겨두지 않습니다.
  최종 산출물(`.md`, `.transcript.json`, `.frames/`)은 삭제하지 않습니다.
  캐시가 성공 시마다 정리되므로 캐시 폴더가 계속 커지지 않습니다.
- **변환 실패 시**: 작업 캐시를 유지합니다. 재시도하면 완료된 stage(Whisper 등)를
  재사용합니다.
- **`--keep-cache`**: 성공한 작업도 캐시를 삭제하지 않습니다
  (예: `uv run video2md lecture.mp4 --keep-cache`).
  `--clean`과 함께 쓰면 `--keep-cache`가 우선합니다.
- **`--clean`**: 해당 영상의 작업 캐시만 명시적으로 정리합니다.
  `--work-dir`로 지정한 위치(관리 캐시 root 밖)도 삭제하며, 최종 산출물은
  건드리지 않습니다.
- 캐시 정리가 실패해도 이미 성공한 변환은 실패로 처리되지 않고 경고만 출력됩니다.

### 캐시 관리 CLI

```sh
# 캐시 상태 확인
uv run video2md cache info
# Cache: /Users/<you>/Library/Caches/video2md
# Size: 3.7 GB
# Entries: 42

# 캐시 전체 삭제 (최종 출력물은 건드리지 않음, cache dir 없어도 성공)
uv run video2md cache clear
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | 성공 |
| `1` | 일반 오류 (ffmpeg 실행 실패, OCR 오류 등), 배치에서 일부 실패 |
| `2` | 사용법 오류 (잘못된 옵션 조합, 입력 없음 등) |
| `3` | ffmpeg/ffprobe를 PATH에서 찾을 수 없음 |
| `4` | 입력 파일/자막 파일 없음, 자막 파싱 실패 |
| `5` | Whisper (STT) 오류 |
| `6` | 플랫폼 오류 (Apple Silicon macOS 아님) |

<p align="right">(<a href="#readme-top">back to top</a>)</p>

## License

MIT License로 배포됩니다. 자세한 내용은 [`LICENSE`](LICENSE) 파일을 참고하세요.

<p align="right">(<a href="#readme-top">back to top</a>)</p>
