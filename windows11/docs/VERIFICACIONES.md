# Verificación de MODIX 11 Multicámara

Se aprobaron 70 pruebas de componentes existentes, 12 comprobaciones de interfaz nativa Qt/OpenGL y nueve pruebas nuevas de geometría, sincronización y estado de cámaras. Se conservan las funciones de impresión; no se enviaron comandos a una impresora física.

El banco sintético genera cámaras pinhole desde lados opuestos y, para cuatro/ocho vistas, alrededor de la cama. Se renderizan la capa y oclusores 3D de color conocido con una proyección independiente. Tras calibrar, la fusión no conservó píxeles del brazo dentro de las zonas declaradas visibles. La cobertura fue 95,66 % con dos cámaras y 99,59 % con cuatro y ocho en esa escena concreta. Son resultados de simulación; no son porcentajes garantizados para la Modix real. Las regiones completamente tapadas quedan en gris, sin reutilizar imágenes anteriores.

Se probaron cambios de altura, movimiento del cabezal, cama móvil, posiciones caducadas, capturas antiguas, separación temporal máxima, rechazo de calibración degenerada, cámaras duplicadas y cambio de resolución. La IA recibe una toma original actual. Se ejercitó el asistente de calibración de dos planos en una ventana real, incluida su versión de 800×600.

La señal de dos cámaras simuladas atravesó el servidor local de fusión, OBS oficial real, H.264 y un cliente Qt nativo por WebRTC y por el respaldo H.264 local. Se comprobó imagen no vacía, ausencia del oclusor sintético, ampliación, revocación del visor y cierre del feed local. Se ejecutaron los codificadores Intel Quick Sync y CPU; se probó además la recuperación con CPU después de un inicio de GPU sin paquetes.

El perfil ligero entregó aproximadamente 20 paquetes de video por segundo en ambos transportes. Esa cifra incluye imágenes repetidas de OBS: no equivale a 20 composiciones nuevas. La composición, captura simulada, principal, OBS y cliente compartían una sola PC y su rendimiento cambió según la carga. El indicador muestra los FPS reales de fusión. La medición local de salida de fusión a cliente por respaldo H.264 tuvo mediana 296 ms y p95 340 ms con 103 muestras; no incluye exposición/captura USB ni red WAN. No se publica una cifra WebRTC equivalente porque esa ejecución no produjo suficientes muestras del reloj.

Las cámaras físicas están en la instalación del usuario: su campo de visión, calibración, dimensiones del brazo, distorsión óptica, sincronización de exposición y velocidad USB deben comprobarse allí. Esta versión requiere calibrarlas; no promete eliminar toda oclusión ni reconstruir superficies a cualquier altura. No se reemplazó el enlace real del usuario para ensayar video WAN.

Los instaladores públicos se verifican por separado: contenido sin credenciales de estación, código correspondiente a esta versión y arranque autónomo mediante su EXE. Los informes de pruebas se guardan en el entorno de trabajo; no contienen imágenes del usuario en las descargas públicas.
