import sys, os, io
from PIL import Image, ImageOps
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Table, TableStyle,
                                Spacer, Image as RLImage, PageBreak, KeepTogether)

SRC, OUT, THUMBS = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(THUMBS, exist_ok=True)

LISTA = [
    ("Disco diamantado para granito 5\" y 7\"", "Carioca - segmentado", "175827",
     ["7\" (180 mm) y 5\" (125 mm), eje 7/8\" (22,2 mm)", "Corte seco, rin segmentado", "Para granito, ladrillo y bloque", "8.600 rpm (7\") / 13.280 rpm (5\")"],
     "$18 - $34", "$16,00"),
    ("Disco diamantado continuo 9\" para cerámica", "Carioca - cód. 00639302", "180224",
     ["9\" (230 mm), eje 7/8\" con reductor 5/8\"", "Rin continuo, corte húmedo", "Cortes limpios en losa, cerámica y mármol", "6.600 rpm máx."],
     "$30 - $60", "$27,00"),
    ("Disco copa diamante para desbaste 7\"", "Carioca - cód. 00639297", "180559",
     ["7\" (180 mm), eje 7/8\" (22,2 mm)", "24 dientes, doble hilera", "Desbaste de concreto y piedra", "8.600 rpm máx."],
     "$42 - $71", "$38,00"),
    ("Disco diamantado continuo 180 mm", "Norton Classic", "180240",
     ["180 x 22,23 mm, rin continuo", "Para cerámica y porcelanato", "8.500 rpm máx."],
     "$28 - $37", "$25,00"),
    ("Disco diamantado láser segmentado 12\"", "Carioca", "175834",
     ["12\" (300 mm) x 25,4 mm", "Tecnología láser, rin segmentado", "Corte seco en concreto, ladrillo y piedra"],
     "$46 - $64", "$42,00"),
    ("Luminaria industrial High Bay UFO 200W", "EvLite", "180800",
     ["200 W, 20.000 lúmenes", "6.500 K luz fría, CRI 70", "110-240 V", "1 año de garantía"],
     "$68 - $80", "$60,00"),
    ("Reflector LED Jeta 200W", "Sylvania - cód. P29774", "191204",
     ["200 W, 20.000 lm (100 lm/W)", "110-277 V, factor de potencia >0,9", "6.500 K, IP65, uso interior/exterior", "Vida útil 50.000 h"],
     "$110 - $196", "$95,00"),
    ("Luminaria LED exterior 200W", "Bellalux", "192045",
     ["200 W, 16.000 lm", "IP65, IK06, cuerpo de aluminio", "100-240 V, ángulo 110°", "Vida útil 10.000 h"],
     "$90 - $150", "$80,00"),
    ("Reflector LED tableta 100W", "Mercury", "191603",
     ["100 W, LED SMD", "Luz blanca 6.500 K", "IP65, uso exterior", "Vida útil 30.000 h, 2 años de garantía"],
     "$45 - $90", "$40,00"),
    ("Lámpara LED de techo 16W", "General Lighting - LED 31501-1", "190901",
     ["16 W, 1.200 lm, luz blanca 6.500 K", "Sobreponer, cuadrada, blanco mate", "Multivoltaje 100-277 V"],
     "$24 - $52", "$22,00"),
    ("Bomba sumergible 0,5 HP", "Pearl Minisub - 4MSP 05A16S", "172208",
     ["0,5 HP, 115 V monofásica", "Altura máx. 50 m (164 ft)", "Caudal máx. 25 gpm", "Acero inoxidable, protección térmica, cert. CSA"],
     "$450 - $570", "$400,00"),
    ("Protector de circuito de motor 250A", "Cutler-Hammer HMCP250J5W", "172947",
     ["250 A, 3 polos, 600 VAC / 250 VDC", "Series C, disparo instantáneo ajustable 875-1.750 A", "Hecho en EE.UU."],
     "$2.546", "$1.900,00"),
]
EXTRA = [
    ("Disco de sierra para aluminio 10\" 80T", "DeWalt - DWA03210", "180402", ["10\", 80 dientes", "Para aluminio", "Eje 30 mm con adaptadores"]),
    ("Disco de sierra 180 mm 60T", "Global - TCT", "180516", ["180 mm (7\") x 60 dientes", "Carburo de tungsteno", "Madera, PVC, fibra de vidrio", "8.500 rpm máx."]),
    ("Disco de sierra dientes finos", "Carioca", "180408", ["Dientes de carburo", "Medida por confirmar"]),
    ("Disco diamantado segmentado 14\"", "Diamond Blade", "175813", ["14\" (350 mm), uso pesado", "Corte seco", "Concreto, ladrillo, piedra y concreto armado"]),
    ("Disco diamantado 180 mm", "Better Diamond Wheel", "175823", ["180 mm segmentado", "Mármol, granito y cerámica", "8.600 rpm máx."]),
    ("Disco copa diamante 4½\"", "Carioca - cód. 00639296", "180603", ["4½\" (115 mm), eje 7/8\"", "16 dientes, desbaste", "13.200 rpm máx."]),
    ("Disco diamantado para cerámica 4½\"", "Carioca", "180227", ["4½\" (115 mm), eje 7/8\"", "Rin turbo multiuso", "12.200 rpm máx."]),
    ("Disco diamantado segmentado 110 mm", "Norton Classic", "180231", ["110 x 22,23 mm", "Concreto, tejas y ladrillo"]),
]
PRECIOS_EXTRA = {  # codigo foto -> (tienda, remate), referencia tiendas EE.UU.
    "180402": ("$60 - $90", "$55,00"), "180516": ("$15 - $25", "$18,00"),
    "180408": ("$45 - $80", "$40,00"), "175813": ("$57 - $80", "$50,00"),
    "175823": ("$13 - $34", "$15,00"), "180603": ("$35 - $52", "$30,00"),
    "180227": ("$10 - $29", "$10,00"), "180231": ("$8 - $16", "$8,00"),
}

