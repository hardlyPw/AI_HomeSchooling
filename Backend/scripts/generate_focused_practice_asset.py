from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1600
HEIGHT = 1000
ASSET_PATH = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "FocusedPractice"
    / "exponential_error_analysis.png"
)
FONT_DIR = Path("C:/Windows/Fonts")


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), size)


def generate() -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#F7F9FC")
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, WIDTH, 158), fill="#143642")
    draw.text(
        (100, 48),
        "Focused Practice | Lesson 4.1",
        font=font("segoeuib.ttf", 46),
        fill="#FFFFFF",
    )
    draw.text(
        (102, 112),
        "Evaluating exponential functions",
        font=font("segoeui.ttf", 24),
        fill="#D6EBE7",
    )

    draw.rounded_rectangle(
        (100, 205, 1500, 330),
        radius=12,
        fill="#FFFFFF",
        outline="#C9D5DE",
        width=3,
    )
    draw.text((145, 238), "Given", font=font("segoeuib.ttf", 30), fill="#52616B")
    draw.text((340, 224), "f(x) = 2^x", font=font("segoeuib.ttf", 54), fill="#102A43")

    draw.text((110, 390), "A.", font=font("segoeuib.ttf", 40), fill="#0F766E")
    draw.text((180, 390), "Evaluate f(4).", font=font("segoeuib.ttf", 40), fill="#172B4D")
    draw.text(
        (180, 453),
        "Show how you substitute the input into the function.",
        font=font("segoeui.ttf", 28),
        fill="#52616B",
    )

    draw.line((100, 535, 1500, 535), fill="#C9D5DE", width=3)

    draw.text((110, 590), "B.", font=font("segoeuib.ttf", 40), fill="#0F766E")
    draw.text(
        (180, 590),
        "A student writes:",
        font=font("segoeuib.ttf", 40),
        fill="#172B4D",
    )
    draw.rounded_rectangle(
        (180, 660, 1130, 760),
        radius=10,
        fill="#FFF3C4",
        outline="#E0B44C",
        width=3,
    )
    draw.text(
        (225, 681),
        "f(-2) = 2^-2 = -2^2 = -4",
        font=font("segoeuib.ttf", 40),
        fill="#5F4108",
    )
    draw.text(
        (180, 805),
        "Find the mistake. Explain what a negative exponent means,",
        font=font("segoeui.ttf", 28),
        fill="#2F3E46",
    )
    draw.text(
        (180, 850),
        "then give the correct value of f(-2).",
        font=font("segoeui.ttf", 28),
        fill="#2F3E46",
    )

    draw.rectangle((0, 945, WIDTH, HEIGHT), fill="#E6EEF3")
    draw.text(
        (100, 959),
        "Goal: substitute inputs, evaluate powers, and explain negative exponents.",
        font=font("segoeui.ttf", 22),
        fill="#405261",
    )

    ASSET_PATH.parent.mkdir(parents=True, exist_ok=True)
    image.save(ASSET_PATH, optimize=True)
    print(ASSET_PATH)


if __name__ == "__main__":
    generate()
