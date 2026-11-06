"""Empaqueta el explorador con código, librerías, cartografía y datos."""
from pathlib import Path
import argparse
import json
import re


def build_standalone(output=None):
    here = Path(__file__).resolve().parent
    root = here if (here/'app').exists() else here.parent  # módulos en src/ dentro del repositorio
    base = root/'app/dist'
    html = (base/'index.html').read_text()
    def embed_style(match):
        filename = match.group(1).split('?')[0]
        source = (base/filename).read_text()
        return '<style>'+source+'</style>'
    html = re.sub(r'<link rel="stylesheet" href="([^"]+)">',embed_style,html)
    scripts = re.findall(r'<script defer src="([^"]+)"></script>',html)
    html = re.sub(r'<script defer src="[^"]+"></script>','',html)
    end = ''
    for tag,filename in [('atlas-world-data','world.geojson'),
                         ('atlas-network-data','network.json'),
                         ('atlas-extensions-data','extensions.json'),
                         ('atlas-interactive-data','interactive.json'),
                         ('atlas-exploration-data','exploration.json')]:
        data = json.loads((base/'data'/filename).read_text())
        encoded = json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        encoded = encoded.replace('<',chr(92)+'u003c')
        end += '<script type="application/json" id="'+tag+'">'+encoded+'</script>'
    for filename in scripts:
        filename = filename.split('?')[0]
        source = (base/filename).read_text()
        if filename=='vendor/leaflet/leaflet.js':
            license_text = (base/'vendor/leaflet/LICENSE').read_text()
            source = '/* Leaflet license: '+license_text.replace('*/','* /')+' */'+source
        # Callable avoids replacement-string interpretation of the JS slash.
        source = re.sub('</script',lambda _: '<'+chr(92)+'/script',source,flags=re.I)
        end += '<script>'+source+'</script>'
    html = html.replace('</body>',end+'</body>')
    target = Path(output) if output else root/'Atlas_Carga_Aerea_2025.html'
    target.write_text(html,encoding='utf-8')
    print(target,target.stat().st_size,'bytes')
    return target


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path)
    args = parser.parse_args()
    build_standalone(args.output)
