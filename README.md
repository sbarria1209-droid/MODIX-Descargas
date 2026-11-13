# MODIX BIGMETER V4 · Versión 10 con OBS

Aplicaciones de escritorio para supervisar y controlar una Modix con Duet desde la PC principal, y ver su cámara, capas y recorrido desde un cliente de solo lectura.

## Descargar para Windows

No necesitas iniciar sesión en GitHub ni instalar Python. Cierra las versiones anteriores e instala ambas aplicaciones:

- **[Descargar Principal 10](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v10.0.0/MODIX_Principal_10_Instalador.exe)** — en la PC conectada a la cámara USB y a Duet. Incluye OBS portátil.
- **[Descargar Cliente 10](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v10.0.0/MODIX_Cliente_10_Instalador.exe)** — en la otra PC.
- [Instrucciones](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v10.0.0/LEEME_PRIMERO.md) · [Pruebas y límites](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v10.0.0/VERIFICACIONES.md) · [SHA256](https://github.com/sbarria1209-droid/MODIX-Descargas/releases/download/v10.0.0/MODIX_10_SHA256.txt).

## Empezar

1. Principal: selecciona la cámara USB física y **Fuente de vídeo: OBS**; pulsa **Activar**. La aplicación prepara y administra una instancia de OBS con perfil propio.
2. Conecta Duet con su IP y contraseña. Se conservan el historial, la carga automática de archivo activo, las capas, el recorrido, tiempos, luces y alertas.
3. Abre **Segunda PC → Compartir por Internet** y pega en Cliente 10 el enlace generado. También puedes compartir en la red local.

OBS codifica H.264 mediante GPU cuando es compatible y dispone de alternativa por CPU. El cliente intenta WebRTC directo; si la red lo impide, usa H.264 por HTTPS. La geometría 3D se transmite por separado. Ampliar y pantalla completa usan la misma imagen recibida. La captura USB directa sigue disponible como alternativa.

## Verificación

70 pruebas de componentes; pruebas nativas Qt/OpenGL; vídeo, modelo, autenticación y revocación. OBS real con GPU Intel y un reloj de ensayo produjo aproximadamente 30 FPS en red local: mediana 290 ms por WebRTC y 233 ms por el respaldo H.264 local. También se probó el codificador por CPU. Son pruebas con fuente sintética y Duet simulado, no medidas de una cámara o impresora física ni una garantía de rendimiento WAN. El enlace real activo no se sustituyó para pruebas.

## Datos y límites

Los instaladores públicos no incluyen credenciales de estación, trabajos, historial ni perfiles o contraseñas privados de OBS. La principal conserva su configuración local existente; una principal en una PC nueva necesita transferir la configuración privada de Internet de forma privada. El cliente solo necesita su enlace de visor.

Se conserva el plan gratuito del puente y el límite preventivo de 1 GB/mes por instancia. WebRTC directo evita retransmitir el vídeo por Render; el respaldo HTTPS consume ese límite. No se ofrecen datos ilimitados ni se contratan servicios de pago.

La recuperación de filamento requiere condiciones comprobadas. No omite calentadores, paradas, pausas del operador ni defectos físicos. Los sensores P7 que no informan presencia requieren revisión manual. Se conserva M591 dinámico con L medido y E informado por Duet.

El puente HTTPS se encuentra en `modix-puente/`. OBS y sus componentes conservan sus licencias y enlaces a fuentes oficiales incluidos en la distribución. Proyecto personalizado independiente de Modix, Duet y Canal de Panamá.
