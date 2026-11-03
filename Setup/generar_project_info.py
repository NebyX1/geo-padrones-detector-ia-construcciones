"""Genera Project_Info.pdf. Requiere reportlab; los datos se revisaron el 3/11/2026."""
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, Flowable, Frame, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle,
)

HERE = Path(__file__).resolve().parent
OUT = HERE / 'Project_Info.pdf'
FONT_DIR = Path('C:/Windows/Fonts')
LINUX_DIR = Path('/usr/share/fonts/truetype/dejavu')
if (FONT_DIR / 'segoeui.ttf').exists():
    font_files = [FONT_DIR / 'segoeui.ttf', FONT_DIR / 'segoeuib.ttf', FONT_DIR / 'segoeuii.ttf']
elif (LINUX_DIR / 'DejaVuSans.ttf').exists():
    font_files = [LINUX_DIR / 'DejaVuSans.ttf', LINUX_DIR / 'DejaVuSans-Bold.ttf', LINUX_DIR / 'DejaVuSans-Oblique.ttf']
else:
    raise SystemExit('Se necesitan fuentes Segoe UI o DejaVu Sans para generar el PDF.')
for name, filename in zip(('Body', 'Body-Bold', 'Body-Italic'), font_files):
    pdfmetrics.registerFont(TTFont(name, str(filename)))
pdfmetrics.registerFontFamily('Body', normal='Body', bold='Body-Bold', italic='Body-Italic', boldItalic='Body-Bold')

NAVY = colors.HexColor('#172f56')
INK = colors.HexColor('#20334c')
MUTED = colors.HexColor('#50677c')
TEAL = colors.HexColor('#098c83')
PALE = colors.HexColor('#e9f5f2')
PAPER = colors.HexColor('#f3f6f8')
AMBER = colors.HexColor('#86531a')
PALE_AMBER = colors.HexColor('#fff3db')
RED = colors.HexColor('#a83446')
WIDTH, HEIGHT = A4

ST = {
    'eyebrow': ParagraphStyle('eyebrow', fontName='Body-Bold', fontSize=8, leading=11, textColor=TEAL, spaceAfter=8),
    'title': ParagraphStyle('title', fontName='Body-Bold', fontSize=31, leading=37, textColor=NAVY, spaceAfter=12),
    'subtitle': ParagraphStyle('subtitle', fontName='Body', fontSize=14, leading=20, textColor=MUTED, spaceAfter=18),
    'h1': ParagraphStyle('h1', fontName='Body-Bold', fontSize=22, leading=28, textColor=NAVY, spaceAfter=11),
    'h2': ParagraphStyle('h2', fontName='Body-Bold', fontSize=13, leading=18, textColor=NAVY, spaceBefore=8, spaceAfter=5),
    'body': ParagraphStyle('body', fontName='Body', fontSize=11.2, leading=17, textColor=INK, spaceAfter=8),
    'small': ParagraphStyle('small', fontName='Body', fontSize=9.8, leading=14, textColor=INK, spaceAfter=5),
    'tiny': ParagraphStyle('tiny', fontName='Body', fontSize=8.35, leading=12.3, textColor=INK, spaceAfter=3),
    'card': ParagraphStyle('card', fontName='Body', fontSize=10.5, leading=15.5, textColor=INK),
    'tablehead': ParagraphStyle('tablehead', fontName='Body-Bold', fontSize=9.3, leading=13, textColor=colors.white),
    'table': ParagraphStyle('table', fontName='Body', fontSize=9.7, leading=14, textColor=INK),
}


def P(text, style='body'):
    return Paragraph(text, ST[style])


def H(text):
    return P(text, 'h2')


def section(number, title, intro=None):
    elements = [P(f'GUÍA PARA ENTENDER EL PROYECTO  /  {number:02d}', 'eyebrow'), P(title, 'h1')]
    if intro:
        elements.append(P(intro))
    return elements


