from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parents[1]
image = Image.new("RGBA", (256,256), (0,0,0,0))
draw = ImageDraw.Draw(image)
draw.rounded_rectangle((8,8,248,248), radius=44, fill="#f5d775")
font = ImageFont.truetype("C:/Windows/Fonts/msyh.ttc", 172)
draw.text((128,119), "中", font=font, fill="#483a20", anchor="mm")
image.save(root / "src/chinese_screen_dictionary/assets/app.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
