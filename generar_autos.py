#!/usr/bin/env python3
"""
AutoPanel · Generador de la biblioteca de autos en PNG sin fondo.

Qué hace, por cada auto de modelos.txt:
  1. Busca fotos con licencia libre en Wikimedia Commons.
  2. Les quita el fondo con rembg (código abierto, se puede usar comercialmente).
  3. Revisa que el recorte haya quedado bien (auto completo, de lado o 3/4).
  4. Guarda el mejor PNG en biblioteca/autos/ y alternativas en biblioteca/revisar/.
  5. Actualiza biblioteca/index.json (lo que lee la app) y biblioteca/CREDITOS.md.

Uso:
  python generar_autos.py                      -> procesa todo modelos.txt (se salta los ya hechos)
  python generar_autos.py "Nissan|Versa|2018"  -> procesa solo ese auto
  python generar_autos.py --forzar ...         -> vuelve a generar aunque ya exista
  python generar_autos.py --usar nissan-versa 2  -> cambia la imagen por la alternativa 2
  python generar_autos.py --propia nissan-versa foto.jpg "Foto: Juan Pérez"
                                               -> usa una foto tuya (con permiso) para ese auto
  python generar_autos.py --cliente jhon foto.jpg
                                               -> PNG sin fondo del carro de un cliente (carpeta clientes/)

Instalar una sola vez:
  pip install "rembg[cpu]" pillow requests
"""
import io
import json
import os
import re
import shutil
import sys
import time
import unicodedata

try:
    import requests
    from PIL import Image
except ImportError:
    sys.exit('Falta instalar: pip install "rembg[cpu]" pillow requests')

AQUI = os.path.dirname(os.path.abspath(__file__))
# En GitHub Actions la biblioteca es la raíz del repositorio (BIB=.); en tu laptop, la carpeta "biblioteca".
BIB = os.path.abspath(os.environ.get("BIB", os.path.join(AQUI, "biblioteca")))
AUTOS = os.path.join(BIB, "autos")
REVISAR = os.path.join(BIB, "revisar")
INDEX = os.path.join(BIB, "index.json")
UA = "AutoPanelLibraryBuilder/1.0 (autopanel.launcher@gmail.com) python-requests"
API = "https://commons.wikimedia.org/w/api.php"

ANCHO_FINAL = 1200      # px del PNG final (suficiente para pantallas de radio)
VARIANTES = 3           # cuántos recortes buenos guardar por auto
MAX_FOTOS = 14          # cuántas fotos probar como máximo por auto

PALABRAS_MALAS = [
    "interior", "engine", "motor ", "dashboard", "cockpit", "logo", "badge", "emblem", " wheel",
    "steering", "instrument", "headlight", "taillight", "tail light", "head light", "detail",
    "grille", "tyre", " tire", "mirror", "console", "airbag", "crash", "accident", "wreck",
    "model car", "scale model", "lego", "diecast", "die-cast", "brochure", "poster", "trunk",
    "cargo", "police", "taxi", "polic", "ambulance", "rally", " race", "tuning", "modified",
    "convoy", "parade", "show floor", "auction", "rust", "abandoned", "junk",
    "itasha", "anime", "decal", "sticker", "livery", "wrap", "cabrio", "convertible"]


# ----------------------------------------------------------------- utilidades

def slug(texto):
    """'Volkswagen Jetta Clásico' -> 'volkswagen-jetta-clasico' (igual que en la app)."""
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")


def cargar_index():
    if os.path.exists(INDEX):
        with open(INDEX, encoding="utf-8") as f:
            return json.load(f)
    return {"version": 1, "autos": []}


def guardar_index(idx):
    idx["autos"].sort(key=lambda a: (a["marca"].lower(), a["modelo"].lower(), a.get("anio", "")))
    idx["actualizado"] = time.strftime("%Y-%m-%d %H:%M")
    with open(INDEX, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=1)
    with open(os.path.join(BIB, "CREDITOS.md"), "w", encoding="utf-8") as f:
        f.write("# Créditos de las imágenes\n\n")
        f.write("Las imágenes son recortes (sin fondo) de fotos de Wikimedia Commons, publicadas "
                "con licencias libres. Cada recorte se comparte bajo la misma licencia que su "
                "foto original, citando a su autor.\n\n")
        f.write("| Auto | Autor y licencia | Original |\n|---|---|---|\n")
        for a in idx["autos"]:
            nombre = f'{a["marca"]} {a["modelo"]} {a.get("anio", "")}'.strip()
            f.write(f'| {nombre} | {a.get("credito", "")} | {a.get("fuente", "")} |\n')


