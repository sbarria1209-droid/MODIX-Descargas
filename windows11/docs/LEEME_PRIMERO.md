# MODIX BIGMETER V4 · 11 · Multicámara

Instala Principal 11 en la PC conectada a la impresora y Cliente 11 en la PC de supervisión. Cada descarga es un instalador EXE completo, con su entorno incluido. La principal incluye OBS portátil y lo administra automáticamente. Cierra la versión anterior antes de instalar. Conserva los datos locales de MODIX.

## Un solo video con dos a ocho cámaras

Conecta al menos dos cámaras USB distintas a la PC principal, una a cada lado, firmes y apuntando hacia abajo a la zona de impresión. Pueden añadirse hasta ocho. La app abre cada dispositivo por separado, combina las vistas y envía un único video al cliente; Ampliar funciona también con la fusión.

En Cámara → Fuente de video, elige **Fusión de 2–8 cámaras** y pulsa **Cámaras…**. Selecciona los dispositivos, pulsa **Previsualizar selección** y calibra cada cámara. Sin calibración verás un mosaico con aviso; activar dos cámaras por sí solo no elimina el brazo.

## Calibración de las cámaras reales

Hazla con la máquina en reposo, sin impresión. El asistente no envía movimientos ni comandos a Duet. Mantén fijas las cámaras, el zoom, el enfoque y el eje Z durante las capturas. Usa lentes normales; una lente ojo de pez necesita corregirse previamente y no está incluida esa corrección.

1. Define cuatro marcas de coordenadas XY conocidas formando un rectángulo. Introduce X/Y mínimas y la separación entre marcas. Cuanto más espacio de la cama cubran las referencias, mejor será el ajuste lejos del centro. Las cuatro deben verse en cada cámara.
2. Define dos alturas físicas de esas mismas posiciones XY, por ejemplo una referencia inferior en Z=0 y otra exactamente 100 mm más alta, sobre soportes rígidos. Mantén el mismo rectángulo y no cambies el eje Z para obtener el segundo plano. Las alturas se miden respecto de la cama de referencia en el momento de calibrar.
3. Indica la Z máquina de Duet durante la calibración. Elige si las cámaras están fijas al chasis y la cama baja en Z, o si la cama es fija/cámaras se desplazan junto a la cama. Esto determina la proyección de la capa durante la impresión.
4. En cada cámara, captura el plano inferior y marca las esquinas en este orden físico: 1 = X−Y−, 2 = X+Y−, 3 = X+Y+, 4 = X−Y+. Repite en el plano superior, conservando el mismo orden físico aunque desde el otro lado se vea invertido.
5. Pulsa **Calcular y guardar calibración de esta cámara**. Repite en la cámara opuesta y en las adicionales. El asistente rechaza referencias degeneradas y ajustes mayores de 6 píxeles. Un error de ajuste pequeño no garantiza que las medidas físicas introducidas sean correctas: comprueba la alineación de una figura conocida en ambas vistas.
6. Ajusta las medidas del travesaño, su orientación y el radio/altura del conjunto completo de cabezales, incluyendo el extrusor inactivo y el cableado que tape la pieza. El margen amplía la exclusión; la velocidad máxima añade margen cuando las posiciones de Duet están espaciadas en el tiempo.
7. Guarda, conecta Duet y pulsa **Activar**. Puedes usar **Prueba de alineación con posición manual** en reposo para comprobar referencias; el video llevará la marca PRUEBA MANUAL. Desactívala para seguir la posición real de Duet durante una impresión.

Las zonas fijas excluidas sirven para soportes o bordes que aparecen siempre en una cámara. No marques toda la pieza ni el recorrido completo del brazo. Colorear procedencia ayuda a comprobar qué cámara aporta cada región.

## Qué muestra la fusión

Es una vista rectificada del plano de la capa actual. Proyecta la geometría del travesaño/cabezal según Duet y busca un píxel visible de otra cámara. No reconstruye un modelo volumétrico ni conserva la perspectiva de una cámara arbitraria; las paredes y objetos a otras alturas pueden verse deformados.

**Los cuadros grises significan que ninguna cámara ve esa región.** La app no inventa lo que hay debajo, no rellena con IA ni reutiliza una imagen antigua. Más cámaras con ángulos útiles pueden reducir la zona oculta, pero no garantizan una cobertura del 100 %. Una oclusión fuera de las medidas configuradas puede quedar visible: revisa la máscara y sus márgenes.

Solo combina capturas recientes con separación temporal acotada. Si falta otra cámara sincronizada, cambia la resolución, falta calibración o se pierde la posición reciente de Duet, muestra las vistas disponibles con un aviso. Los dispositivos conocidos se identifican por USB; cambiar de cámara o de formato exige recalibrar. Si Windows/driver no entrega una identidad estable, vuelve a comprobar la selección después de reconectar.

El análisis visual de defectos utiliza una toma original actual, no el mosaico, el relleno ni la fusión. Sus alertas no constituyen una garantía de detección de todos los defectos.

## Fluidez y transmisión

Captura USB MJPEG, una tarea por cámara, memoria acotada y selección de imágenes recientes. Empieza con USB 1280×720, detalle de fusión 640 px y objetivo 20 FPS. Si el equipo o los puertos USB se saturan, reduce a 640×480 y fusión 480 px; al cambiar el formato USB debes recalibrar. Para muchas cámaras, distribúyelas entre controladores USB y evita un concentrador sin alimentación.

OBS comprime una sola salida H.264; intenta la GPU y usa CPU si el codificador no funciona o no entrega paquetes. El cliente recibe WebRTC directo cuando es posible, con respaldo H.264 por HTTPS para redes restrictivas. Los datos y el recorrido de la boquilla mantienen sus canales independientes. Los FPS de salida de OBS pueden repetir una imagen: el indicador **Fusión FPS** muestra la frecuencia real de composición. Más cámaras y más detalle exigen más procesamiento. No se promete video sin retraso.

También siguen disponibles OBS con una sola cámara y USB directa. OBS incluido usa un perfil propio, sin alterar perfiles de otro OBS. No transmite audio.

## Compartir y datos conservados

Segunda PC → Internet → Compartir por Internet genera el enlace del visor. Pégalo en Cliente 11. Para la misma red puedes usar Compartir en la red. Cerrar el enlace revoca el acceso y borra la imagen del cliente, incluida la ampliada. El puente existente se conserva, con su plan gratuito y límite preventivo de transferencia; no se contrataron servicios adicionales. El video directo evita retransmitirlo por el puente; el respaldo HTTPS consume su límite.

Se conservan recorrido de boquilla y capas, descarga automática del archivo en impresión, historial, tiempos, luces que informa Duet, alertas de sensores y análisis visual. El cliente es de solo lectura. M591 dinámico conserva L medido y E informado. No se modifican las reglas de reanudación comprobada: una oclusión de cámara no da permiso para ignorar un sensor, un atasco o un calentador.

La configuración de cámaras se guarda localmente en los datos de MODIX como multicam11.json. No contiene imágenes capturadas. Los instaladores públicos no contienen calibraciones personales, contraseñas, clave de estación, trabajos ni historial. Para compartir desde una principal instalada en otra PC, transfiere su configuración privada por un medio privado. Nunca publiques bridge.json ni estacion_privada.*.

OBS y bibliotecas conservan sus licencias. Fuentes: https://github.com/obsproject/obs-studio, https://github.com/opencv/opencv, https://github.com/aiortc/aiortc, https://github.com/PyAV-Org/PyAV y https://github.com/imageio/imageio-ffmpeg.

Proyecto personalizado independiente de Modix, Duet y Canal de Panamá.
