# MODIX 9.0.1 · Descarga directa para Windows

**Descarga sin cuenta ni inicio de sesión. Instala ambos EXE nuevos:**

- **[DESCARGAR PRINCIPAL](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v9.0.1/MODIX_Principal_9_Instalador.exe)** · PC conectada a Duet y la cámara USB.
- **[DESCARGAR CLIENTE](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v9.0.1/MODIX_Cliente_9_Instalador.exe)** · Otra computadora para supervisar.

[Versión y todos sus archivos](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/tag/v9.0.1) · [Guía completa](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v9.0.1/LEEME_PRIMERO.md). Cierra versiones anteriores antes de instalar. Python y las dependencias están incluidos. Los ZIP automáticos de código fuente no son los instaladores.

## Nuevo en la versión 9

- Cliente rediseñado según la referencia: Vista, Cámara e Historial; indicadores, progreso circular, temperaturas y trabajo. El botón de enlace del encabezado muestra la conexión; Ampliar o doble clic abre la cámara grande.
- Recorrido del archivo por bytes, boquilla roja de Duet, posiciones recientes en cian y marcador amarillo del archivo. Los modelos muy grandes se muestrean y la telemetría son posiciones muestreadas, sin certificar físicamente cada trazo extruido.
- Vídeo y datos por WebSocket persistente, con respaldo HTTP y descarte de imágenes atrasadas. Modelo transmitido aparte. Prueba real PC → Render → cliente, con imágenes sintéticas: 10,73 FPS y 187 ms de retraso mediano. La cámara, CPU y red reales pueden dar resultados distintos.
- Descarga y análisis automáticos del G-code activo al conectar, con reintentos y caché por trabajo.
- Historial persistente de impresiones en la principal con filtros y exportación CSV. El cliente recibe los 40 registros más recientes. Un corte de red no se marca como impresión finalizada.
- Estado de luces y brillo según la telemetría disponible de Duet; las tiras sin información de estado se identifican como no confirmadas.
- Recuperación de comunicaciones y descargas. Reanudación por filamento solo tras comprobar una recuperación; no se fuerzan pausas desconocidas ni se ignoran protecciones. Los sensores P7 sin presencia de filamento confirmable requieren revisión manual. No se cancela por contar errores.
- Se conservan M591 dinámico con L medido y E informado por Duet, controles de máquina y macros, placa/boquillas, preparación, laminado externo, heightmap e IA visual local.

## Uso

Conecta Duet y activa la cámara USB en la principal. En Segunda PC pulsa Compartir por Internet y pega el enlace generado en el cliente. Mantén abierta la principal. La cámara local y la remota tienen perfiles separados; Fluida solicita hasta 12 FPS remotos y Ahorro reduce consumo. El puente gratuito mantiene sus límites: no es vídeo ilimitado ni se promete latencia cero.

La IA emite posibles fallos y necesita validación con tu encuadre y piezas. La aplicación no puede retirar un atasco, colocar filamento, recuperar una pieza despegada ni reparar un calentador: esos casos quedan en pausa para revisión.

## Configuración privada

Los EXE públicos no contienen claves de estación, registros ni trabajos de tu PC. Al actualizar una principal ya configurada se conservan sus datos locales de Windows. Una PC principal completamente nueva necesita recibir su configuración de Internet de forma privada; Duet, cámara y LAN funcionan sin ella. El cliente solo necesita el enlace de supervisión. No publiques archivos de credenciales.

Proyecto personalizado independiente, sin afiliación oficial a Modix, Duet o Canal de Panamá. Guía, verificaciones y licencias incluidas en la instalación.
