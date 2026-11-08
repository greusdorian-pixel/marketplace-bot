"""Genera productos.json y fotos optimizadas para Marketplace a partir de los datos del catalogo."""
import json, math, os, re, sys
from PIL import Image, ImageOps

CATALOGO, FOTOS = sys.argv[1], sys.argv[2]
BASE = os.path.dirname(os.path.abspath(__file__))

src = open(CATALOGO, encoding="utf-8").read().split("def thumb")[0]
src = re.sub(r"SRC, OUT, THUMBS = .*\n|os\.makedirs\(THUMBS.*\n", "", src)
datos = {}
exec(src, datos)

FOTOS_EXTRA = {
    "175827": ["175830"], "180224": ["180201"], "180559": ["180609"], "180240": ["180236"],
    "175834": ["175803"], "180800": ["180744", "180819", "180828"],
    "191204": ["191112", "191211", "191121"], "192045": ["192050", "191935", "191946"],
    "191603": ["191504", "191608", "191616"], "190901": ["191026"],
    "172208": ["172247", "172148", "171950"], "172947": ["172719", "172924", "172936"],
    "180402": ["180429"], "180516": ["180532"], "175813": ["175818"], "180603": ["180613"],
}
USADOS = {"172208", "172947"}  # bomba y breaker se ven usados
CATEGORIA = lambda nombre: "Herramientas"

def precio_num(txt):
    m = re.findall(r"[\d.,]+", txt)
    return math.ceil(float(m[0].replace(".", "").replace(",", "."))) if m else None

def foto(code, carpeta):
    out = os.path.join(carpeta, code + ".jpg")
    im = ImageOps.exif_transpose(Image.open(os.path.join(FOTOS, f"20261011_{code}.jpg"))).convert("RGB")
    im.thumbnail((1400, 1400))
    im.save(out, quality=82, optimize=True)
    return out

productos = []
items = [(n, m, c, f, r, p) for n, m, c, f, r, p in datos["LISTA"]]
items += [(n, m, c, f, *datos["PRECIOS_EXTRA"][c]) for n, m, c, f in datos["EXTRA"]]
for i, (nombre, marca, code, feats, ref, remate) in enumerate(items, 1):
    carpeta = os.path.join(BASE, "fotos", f"{i:02d}")
    os.makedirs(carpeta, exist_ok=True)
    fotos = [foto(c, carpeta) for c in [code] + FOTOS_EXTRA.get(code, [])]
    titulo = f"{nombre.replace(chr(34), ' pulg')} {marca.split(' - ')[0]}".replace("  ", " ")[:99]
    desc = "\n".join([f"{nombre} - {marca}", ""] + ["- " + f for f in feats] +
                     ["", f"Precio en tienda: {ref}", "Remate por liquidación. Precio negociable.", "Pregunta por disponibilidad."])
    productos.append({
        "id": f"{i:02d}", "titulo": titulo,
        "precio": precio_num(remate) or precio_num(ref),  # None = Consultar
        "categoria": CATEGORIA(nombre),
        "estado": "Usado - Buen estado" if code in USADOS else "Nuevo",
        "descripcion": desc, "fotos": [os.path.relpath(f, BASE) for f in fotos],
    })

json.dump(productos, open(os.path.join(BASE, "productos.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print(len(productos), "productos")
for p in productos: print(p["id"], p["precio"], p["titulo"])
