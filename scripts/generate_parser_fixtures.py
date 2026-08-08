"""Generate small deterministic parser capability fixtures."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "backend" / "assets"
OUTPUT.mkdir(parents=True, exist_ok=True)


def font(size: int, bold: bool = False):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def avatar(size=110):
    image = Image.new("RGB", (size, size), "#dce7f8")
    draw = ImageDraw.Draw(image)
    draw.ellipse((34, 16, 76, 58), fill="#617aa5")
    draw.rounded_rectangle((21, 60, 89, 104), radius=22, fill="#617aa5")
    return image


def code_badge(text: str, width=250, height=54):
    image = Image.new("RGB", (width, height), "#eef4ff")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=8, outline="#4f6f9f", width=2)
    draw.text((14, 15), text, fill="#18304f", font=font(19, True))
    return image


def generate_page(code: str):
    image = Image.new("RGB", (900, 1160), "white")
    draw = ImageDraw.Draw(image)
    dark, muted, line = "#17243a", "#53627a", "#d8e0ec"
    draw.text((58, 52), "LIN YANZHEN", fill=dark, font=font(38, True))
    draw.text((58, 103), "Backend Engineer", fill="#466896", font=font(21, True))
    image.paste(avatar(118), (714, 45))
    draw.line((58, 177, 842, 177), fill=line, width=3)
    draw.text((58, 205), "CONTACT", fill=dark, font=font(19, True))
    draw.text((58, 244), "Phone: 13800001234", fill=muted, font=font(18))
    draw.text((58, 276), "Email: parser-check@example.com", fill=muted, font=font(18))
    draw.text((58, 335), "SKILLS", fill=dark, font=font(19, True))
    draw.text((58, 374), "- Python\n- FastAPI\n- SQL", fill=muted, font=font(18), spacing=12)
    draw.line((342, 205, 342, 1040), fill=line, width=2)
    draw.text((382, 205), "EDUCATION", fill=dark, font=font(19, True))
    draw.text((382, 247), "QINGLAN UNIVERSITY", fill=dark, font=font(18, True))
    draw.text((382, 280), "Software Engineering | 2020.09 - 2024.06", fill=muted, font=font(17))
    draw.text((382, 350), "EXPERIENCE", fill=dark, font=font(19, True))
    draw.text((382, 392), "XINGHE TECHNOLOGY", fill=dark, font=font(18, True))
    draw.text((382, 425), "Backend Engineer | 2024.07 - Present", fill=muted, font=font(17))
    draw.text((382, 472), "- Built reliable API services", fill=muted, font=font(17))
    image.paste(code_badge(f"VISUAL CODE: {code}"), (382, 550))
    draw.text((58, 1085), "Parser capability fixture - not a real resume", fill="#8a96a8", font=font(15))
    return image


def generate_png(path: Path):
    generate_page("IMG-4827").save(path, optimize=True)


def generate_pdf(path: Path):
    # A raster-only PDF intentionally prevents text extraction from passing the
    # test without actual page vision/OCR support.
    generate_page("PDF-7319").save(path, "PDF", resolution=144.0)


if __name__ == "__main__":
    generate_png(OUTPUT / "parser_fixture.png")
    generate_pdf(OUTPUT / "parser_fixture.pdf")
    print(OUTPUT)
