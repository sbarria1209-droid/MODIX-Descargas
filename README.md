# MODIX BIGMETER V4 · 11 · Multicámara

Aplicaciones de Windows para controlar la Modix con Duet desde la principal y supervisar video, capas y recorrido desde un cliente de solo lectura.

## Descarga directa

No necesitas una cuenta de GitHub ni instalar Python. Cierra la versión anterior e instala las dos aplicaciones:

- **[Descargar Principal 11](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v11.0.0/MODIX_Principal_11_Instalador.exe)** — PC de la impresora y las cámaras. Incluye OBS portátil.
- **[Descargar Cliente 11](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v11.0.0/MODIX_Cliente_11_Instalador.exe)** — PC de supervisión.
- [Calibración y uso](windows11/docs/LEEME_PRIMERO.md) · [Pruebas y límites](windows11/docs/VERIFICACIONES.md) · [SHA256](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v11.0.0/MODIX_11_SHA256.txt).

## Combinar las cámaras

Conecta de **2 a 8 cámaras USB** a la principal, una a cada lado y las adicionales desde ángulos útiles. En Cámara elige **Fusión de 2–8 cámaras → Cámaras…**. Selecciona los dispositivos y sigue la calibración con cuatro referencias XY en dos alturas físicas conocidas. Guarda, conecta Duet y pulsa Activar. El cliente recibe **un solo video**, también ampliable.

La fusión proyecta el plano de la capa y excluye el volumen configurado de brazo/cabezal según Duet para tomar píxeles visibles de otras cámaras. **Requiere calibrar las cámaras reales y ajustar las medidas del brazo.** Las regiones que ninguna cámara ve quedan grises. No se rellena con IA ni con imágenes antiguas, no es una reconstrucción volumétrica y no garantiza retirar toda oclusión. Si faltan imágenes recientes, calibración o posición de Duet, se muestran las vistas disponibles con un aviso.

OBS comprime H.264 una vez; el cliente intenta WebRTC directo y utiliza el respaldo HTTPS cuando hace falta. El perfil inicial es ligero y permite subir la calidad. Los FPS de OBS pueden incluir repeticiones; el indicador Fusión FPS muestra el procesamiento real. Más cámaras y más resolución requieren más recursos. También siguen disponibles OBS con una sola cámara y USB directa.

## Funciones conservadas

Recorrido de boquilla, capas, descarga del G-code activo, historial, tiempos, luces que informa Duet, alertas y análisis visual de una toma original. Compartir por Internet genera el enlace del visor; cerrarlo revoca el acceso y borra el video del cliente. Las reglas de recuperación comprobada se mantienen: no se ignoran calentadores, paradas ni defectos físicos. M591 dinámico conserva L medido y E informado.

## Verificación y datos

70 pruebas de componentes, 12 comprobaciones nativas y nueve pruebas de fusión. Se probó la señal de dos cámaras simuladas con OBS real y cliente Qt por WebRTC y respaldo H.264, ampliación y revocación. También se simuló geometría de cuatro y ocho cámaras. **No se ensayaron las cámaras físicas de la instalación ni video WAN con el enlace real del usuario.** Consulta el informe para conocer las mediciones y sus límites.

Los instaladores no incluyen claves de estación, calibraciones personales, imágenes, trabajos ni historial. Una principal en otra PC necesita su configuración privada de Internet por un medio privado. Nunca publiques bridge.json ni estacion_privada.*.

Se conserva el puente y su plan gratuito, con límite preventivo de transferencia. WebRTC directo evita retransmitir el video por Render; el respaldo HTTPS consume ese límite. El puente está en `modix-puente/` y el código nuevo de la aplicación y su compilación en `windows11/`. Las licencias de OBS y bibliotecas se conservan en los instaladores. Proyecto independiente de Modix, Duet y Canal de Panamá.

[Versión 10 anterior](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/tag/v10.0.0).

