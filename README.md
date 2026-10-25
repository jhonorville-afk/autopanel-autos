# autopanel-autos

Biblioteca de autos **en PNG sin fondo** para el launcher AutoPanel.
Las imágenes se generan solas en los servidores de GitHub (gratis) y cada radio descarga
la del auto de su cliente.

## Cómo funciona

1. Escribes los autos en `modelos.txt` (`Marca | Modelo | Año`; el año es opcional).
2. Al guardar, GitHub corre `generar_autos.py`, que:
   - busca fotos con **licencia libre** en Wikimedia Commons (prefiere 3/4 de frente),
   - les **quita el fondo** con rembg (código abierto),
   - revisa que el recorte haya quedado bien,
   - publica `autos/*.png`, `index.json` (lo que lee la app), `CREDITOS.md` y `FALTAN.md`.
3. Los radios descargan la imagen automáticamente. El cliente no hace nada.

## Puesta en marcha (una sola vez)

### Desde la laptop (lo más fácil)
1. Crea una cuenta en https://github.com.
2. **New repository** → nombre: **`autopanel-autos`** → **Public** → marca **Add a README file** → **Create repository**.
3. **Add file → Upload files** y arrastra **todo** el contenido de esta carpeta
   (incluida la carpeta `.github`) → **Commit changes**.

### Desde el celular
1. Pasos 1 y 2 de arriba.
2. **Add file → Upload files**: sube `generar_autos.py` y `modelos.txt`.
3. **Add file → Create new file**, escribe como nombre
   `.github/workflows/generar.yml`, pega el contenido de ese archivo → **Commit changes**.

### Dar permiso para publicar
**Settings → Actions → General → Workflow permissions → Read and write permissions → Save.**

### Generar la primera vez
Pestaña **Actions** → (si lo pide, **I understand… enable**) → **Generar autos** → **Run workflow**.
La primera vez tarda entre 30 y 90 minutos. Al terminar verás la carpeta `autos` llena.

## Uso diario

- **Agregar autos:** edita `modelos.txt` (ícono del lápiz), agrega líneas y guarda. Se generan solos.
- **Autos que no salieron:** revisa `FALTAN.md`; prueba otro nombre o agrega el año.
- **Rehacer todo:** Actions → Generar autos → Run workflow → forzar = `sí`.

## Licencias

Las fotos vienen de Wikimedia Commons con licencias libres (CC BY / CC BY-SA) que permiten
uso comercial dando crédito. Los recortes se comparten con la misma licencia; `CREDITOS.md`
lista autor, licencia y foto original, y la app muestra el crédito debajo del auto.
No agregues fotos de Google Imágenes, agencias o páginas de marcas.
