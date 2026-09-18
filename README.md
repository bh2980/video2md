# video2md

Local lecture video → Markdown (captions/STT + OCR). No LLM.

## Requirements

- macOS on Apple Silicon
- ffmpeg (available on `PATH`)
- Python 3.14 via [uv](https://docs.astral.sh/uv/)

## Install

```sh
uv sync
```

## Usage

```sh
uv run video2md lecture.mp4
```

Input은 파일 하나, 여러 파일, 또는 디렉터리(배치 모드)를 그대로 positional으로 받습니다.
출력은 기본적으로 입력 파일 옆의 동일한 stem을 가진 `.md` 파일입니다
(예: `lecture.mp4` → `lecture.md`). 같은 위치에 `lecture.vtt` / `lecture.srt`가
있으면 자동으로 사용하고, 없으면 mlx-whisper로 STT를 수행합니다.

## Parameters

```sh
uv run video2md [options] inputs [inputs ...]
```

### Positional

| Parameter | Description |
| --- | --- |
| `inputs` | 비디오 파일 및/또는 비디오가 담긴 디렉터리. 1개 이상 필수. 지원 확장자: `.mp4`, `.mov`, `.mkv`, `.m4v` (디렉터리 수집 시 대소문자 무시) |

### Input / output

| Parameter | Default | Description |
| --- | --- | --- |
| `--out PATH` | `<input>.md` | 출력 Markdown 경로. **단일 비디오 전용** (배치 모드에서 지정하면 오류) |
| `--captions PATH` | auto | 기존 자막 파일(`.vtt`/`.srt`)을 직접 지정. **단일 비디오 전용** |
| `--work-dir PATH` | `~/Library/Caches/video2md/<hash>` | 중간 산출물(프레임, STT 결과, manifest)을 저장하는 작업 디렉터리 |
| `--recursive` | off | 디렉터리 입력 시 하위 디렉터리까지 재귀 탐색 |
| `--fail-fast` | off | 배치 모드에서 첫 실패 job에서 중단하고 해당 exit code 반환 |

### Language / STT

| Parameter | Default | Description |
| --- | --- | --- |
| `--language LANG` | auto-detect | 발화 언어 힌트 (예: `ko`, `en`). OCR 언어 preference에도 사용됨 |
| `--whisper-model NAME` | `turbo` | Whisper 모델. 별칭 `tiny` / `base` / `small` / `medium` / `large` / `turbo` 또는 로컬 모델 디렉터리 경로 |
| `--force-stt` | off | 자막 파일이 있어도 무시하고 항상 Whisper STT 수행 |

### Frame selection

| Parameter | Default | Description |
| --- | --- | --- |
| `--scene-threshold FLOAT` | `0.30` | ffmpeg 장면 전환 감지 임계값 (낮을수록 민감) |
| `--min-scene-interval FLOAT` | `1.5` | 유지할 프레임 사이 최소 간격(초) |
| `--frame-every FLOAT` | `5.0` | 장면 감지 외에 N초마다 추가 프레임 추출. `0`이면 비활성화 |
| `--max-frames INT` | `500` | 유지 프레임 상한. 초과 시 균등 샘플링으로 축소 |
| `--hash-threshold INT` | `8` | perceptual hash 거리 임계값. 이하면 직전 프레임과 유사한 것으로 간주해 제거 |

### OCR

| Parameter | Default | Description |
| --- | --- | --- |
| `--ocr-confidence FLOAT` | `0.30` | Apple Vision OCR 신뢰도 하한 |
| `--ocr-min-chars INT` | `12` | 프레임별 최소 영숫자 수. 이하면 해당 프레임 버림 |
| `--skip-ocr` | off | OCR 생략 (음성/자막만으로 Markdown 생성) |

### Modes / maintenance

| Parameter | Default | Description |
| --- | --- | --- |
| `--skip-speech` | off | 음성/자막 처리 생략 (OCR만 사용). `--skip-ocr`과 동시 사용 불가 |
| `--force` | off | 캐시를 무시하고 모든 단계 재실행 |
| `--clean` | off | 성공 후 작업 디렉터리 삭제 (기본 캐시 라이프사이클에서 기본으로 수행되지만, 명시적으로 요청하는 기능으로 유지) |
| `--keep-cache` | off | 변환이 성공해도 작업 캐시를 삭제하지 않음 (디버깅/반복 재생성용) |
| `--hash-source` | off | 입력 비디오의 SHA-256을 Markdown 메타데이터에 포함 |
| `--verbose`, `-v` | off | DEBUG 로그 출력 |
| `--version` | — | 버전 출력 |

### Validation rules

- `--frame-every`는 `0` 이상이어야 합니다.
- `--skip-ocr`과 `--skip-speech`는 함께 사용할 수 없습니다.
- `--out`, `--captions`는 단일 비디오 입력에서만 유효합니다.
- `--out`은 입력 비디오와 같은 경로일 수 없습니다.

## Examples

```sh
# 기본: 자막 자동 감지, 없으면 Whisper STT
uv run video2md lecture.mp4

# 한국어 힌트 + 더 작은 모델
uv run video2md lecture.mp4 --language ko --whisper-model small

# 자막 직접 지정 + 출력 경로 지정
uv run video2md lecture.mp4 --captions subs/lecture.vtt --out notes/lecture.md

# 배치: 디렉터리 전체 (각 비디오 옆에 .md 생성)
uv run video2md lectures/ --recursive --fail-fast

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

## Outputs

단일 비디오 `lecture.mp4` 처리 시:

- `lecture.md` — 변환된 Markdown
- `lecture.transcript.json` — 발화 큐 타임스탬프 사이드카 (`start_s`, `end_s`, `text`)
- `lecture.frames/` — Markdown에 삽입된 프레임 이미지 (`0001_t12.345.jpg` 형식)

## Caching

작업 캐시(중간 산출물)는 `--work-dir`(기본 `~/Library/Caches/video2md/<hash>`)에 저장되며,
입력/파라미터/모델 revision으로 계산한 fingerprint가 일치하면 해당 단계를 재사용합니다.
파라미터를 바꾸면 관련 단계만 다시 실행됩니다.

### 캐시 라이프사이클

- **변환 성공 시**: 해당 영상의 작업 캐시(`~/Library/Caches/video2md/<hash>/`)를
  전부 삭제합니다. WAV, 임시 frame, OCR/STT 결과 등을 종류별로 남겨두지 않습니다.
  최종 산출물(`.md`, `.transcript.json`, `.frames/`)은 절대 삭제되지 않습니다.
  강의를 대량 처리해도 캐시 폴더가 계속 커지지 않습니다.
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

# 캐시 전체 삭제 (최종 출력물은 절대 건드리지 않음, cache dir 없어도 성공)
uv run video2md cache clear
```

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