def thumb(code):
    out = os.path.join(THUMBS, code + ".jpg")
    if not os.path.exists(out):
        im = ImageOps.exif_transpose(Image.open(os.path.join(SRC, f"20261011_{code}.jpg"))).convert("RGB")
        im.thumbnail((700, 700))
        im.save(out, quality=72, optimize=True)
    w, h = Image.open(out).size
    s = min(62*mm / w, 62*mm / h)
    return RLImage(out, w*s, h*s)

ORANGE = colors.HexColor("#E8590C"); DARK = colors.HexColor("#1F2933"); GREY = colors.HexColor("#6B7280")
st = lambda **k: ParagraphStyle("x", **{"fontName": "Helvetica", **k})
sTitle = st(fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=DARK)
sBrand = st(fontSize=9.5, leading=12, textColor=GREY)
sFeat = st(fontSize=9, leading=12, textColor=DARK)
sRef = st(fontSize=9, leading=12, textColor=GREY)
sPrice = st(fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=ORANGE)

def card(name, brand, code, feats, ref, rem):
    txt = [Paragraph(name, sTitle), Paragraph(brand, sBrand), Spacer(1, 4)]
    txt += [Paragraph("• " + f, sFeat) for f in feats]
    txt += [Spacer(1, 6)]
    if ref == rem == "Consultar":
        txt += [Paragraph("Precio: CONSULTAR", sPrice)]
    else:
        txt += [Paragraph(f"Precio en tienda: <strike>{ref}</strike>", sRef),
                Paragraph(f"REMATE: {rem}", sPrice)]
    t = Table([[thumb(code), txt]], colWidths=[66*mm, 108*mm])
    t.setStyle(TableStyle([("VALIGN", (0,0), (-1,-1), "MIDDLE"),
                           ("BOX", (0,0), (-1,-1), 0.6, colors.HexColor("#D1D5DB")),
                           ("LEFTPADDING", (0,0), (-1,-1), 6), ("RIGHTPADDING", (0,0), (-1,-1), 6),
                           ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6)]))
    return KeepTogether([t, Spacer(1, 5*mm)])

def header(c, doc):
    c.saveState()
    c.setFillColor(DARK); c.rect(0, A4[1]-18*mm, A4[0], 18*mm, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont("Helvetica-Bold", 16)
    c.drawString(18*mm, A4[1]-12*mm, "CATÁLOGO DE REMATE")
    c.setFillColor(ORANGE); c.setFont("Helvetica-Bold", 10)
    c.drawRightString(A4[0]-18*mm, A4[1]-12*mm, "Precios en USD · Hasta agotar stock")
    c.setFillColor(GREY); c.setFont("Helvetica", 8)
    c.drawCentredString(A4[0]/2, 10*mm, f"Página {doc.page}")
    c.restoreState()

doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm, topMargin=26*mm, bottomMargin=18*mm,
                        title="Catálogo de Remate")
sSec = st(fontName="Helvetica-Bold", fontSize=12, leading=16, textColor=ORANGE, spaceAfter=6)
flow = [Paragraph("DISCOS DE CORTE Y DESBASTE", sSec)]
for i, p in enumerate(LISTA):
    if i == 5: flow.append(Paragraph("ILUMINACIÓN LED", sSec))
    if i == 10: flow.append(Paragraph("BOMBAS Y ELÉCTRICOS", sSec))
    flow.append(card(*p))
flow += [PageBreak(), Paragraph("OTROS PRODUCTOS EN REMATE", sSec)]
for name, brand, code, feats in EXTRA:
    ref, rem = PRECIOS_EXTRA.get(code, ("Consultar", "Consultar"))
    flow.append(card(name, brand, code, feats, ref, rem))
doc.build(flow, onFirstPage=header, onLaterPages=header)
print(os.path.getsize(OUT)//1024, "KB")
