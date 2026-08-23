# Hoja de ruta de audio y medios

## Gestión de prioridades de audio

- Implementar *ducking*: reducir temporalmente la música local al 20–30 % durante una indicación de navegación y recuperar el volumen suavemente al terminar.
- Pausar la música local durante llamadas telefónicas y reanudarla al finalizar.
- Pausar o atenuar la música local mientras Siri o el asistente de Android Auto están activos.
- Atenuar brevemente la música local durante alertas de CarPlay o Android Auto.
- Procesar explícitamente los eventos `Start` y `Stop` de cada canal de audio.
- Verificar en hardware cómo utiliza cada modelo y firmware de dongle `AudioOutputStart` y `audioType`.
- Mantener registros de diagnóstico del comando, `audioType` y formato recibido para facilitar la calibración.

## Página de ajustes de audio

- Añadir una página de audio dentro de Ajustes.
- Configurar de forma independiente el volumen multimedia local.
- Configurar el volumen de la música de CarPlay y Android Auto.
- Configurar el volumen de las indicaciones de navegación.
- Configurar el volumen de las llamadas.
- Configurar el volumen de Siri y otros asistentes de voz.
- Configurar el volumen de las alertas.
- Configurar el porcentaje de atenuación aplicado a la música durante la navegación.
- Configurar la velocidad de bajada y recuperación del volumen durante el *ducking*.
- Configurar el volumen o ganancia del micrófono durante las llamadas.
- Añadir una prueba de micrófono y un indicador de nivel para evitar saturación.
- Permitir restaurar todos los valores de audio a sus ajustes predeterminados.

## Reproductor local

- Reanudar una canción desde el segundo exacto después de reiniciar V-Link.
- Conservar el historial aleatorio entre arranques para que `Anterior` mantenga la secuencia real.
- Leer etiquetas ID3 y mostrar título, artista, álbum y carátula.
- Añadir normalización de volumen entre canciones.
- Añadir favoritos y listas de reproducción.
- Permitir búsqueda alfabética en bibliotecas grandes.
- Explorar e indexar recursivamente la música por carpeta, artista y álbum.
- Mostrar el estado del escaneo y actualizar la biblioteca cuando cambie el contenido del dispositivo.

## Dispositivos y recuperación

- Detectar cuándo se conecta o retira una unidad USB.
- Mostrar un aviso no intrusivo si desaparece el dispositivo que contiene la pista actual.
- Conservar la biblioteca y la última selección recordadas cuando el USB no esté disponible.
- Restaurar automáticamente la carpeta, pista y posición cuando se vuelva a conectar el mismo dispositivo.
- Identificar unidades por UUID o etiqueta para evitar confundir dispositivos montados en rutas diferentes.

## Pruebas recomendadas

- Música local con una indicación de navegación de CarPlay.
- Música local con una indicación de navegación de Android Auto.
- Llamada entrante, llamada saliente y recuperación de la música al colgar.
- Activación y cierre de Siri o del asistente de Google.
- Alertas mientras se reproduce audio local.
- Conexión y retirada del USB durante la reproducción.
- Reinicio con dongle conectado y sin dongle conectado.
- Comparación entre distintos dongles y versiones de firmware.
