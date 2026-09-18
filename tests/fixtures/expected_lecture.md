---
schema: "video2md/v1"
source: "/Users/you/Lectures/cs161-binsearch.mp4"
source_size_bytes: 84215552
duration_s: 61.04
width: 1920
height: 1080
speech_source: "captions"
captions_path: "/Users/you/Lectures/cs161-binsearch.vtt"
language: null
whisper_model: null
whisper_revision: null
generated_at: "2026-09-17T16:02:11Z"
cue_count: 6
screen_count: 3
warnings: []
tool:
  name: "video2md"
  version: "0.1.0"
  ffmpeg: "9.0.1"
  webvtt_py: "0.5.1"
  mlx_whisper: "0.4.3"
  ocrmac: "1.0.1"
  imagehash: "4.3.2"
source_sha256: null
---

# Cs161 Binsearch

## Timeline

### [00:00:00.000] Screen

![](<cs161-binsearch.frames/0001_t0.000.jpg>)

```text
CS 161 — Lecture 4
Binary Search
Prof. Kim
```

### Speech [00:00:01.200 – 00:00:12.050]

Welcome back. Today we will prove the log n bound for binary search and then implement it. The invariant is that the target, if it exists, always lies in the half-open interval lo to hi.

### [00:00:12.480] Screen

![](<cs161-binsearch.frames/0002_t12.480.jpg>)

```text
def binary_search(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        mid = (lo + hi) // 2
        if a[mid] < x:
            lo = mid + 1
        else:
            hi = mid
    return lo if lo < len(a) and a[lo] == x else -1
```

### Speech [00:00:13.000 – 00:00:34.500]

Here is the Python. Notice we use a half-open interval so we never have to special-case an empty slice. mid is floor of lo plus hi over two. Each iteration discards at least half of the remaining range, so the loop runs at most floor of log2 of n plus one times. That is the entire proof.

### [00:00:35.200] Screen

![](<cs161-binsearch.frames/0003_t35.200.jpg>)

```text
Complexity
Time:  O(log n)
Space: O(1)
Requires a sorted array
```

### Speech [00:00:36.000 – 00:01:00.500]

Two caveats. The array must already be sorted, and if you overflow lo plus hi in a language with fixed-width integers, use lo plus the difference over two. Next time we will use this as a subroutine in a lower-bound argument. That is it for today.
