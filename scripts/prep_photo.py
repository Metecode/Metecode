import sys, os
import numpy as np
import cv2
from PIL import Image
from rembg import remove

def main(src):
    img = Image.open(src).convert("RGBA")

    # 1) arka planı sil
    cut = remove(img)
    arr = np.array(cut)
    rgb, alpha = arr[:, :, :3], arr[:, :, 3]

    # 2) gri tonlama + CLAHE (lokal kontrast)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # 3) özneyi saf beyaz zemine bindir
    a = alpha.astype(np.float32) / 255.0
    out = gray.astype(np.float32) * a + 255.0 * (1.0 - a)
    out = np.clip(out, 0, 255).astype(np.uint8)

    Image.fromarray(out).save("source-prepped.png")
    print("yazildi: source-prepped.png", out.shape)

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "source-photo.jpeg")