def clave(marca, modelo, anio):
    return slug(f"{marca} {modelo} {anio}".strip())


def http_json(params):
    params = dict(params, format="json", formatversion="2")
    r = requests.get(API, params=params, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.json()


def limpiar_html(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    return re.sub(r"\s+", " ", s).strip()[:80]


# ----------------------------------------------------------------- búsqueda en Commons

def buscar_fotos(marca, modelo, anio, busqueda=""):
    """Devuelve candidatos ordenados del más prometedor al menos."""
    consultas = []
    if busqueda:
        consultas.append(busqueda)
    if anio:
        consultas.append(f"{anio} {marca} {modelo}")
    consultas.append(f"{marca} {modelo}")
    m = slug(modelo).split("-")[0]
    b = slug(marca).split("-")[0]
    vistos, cands = set(), []
    for q in consultas:
        data = http_json({
            "action": "query", "generator": "search", "gsrnamespace": 6, "gsrlimit": 50,
            "gsrsearch": q + " filetype:bitmap",
            "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1600,
            "iiextmetadatafilter": "Artist|LicenseShortName|LicenseUrl",
        })
        for pg in data.get("query", {}).get("pages", []):
            titulo = pg.get("title", "")
            t = slug(titulo).replace("-", " ")
            info = (pg.get("imageinfo") or [{}])[0]
            if info.get("mime") != "image/jpeg":
                continue
            w, h = info.get("width", 0), info.get("height", 0)
            if w < 900 or h < 450 or w < h * 1.15:
                continue
            if m not in t.split() and m not in t:
                continue
            if any(p.strip() in t for p in PALABRAS_MALAS):
                continue
            url = info.get("thumburl") or info.get("url")
            if not url or url in vistos:
                continue
            vistos.add(url)
            meta = info.get("extmetadata", {})
            autor = limpiar_html(meta.get("Artist", {}).get("value", "")) or "autor en Wikimedia Commons"
            lic = meta.get("LicenseShortName", {}).get("value", "")
            score = 100 - pg.get("index", 50)
            if b in t: score += 20
            if anio and anio in t: score += 30
            # se prefiere la vista 3/4 de frente (como en las pantallas de fábrica)
            if any(x in t for x in ("front", "frontal", "vorne", "avant", "3 4", "three quarter", "frontansicht")): score += 35
            if any(x in t for x in ("side", "seitenansicht", "lateral", "profile")): score -= 5
            if any(x in t for x in ("rear", "heck", "arriere", "trasera", "back")): score -= 40
            cands.append({
                "url": url, "titulo": titulo, "score": score,
                "credito": f"Foto: {autor}" + (f" · {lic}" if lic else "") + " · Wikimedia Commons",
                "licencia": lic,
                "fuente": info.get("descriptionurl", "https://commons.wikimedia.org/wiki/" + titulo.replace(" ", "_")),
            })
    cands.sort(key=lambda c: -c["score"])
    return cands


# ----------------------------------------------------------------- recorte

_sesion = None


def quitar_fondo(img):
    global _sesion
    from rembg import remove, new_session
    if _sesion is None:
        print("   (cargando el modelo de recorte; la primera vez descarga ~170 MB)")
        _sesion = new_session("isnet-general-use")
    return remove(img, session=_sesion, post_process_mask=True)


def recorte_valido(png):
    """Revisa el recorte y lo ajusta a su contorno. Devuelve la imagen o None."""
    a = png.getchannel("A")
    w, h = png.size
    caja = a.point(lambda v: 255 if v > 40 else 0).getbbox()
    if not caja:
        return None, "vacío"
    x0, y0, x1, y1 = caja
    bw, bh = x1 - x0, y1 - y0
    if bw < w * 0.35:
        return None, "auto muy pequeño"
    if bw < bh * 1.15:
        return None, "auto de frente o cortado"
    # el auto no debe quedar cortado por el borde de la foto
    margen = 3
    if x0 <= margen or x1 >= w - margen:
        return None, "auto cortado por la orilla"
    # proporción de pixeles del auto dentro de su caja: muy baja = recorte roto
    hist = a.crop(caja).point(lambda v: 255 if v > 40 else 0).histogram()
    lleno = hist[255] / float(bw * bh)
    if lleno < 0.45 or lleno > 0.97:
        return None, "recorte irregular"
    # varios pedazos sueltos = probablemente recortó otras cosas (gente, otros autos)
    piezas = contar_piezas(a.crop(caja).resize((max(1, bw // 8), max(1, bh // 8))))
    if piezas > 3:
        return None, "recortó objetos extra"
    pad = max(4, bw // 100)
    out = png.crop((max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad)))
    if out.width > ANCHO_FINAL:
        out = out.resize((ANCHO_FINAL, round(out.height * ANCHO_FINAL / out.width)), Image.LANCZOS)
    return out, "ok"


def contar_piezas(mask):
    """Cuenta manchas grandes y separadas en una máscara chica."""
    w, h = mask.size
    px = mask.load()
    visto = [[False] * w for _ in range(h)]
    grandes = 0
    for y in range(h):
        for x in range(w):
            if visto[y][x] or px[x, y] <= 40:
                continue
            pila, n = [(x, y)], 0
            visto[y][x] = True
            while pila:
                cx, cy = pila.pop()
                n += 1
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not visto[ny][nx] and px[nx, ny] > 40:
                        visto[ny][nx] = True
                        pila.append((nx, ny))
            if n > (w * h) * 0.02:
                grandes += 1
    return grandes


# ----------------------------------------------------------------- proceso

def procesar(marca, modelo, anio, busqueda="", forzar=False):
    k = clave(marca, modelo, anio)
    nombre = f"{marca} {modelo} {anio}".strip()
    idx = cargar_index()
    if not forzar and any(a["clave"] == k for a in idx["autos"]) and os.path.exists(os.path.join(AUTOS, k + ".png")):
        print(f"✓ {nombre}: ya existe (usa --forzar para rehacerlo)")
        return True
    print(f"→ {nombre}")
    try:
        cands = buscar_fotos(marca, modelo, anio, busqueda)
    except Exception as e:
        print(f"   ✗ no pude buscar en Commons: {e}")
        return False
    if not cands:
        print("   ✗ no hay fotos útiles en Commons; revisa cómo está escrito o usa --propia")
        return False
    dir_rev = os.path.join(REVISAR, k)
    shutil.rmtree(dir_rev, ignore_errors=True)
    os.makedirs(dir_rev, exist_ok=True)
    buenas = []
    for c in cands[:MAX_FOTOS]:
        try:
            r = requests.get(c["url"], headers={"User-Agent": UA}, timeout=60)
            r.raise_for_status()
            img = Image.open(io.BytesIO(r.content)).convert("RGB")
            png = quitar_fondo(img).convert("RGBA")
            out, motivo = recorte_valido(png)
        except Exception as e:
            out, motivo = None, f"error: {e}"
        if out is None:
            print(f"   · descartada ({motivo}): {c['titulo'][:60]}")
            continue
        n = len(buenas) + 1
        out.save(os.path.join(dir_rev, f"{n}.png"), optimize=True)
        buenas.append(dict(c, n=n))
        print(f"   ✓ alternativa {n}: {c['titulo'][:60]}")
        if len(buenas) >= VARIANTES:
            break
        time.sleep(0.5)  # cortesía con los servidores de Wikimedia
    if not buenas:
        print("   ✗ ninguna foto quedó bien recortada; prueba con --propia")
        return False
    with open(os.path.join(dir_rev, "info.json"), "w", encoding="utf-8") as f:
        json.dump({"marca": marca, "modelo": modelo, "anio": anio, "alternativas": buenas}, f,
                  ensure_ascii=False, indent=1)
    publicar(k, marca, modelo, anio, buenas[0], os.path.join(dir_rev, "1.png"))
    print(f"   ★ listo: autos/{k}.png  (revisa las alternativas en revisar/{k}/)")
    return True


def publicar(k, marca, modelo, anio, c, ruta_png):
    os.makedirs(AUTOS, exist_ok=True)
    shutil.copyfile(ruta_png, os.path.join(AUTOS, k + ".png"))
    idx = cargar_index()
    idx["autos"] = [a for a in idx["autos"] if a["clave"] != k]
    idx["autos"].append({
        "clave": k, "marca": marca, "modelo": modelo, "anio": anio,
        "archivo": f"autos/{k}.png", "credito": c["credito"],
        "licencia": c.get("licencia", ""), "fuente": c.get("fuente", ""),
    })
    guardar_index(idx)


def usar_alternativa(k, n):
    dir_rev = os.path.join(REVISAR, k)
    try:
        with open(os.path.join(dir_rev, "info.json"), encoding="utf-8") as f:
            info = json.load(f)
    except FileNotFoundError:
        sys.exit(f"No hay alternativas para «{k}». Primero genera ese auto.")
    alt = [a for a in info["alternativas"] if a["n"] == n]
    if not alt:
        sys.exit(f"«{k}» solo tiene {len(info['alternativas'])} alternativas.")
    publicar(k, info["marca"], info["modelo"], info["anio"], alt[0], os.path.join(dir_rev, f"{n}.png"))
    print(f"✓ {k} ahora usa la alternativa {n}")


def usar_propia(k, ruta, credito):
    idx = cargar_index()
    prev = [a for a in idx["autos"] if a["clave"] == k]
    if prev:
        marca, modelo, anio = prev[0]["marca"], prev[0]["modelo"], prev[0].get("anio", "")
    else:
        partes = input("Escribe Marca|Modelo|Año de esta foto: ").split("|") + ["", ""]
        marca, modelo, anio = partes[0].strip(), partes[1].strip(), partes[2].strip()
        k = clave(marca, modelo, anio)
    img = Image.open(ruta).convert("RGB")
    out, motivo = recorte_valido(quitar_fondo(img).convert("RGBA"))
    if out is None:
        sys.exit(f"La foto no quedó bien ({motivo}). Usa una foto del auto completo, de lado o 3/4.")
    os.makedirs(os.path.join(REVISAR, k), exist_ok=True)
    tmp = os.path.join(REVISAR, k, "propia.png")
    out.save(tmp, optimize=True)
    publicar(k, marca, modelo, anio, {"credito": credito, "licencia": "", "fuente": ""}, tmp)
    print(f"✓ {k} usa tu foto")


def foto_cliente(nombre, ruta):
    """PNG sin fondo del carro de un cliente. NO se publica en la biblioteca."""
    img = Image.open(ruta).convert("RGB")
    out, motivo = recorte_valido(quitar_fondo(img).convert("RGBA"))
    if out is None:
        sys.exit(f"La foto no quedó bien ({motivo}). Toma el carro completo, de 3/4 de frente, sin nada enfrente.")
    carpeta = os.path.join(AQUI, "clientes")
    os.makedirs(carpeta, exist_ok=True)
    destino = os.path.join(carpeta, slug(nombre) + ".png")
    out.save(destino, optimize=True)
    print(f"✓ Listo: {destino}\n  Pásalo al radio y elígelo en Ajustes → «Usar foto del carro».")


def leer_modelos():
    ruta = os.path.join(AQUI, "modelos.txt")
    autos = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            linea = linea.split("#")[0].strip()
            if not linea:
                continue
            p = [x.strip() for x in linea.split("|")] + ["", "", ""]
            if p[0] and p[1]:
                autos.append((p[0], p[1], p[2], p[3]))
    return autos


def main():
    args = sys.argv[1:]
    forzar = "--forzar" in args
    args = [a for a in args if a != "--forzar"]
    os.makedirs(AUTOS, exist_ok=True)
    os.makedirs(REVISAR, exist_ok=True)
    if args[:1] == ["--usar"] and len(args) == 3:
        return usar_alternativa(args[1], int(args[2]))
    if args[:1] == ["--cliente"] and len(args) == 3:
        return foto_cliente(args[1], args[2])
    if args[:1] == ["--propia"] and len(args) >= 3:
        return usar_propia(args[1], args[2], args[3] if len(args) > 3 else "Foto: propia")
    if args:
        autos = []
        for a in args:
            p = [x.strip() for x in a.split("|")] + ["", "", ""]
            if not (p[0] and p[1]):
                sys.exit('Formato: "Marca|Modelo|Año|Búsqueda"   (año y búsqueda son opcionales)')
            autos.append((p[0], p[1], p[2], p[3]))
    else:
        autos = leer_modelos()
    faltan = []
    ok = 0
    for a in autos:
        if procesar(*a, forzar=forzar):
            ok += 1
        else:
            faltan.append(" | ".join(x for x in a[:3] if x))
    print(f"\nTerminado: {ok} de {len(autos)} autos con imagen.")
    with open(os.path.join(BIB, "FALTAN.md"), "w", encoding="utf-8") as f:
        f.write("# Autos sin imagen\n\nNo hubo foto libre que quedara bien recortada. "
                "Prueba escribiéndolos distinto en modelos.txt o agrega el año.\n\n")
        for x in faltan:
            f.write(f"- {x}\n")
    print("Sube la carpeta 'biblioteca' a tu repositorio de GitHub (ver LEEME.md).")


if __name__ == "__main__":
    main()