def callout(title, text, warning=False):
    bg = PALE_AMBER if warning else PALE
    accent = AMBER if warning else TEAL
    cell = [P(f'<b>{title}</b>', 'card'), Spacer(1, 4), P(text, 'card')]
    table = Table([[cell]], colWidths=[483])
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), bg),
                               ('LINEBEFORE', (0, 0), (0, 0), 3, accent),
                               ('LEFTPADDING', (0, 0), (-1, -1), 12), ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                               ('TOPPADDING', (0, 0), (-1, -1), 10), ('BOTTOMPADDING', (0, 0), (-1, -1), 10)]))
    return [table, Spacer(1, 9)]


def bullet(text):
    row = Table([[P('•', 'body'), P(text, 'body')]], colWidths=[16, 467])
    row.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                             ('RIGHTPADDING', (0, 0), (-1, -1), 0), ('TOPPADDING', (0, 0), (-1, -1), 0),
                             ('BOTTOMPADDING', (0, 0), (-1, -1), 0)]))
    return row


def grid(headers, rows, widths):
    data = [[P(h, 'tablehead') for h in headers]] + [[P(c, 'table') for c in row] for row in rows]
    table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, 0), NAVY),
                               ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, PAPER]),
                               ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                               ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                               ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
                               ('LINEBELOW', (0, 0), (-1, 0), .5, NAVY)]))
    return [table, Spacer(1, 10)]


