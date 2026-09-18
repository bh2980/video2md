"""Generate the synthetic Korean lecture-slide fixture for the OCR integration test.

Run once to regenerate `korean_slide.jpg`:

    ../../.venv/bin/python make_slide.py

Uses the system Korean font so the output is reproducible and free of
third-party copyrighted material.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
SIZE = (1280, 720)
OUT = Path(__file__).resolve().parent / "korean_slide.jpg"

BG = (255, 255, 255)
HEADER_BG = (245, 245, 247)
INK = (30, 30, 32)
MUTED = (110, 110, 115)
ACCENT_BG = (217, 234, 211)
INK_DARK = (24, 38, 18)


def font(size: int, index: int = 0) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, size, index=index)


def main() -> None:
    img = Image.new("RGB", SIZE, BG)
    draw = ImageDraw.Draw(img)

    # Top navigation bar, like a typical player UI.
    draw.rectangle([0, 0, SIZE[0], 56], fill=HEADER_BG)
    draw.text((24, 12), "Lecture", fill=INK, font=font(24))
    draw.text((120, 12), " 화면 OCR 샘플 슬라이드", fill=MUTED, font=font(24))

    # Slide title.
    draw.text((64, 120), "2-1. 화면 OCR 샘플", fill=INK, font=font(56))

    # Body bullets: Korean-first with a little English mixed in, small body size
    # so the regression test still exercises small Korean glyph rendering.
    bullets = [
        "1. 한국어와 English가 섞인 문장을 읽습니다.",
        "2. Apple Vision OCR은 라인을 위에서 아래로 정렬합니다.",
        "3. 작은 본문 글씨도 놓치지 않아야 합니다.",
        "4. Recognized text is sorted top to bottom.",
    ]
    y = 240
    for text in bullets:
        draw.text((64, y), text, fill=INK, font=font(30))
        y += 64

    # Highlighted phrase inside the last Korean bullet, mimicking a marker.
    draw.text((64, y + 12), "이렇게 강조된 코드 스타일 텍스트도 읽습니다.", fill=INK, font=font(30))

    # Bottom band from the "next slide" teaser.
    band_top = 600
    draw.rectangle([0, band_top, SIZE[0], band_top + 120], fill=(28, 30, 46))
    draw.text((140, band_top + 34), "다음 장에서 계속 학습할 예정입니다.", fill=BG, font=font(48, index=1))

    img.save(OUT, "JPEG", quality=92)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