class FlowDiagram(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = 483, 83

    def draw(self):
        c = self.canv
        labels = [('1', 'Padrón'), ('2', 'Ortofoto'), ('3', 'Modelo'), ('4', 'Medición'), ('5', 'Revisión')]
        x, y, w, h, gap = 0, 20, 83, 46, 17
        for i, (number, label) in enumerate(labels):
            px = x + i * (w + gap)
            c.setFillColor(PALE if i != 2 else NAVY)
            c.roundRect(px, y, w, h, 6, stroke=0, fill=1)
            c.setFillColor(TEAL if i != 2 else colors.HexColor('#9ee0d1'))
            c.setFont('Body-Bold', 8)
            c.drawCentredString(px + w / 2, y + 28, number)
            c.setFillColor(NAVY if i != 2 else colors.white)
            c.setFont('Body-Bold', 9)
            c.drawCentredString(px + w / 2, y + 12, label)
            if i < 4:
                c.setStrokeColor(TEAL)
                c.setLineWidth(1.3)
                c.line(px + w + 3, y + 23, px + w + gap - 3, y + 23)
                c.line(px + w + gap - 7, y + 26, px + w + gap - 3, y + 23)
                c.line(px + w + gap - 7, y + 20, px + w + gap - 3, y + 23)


def chrome(c, doc):
    c.saveState()
    page = doc.page
    c.setFillColor(NAVY)
    c.rect(0, HEIGHT - 7, WIDTH, 7, stroke=0, fill=1)
    c.setFillColor(TEAL)
    c.rect(0, HEIGHT - 7, 90, 7, stroke=0, fill=1)
    c.setStrokeColor(colors.HexColor('#dce5e9'))
    c.line(56, 39, WIDTH - 56, 39)
    c.setFont('Body', 8)
    c.setFillColor(MUTED)
    c.drawString(56, 25, 'GEOPADRONES LAVALLEJA  /  GUÍA DE LECTURA')
    c.drawRightString(WIDTH - 56, 25, f'{page:02d}  /  12')
    c.restoreState()


def document():
    doc = BaseDocTemplate(str(OUT), pagesize=A4, leftMargin=56, rightMargin=56, topMargin=46, bottomMargin=56,
                          title='GeoPadrones Lavalleja - Guía clara del proyecto', author='GeoPadrones Lavalleja',
                          subject='Cómo interpretar el catastro, la ortofoto y los modelos de detección')
    frame = Frame(56, 55, WIDTH - 112, HEIGHT - 103, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates(PageTemplate(id='main', frames=[frame], onPage=chrome))
    s = []

    # 1. Portada
    s += [Spacer(1, 33), P('GUÍA CLARA  /  03 NOVIEMBRE 2026', 'eyebrow'),
          P('GeoPadrones<br/>Lavalleja', 'title'),
          P('Cómo leer el territorio con catastro, fotografías aéreas e inteligencia artificial.', 'subtitle'),
          FlowDiagram(), Spacer(1, 8)]
    s += callout('Qué hace', 'Relaciona la información de Catastro con una fotografía aérea y señala posibles construcciones para que una persona revise los casos.')
    s += callout('Qué no debe prometerse', 'La precisión del modelo en Lavalleja todavía no se ha medido con una muestra independiente. Una señal o discrepancia no demuestra una infracción.', True)
    s += [Spacer(1, 8), P('Una explicación sin conocimientos previos, con ejemplos para conversar sobre el proyecto con propiedad. Las referencias se reúnen al final.', 'small'), PageBreak()]

    # 2. Overview
    s += section(2, 'La idea en un minuto', 'El sistema reúne tres piezas: un mapa de predios, una fotografía aérea y un detector de construcciones.')
    s += [FlowDiagram(), H('El recorrido, explicado paso a paso'),
          bullet('<b>Elegir:</b> una persona busca un padrón, dibuja una zona o filtra un conjunto de casos.'),
          bullet('<b>Mirar:</b> el programa solicita el fragmento de ortofoto correspondiente a cada parcela.'),
          bullet('<b>Detectar:</b> la red neuronal marca los píxeles que se parecen a una construcción.'),
          bullet('<b>Medir:</b> se conservan las marcas dentro del predio y se calcula su área en metros cuadrados.'),
          bullet('<b>Comparar y revisar:</b> se contrasta la detección con Catastro o una declaración; un operador examina la evidencia.'),
          H('La persona sigue teniendo la última palabra'),
          P('GeoPadrones organiza imágenes, límites y resultados; no inspecciona el interior de un edificio ni determina por sí solo si una obra es legal. La información puede tener fechas distintas y contener errores.')]
    s += callout('Una frase para explicarlo', '«Usamos la IA para priorizar casos que merecen revisión; el resultado es un indicio, no un dictamen».')
    s += [PageBreak()]

    # 3. Cadastre
    s += section(3, 'Qué es un padrón y qué muestra el mapa')
    s += [P('Un <b>padrón</b> identifica un inmueble en Catastro. El mapa muestra el contorno de la parcela, como una pieza de un rompecabezas. Una misma identidad puede estar formada por varias piezas geométricas; se reúnen para que no se cuenten dos veces.'),
          H('No alcanza con decir solo el número'),
          P('Un número puede repetirse en distintas localidades. Por eso se usa una identidad que combina departamento, localidad y padrón. Para los rurales se usa una clave interna que no inventa una localidad.'),
          H('Capas distintas, preguntas distintas')]
    s += grid(['Capa', 'Qué aporta'], [
        ['Parcelario de IDE / Catastro', 'Dibuja límites e identifica los predios. [1]'],
        ['Calles de OpenStreetMap', 'Da contexto: calles, nombres y lugares. No determina la propiedad. [4]'],
        ['Categoría territorial de IDE', 'Aporta una referencia de suelo urbano, suburbano o rural calculada por cruce espacial. [1]'],
        ['Datos abiertos de Catastro', 'Aportan lo registrado sobre padrones y superficie edificada, cuando existe ese dato. [2]'],
    ], [157, 326])
    s += callout('Un matiz importante', 'La categoría de suelo y el tipo de padrón catastral son datos diferentes. Una parcela puede tocar varias categorías. El cruce es informativo y no certifica por sí mismo la situación jurídica.')
    s += [PageBreak()]

    # 4. Ortho
    s += section(4, 'La ortofoto: una fotografía que se puede ubicar en el mapa')
    s += [P('Una foto aérea común puede deformar las distancias por la inclinación de la cámara y el relieve. Una <b>ortofoto</b> es una imagen corregida para representar el terreno de manera compatible con un mapa. No significa que sea perfecta ni que todos los techos coincidan exactamente con su límite real. [3]'),
          H('La imagen que utiliza este proyecto'),
          P('La fuente habilitada para el modelo es el vuelo de <b>Minas de diciembre de 2025</b>, publicado por IDE Uruguay. La imagen muestra ese momento: una construcción posterior puede no aparecer y una que fue demolida puede seguir visible. [5]'),
          H('5 cm de origen; 20 cm para el análisis'),
          P('La resolución nativa indicada es de aproximadamente <b>5 cm por píxel</b>. Para procesar, GeoPadrones prepara recortes a <b>20 cm por píxel</b>: cada cuadrito de la imagen de trabajo representa aproximadamente 20 cm de terreno por lado. No son 20 cm de precisión garantizada.'),
          P('El visor solicita imágenes para mostrarlas en pantalla; el detector pide un recorte georreferenciado que también contiene información de ubicación y escala. No se descarga todo el mosaico para cada análisis.')]
    s += callout('Límite real de cobertura', 'La ortofoto habilitada cubre el área del vuelo de Minas, no todo Lavalleja. Donde no hay imagen suficiente, el sistema no debe concluir que el padrón está vacío.', True)
    s += [PageBreak()]

    # 5. Models
    s += section(5, 'Qué hace la red neuronal', 'Una red neuronal es un programa que aprendió patrones a partir de muchos ejemplos. Aquí se usa para mirar imágenes, no para redactar textos.')
    s += [P('Durante su entrenamiento recibió imágenes acompañadas de marcas que indicaban dónde había edificios y ajustó sus parámetros internos, llamados <b>pesos</b>. Unas capas reconocen patrones sencillos; otras los combinan y recuperan detalles de ubicación. Al procesar una imagen nueva, calcula para cada píxel cuánto se parece a la clase «edificio» y genera una <b>máscara</b>: un mapa de zonas candidatas.'),
          H('Dos modelos disponibles en GeoPadrones')]
    s += grid(['Modelo', 'Cómo entenderlo'], [
        ['FLAIR - U-Net / ResNet-34', 'Modelo multiclase del IGN de Francia. Sus pesos usados por el proyecto distinguen 19 salidas; una corresponde a edificios. [6]'],
        ['UNet++ / EfficientNet-B4', 'Modelo especializado en edificio / fondo, publicado con entrenamiento sobre WHU. Su codificador reconoce patrones y su decodificador reconstruye la máscara. [7, 8]'],
    ], [185, 298])
    s += [P('Ambos miran colores y formas desde arriba. No conocen al propietario, no leen los permisos de obra y no dibujan los límites catastrales. El sistema procesa la imagen en ventanas que se superponen para reducir cortes en los bordes.'),
          P('Por defecto se ofrece FLAIR y CPU si no hay una preferencia guardada; se puede elegir UNet++ y, si el servidor dispone de ella, una GPU NVIDIA.')]
    s += callout('Analogía útil', 'La red es un resaltador que señala posibles techos. El mapa catastral aporta la parcela; otra parte del programa hace la medición.')
    s += [PageBreak()]

    # 6. Metres
    s += section(6, 'De los píxeles a los metros cuadrados')
    s += [P('El sistema transforma el mapa a coordenadas que se miden en metros, recorta la detección por el contorno de cada padrón y calcula el área de la parte que queda dentro. Si una marca cruza el límite, solo se cuenta la parte interior.'),
          H('Huella no es lo mismo que superficie edificada'),
          P('Imaginá una casa cuyo techo ocupa <b>80 m²</b> vistos desde arriba. Esa es su huella aproximada. Si tiene dos plantas de 80 m², la superficie total de pisos podría rondar <b>160 m²</b>. Una ortofoto por sí sola no cuenta los pisos interiores.'),
          H('Qué decide el resultado'),
          P('Las reglas iniciales son configurables: umbral de probabilidad de píxel 0,5, descarte de objetos menores a 2 m², huella mínima de 8 m² y ocupación mínima del 1 % para declarar construcción visible; se exige además al menos 95 % de cobertura de imagen válida.'),
          P('Una señal que queda por debajo de la huella u ocupación mínimas puede quedar <b>indeterminada</b>. Si no queda ningún objeto detectable, se informa «sin construcción visible». Un objeto pequeño descartado también puede quedar fuera del resultado. La imagen demasiado antigua también puede producir un resultado indeterminado.')]
    s += callout('No confundir umbral con acierto', 'Un umbral de 0,5 o una cobertura del 95 % son reglas de funcionamiento: no significan que el modelo acierte el 50 % o el 95 % de las veces.', True)
    s += [PageBreak()]

    # 7. Metrics
    s += section(7, 'Qué sabemos de la precisión', 'Las fichas de los modelos muestran resultados de sus propias pruebas. Se hicieron con imágenes y referencias diferentes de las de Lavalleja.')
    s += grid(['Modelo y prueba', 'Resultados publicados'], [
        ['FLAIR / imágenes de prueba francesas [6]', 'Edificio: precisión 88,892 %, sensibilidad 87,662 % e IoU 79,007 %. Son medidas por píxel, no por padrón.'],
        ['UNet++ / prueba WHU, Nueva Zelanda [7, 8]', 'IoU 90,54 % y Dice 95,03 % en la prueba informada. No son un porcentaje de padrones acertados.'],
    ], [218, 265])
    s += [P('<b>Precisión</b> pregunta: de los píxeles marcados como edificio, ¿qué proporción coincidió con la referencia? <b>Sensibilidad</b> pregunta: de los píxeles de edificio de la referencia, ¿qué proporción encontró? <b>IoU</b> compara la zona marcada con la zona de referencia, tomando en cuenta tanto lo que sobra como lo que falta.'),
          P('No corresponde comparar directamente esas cifras para afirmar que uno gana en Lavalleja: se evaluaron con imágenes, lugares y conjuntos distintos. Tampoco hay todavía un error local comprobado para los metros cuadrados.'),
          H('Qué hace falta para medirlo aquí'),
          P('Revisar una muestra local independiente y diversa, con y sin construcción, y comparar cada predicción y su superficie con una referencia humana. El proyecto propone al menos 200 casos; esa validación sigue pendiente.')]
    s += callout('La cifra honesta para Lavalleja', 'La precisión local, la tasa de errores y el error de área son todavía desconocidos. Que el sistema funcione no demuestra cuánto acierta.', True)
    s += [PageBreak()]

    # 8. Confidence
    s += section(8, 'Confianza, falsos positivos y revisión')
    s += [P('Algunos resultados incluyen una <b>confianza</b>. En este proyecto se calcula como el promedio de las probabilidades que el modelo asignó a los píxeles detectados y válidos. Un valor alto indica una señal más fuerte para la red; <b>no es una probabilidad validada de que todo el padrón sea correcto</b>.'),
          H('Los dos errores que conviene conocer'),
          bullet('<b>Falso positivo:</b> el modelo marca una construcción donde la referencia no la considera tal; por ejemplo, puede confundir un pavimento claro con un techo.'),
          bullet('<b>Falso negativo:</b> hay una construcción, pero el modelo no la detecta; un techo pequeño, oculto por árboles o cubierto por sombra puede pasar inadvertido.'),
          H('Qué revisar en la práctica'),
          P('Comprobá primero la fecha y la cobertura de la foto, después el contorno del padrón y la zona marcada. Una sombra, vegetación, un borde catastral impreciso o una obra posterior a 2025 pueden explicar una diferencia.'),
          P('La pantalla de revisión conserva la evidencia automática y permite registrar una intervención humana. Los casos sin datos o con calidad insuficiente se mantienen separados de los negativos.')]
    s += callout('Cómo decirlo con precisión', '«La confianza es una señal del modelo; para hablar de confiabilidad necesito una validación independiente con casos locales».')
    s += [PageBreak()]

    # 9. CPU GPU
    s += section(9, 'CPU, GPU y CUDA: el motor de cálculo')
    s += [P('La <b>CPU</b> es el procesador general de la computadora. Una <b>GPU</b> puede ejecutar muchas operaciones numéricas en paralelo. <b>CUDA</b> es la plataforma de NVIDIA que permite a programas compatibles usar sus GPU para este tipo de cálculos. [9]'),
          H('Qué se hizo para usar la GPU'),
          P('Se preparó un worker -el proceso que ejecuta los trabajos- con PyTorch compatible con CUDA, soporte para el controlador NVIDIA y acceso a la GPU desde Docker. El usuario elige CPU o GPU; la GPU debe existir en el servidor que procesa el trabajo, aunque la web se abra en otra computadora.'),
          H('La medición de esta instalación')]
    s += grid(['Prueba de UNet++', 'Mediana observada'], [
        ['CPU, dos hilos', '13,323 segundos'],
        ['NVIDIA RTX 3050, 8 GB', '0,972 segundos'],
    ], [270, 213])
    s += [P('Fue el mismo recorte de Minas, 1.300 × 1.300 píxeles, con calentamiento y tres pasadas. La GPU fue unas <b>13,7 veces más rápida en esa inferencia</b>. No incluye espera en cola, descarga de imagen ni preparación del resultado; otro equipo dará otros tiempos.'),
          P('Las salidas CPU y GPU coincidieron en el 99,9919 % de los píxeles de esa prueba. Eso mide su parecido entre sí, no su acierto frente a la realidad.')]
    s += [PageBreak()]

    # 10. Comparison
    s += section(10, 'Cómo funciona «Comparar»')
    s += [P('Primero elegís categoría de suelo, localidad y estado informado por Catastro: con construcción, sin construcción declarada o no definido. Podés acotar el rango de números y elegir modelo y procesador. La vista anticipa cuántos casos se pueden analizar.'),
          H('Qué significa el color rojo'),
          P('La pantalla compara el dato catastral con el resultado del <b>lote recién ejecutado</b>. Marca una posible discrepancia cuando uno indica construcción y el otro ausencia visible. Por ejemplo: Catastro declara cero, pero la imagen y el modelo sugieren un techo.'),
          P('Si Catastro no informa el dato, se puede ejecutar el detector pero no hay una expectativa contra la cual afirmar coincidencia o discrepancia. Un error, una señal dudosa o la falta de imagen tampoco se convierten en una ausencia.'),
          H('Por qué no siempre se pueden analizar todos'),
          P('El archivo rural de datos abiertos no informa superficie edificada: para esos registros el valor es desconocido. Además, algunas geometrías faltan, algunos predios exceden el tamaño de recorte y muchos quedan fuera de la foto de Minas. Se informa el motivo antes de iniciar.'),
          P('Cada comparación admite hasta 5.000 casos aptos con la configuración actual; una selección mayor puede dividirse usando rangos de padrón. La categoría de suelo es una referencia geográfica que puede tener cobertura parcial o categorías mixtas.')]
    s += callout('Para presentar un hallazgo', '«Encontramos una diferencia entre lo registrado y lo visible en la imagen de 2025; corresponde comprobarla con antecedentes y revisión humana».')
    s += [PageBreak()]

    # 11. Operations
    s += section(11, 'Dónde se guardan los datos y qué queda pendiente')
    s += [P('El navegador muestra el mapa y los formularios. El servidor organiza las solicitudes; una cola entrega los trabajos a los workers. <b>PostGIS</b> guarda y consulta los datos geográficos; un almacén de objetos conserva imágenes y evidencias. Los análisis y revisiones se registran para poder consultarlos.'),
          H('Acceso y cuidado de la información'),
          P('El sistema dispone de inicio de sesión, captcha y doble factor. En esta instalación se habilitó una entrada local de prueba sin autenticación; no debe confundirse con una configuración de producción. Las opciones de limpieza permiten eliminar análisis y evidencias según el alcance elegido.'),
          H('Cómo se recupera la instalación'),
          P('El código, las instrucciones de <b>Setup</b>, las fuentes públicas y las versiones de modelos permiten reconstruir las funciones. Los datos, pesos, secretos, usuarios y resultados históricos no viajan automáticamente con el código. Para recuperar exactamente esta instalación se necesitan también las copias originales y los respaldos correspondientes.'),
          H('Lo que aún hay que validar'),
          bullet('Medir el desempeño local y el error de superficie con referencias independientes.'),
          bullet('Ampliar o confirmar la cobertura de imágenes antes de analizar otras zonas.'),
          bullet('Revisar el instrumento normativo, las fechas y la idoneidad de cada fuente antes de usar los resultados para decisiones.'),
          bullet('En producción: asegurar autenticación, HTTPS, copias de seguridad, responsables y permisos adecuados.')]
    s += [PageBreak()]

    # 12. Sources and professional vocabulary
    s += section(12, 'Fuentes y palabras para explicarlo')
    s += [P('<b>Padrón:</b> identidad catastral. <b>Ortofoto:</b> foto aérea corregida para ubicarse en el mapa. <b>Segmentación:</b> marcar en la imagen los píxeles que corresponden a una clase. <b>Huella:</b> superficie de una construcción vista desde arriba. <b>IoU:</b> medida de solapamiento con una referencia.', 'small'),
          P('Las fuentes enlazadas permiten consultar el origen; las métricas y fechas deben leerse en el contexto de cada fuente.', 'small')]
    links = [
        ('1', 'IDE Uruguay: servicios geográficos y capas oficiales', 'https://mapas.ide.uy/geoserver-vectorial/ideuy/wfs'),
        ('2', 'DNC: padrones urbanos y rurales, datos abiertos', 'https://catalogodatos.gub.uy/dataset/direccion-nacional-de-catastro-padrones-urbanos-y-rurales'),
        ('3', 'USGS: qué es una ortoimagen', 'https://www.usgs.gov/faqs/what-a-digital-orthophoto-quadrangle-doq-or-orthoimage'),
        ('4', 'OpenStreetMap: derechos y atribución', 'https://www.openstreetmap.org/copyright'),
        ('5', 'IDE: vuelo fotogramétrico Minas, diciembre de 2025', 'https://catalogodatos.gub.uy/dataset/ide-vuelo-fotogrametrico-minas-diciembre-2025'),
        ('6', 'IGN: ficha y métricas de FLAIR, revisión usada', 'https://huggingface.co/IGNF/FLAIR-INC_rgb_12cl_resnet34-unet/blob/533aa8f000dd36f2d07279ae73e0263d5f23a976/README.md'),
        ('7', 'Ficha de UNet++ / EfficientNet-B4, revisión usada', 'https://huggingface.co/giswqs/whu-building-unetplusplus-efficientnet-b4/blob/09df9efd323bbd3d56b98b4857129eb9b5baa2d3/README.md'),
        ('8', 'Universidad de Wuhan: conjunto de edificios WHU', 'https://gpcv.whu.edu.cn/data/building_dataset.html'),
        ('9', 'NVIDIA: guía de programación CUDA', 'https://docs.nvidia.com/cuda/cuda-programming-guide/index.html'),
    ]
    for number, label, url in links:
        s.append(P(f'[{number}] <link href="{escape(url)}" color="#087f78">{escape(label)}</link>', 'small'))
    s += [Spacer(1, 5)]
    s += callout('La idea que conviene recordar', 'Mapa + fotografía + IA producen evidencia para examinar. La fecha, la cobertura, los errores posibles y la revisión humana son parte del resultado.')
    doc.build(s)
    print(OUT)


if __name__ == '__main__':
    document()
