# Administrar análisis y revisiones

En **Análisis con IA** y **Casos para revisar** se puede buscar por padrón o localidad y filtrar por fecha, modelo y estado. Las revisiones también se filtran por detección y metros cuadrados; los trabajos, por procesador. Los resultados están paginados y el contador incluye todas las páginas. «Limpiar filtros» devuelve la lista completa.

Un administrador puede eliminar un elemento, seleccionar varios, eliminar todos los filtrados o usar **Empezar de cero**. Antes de borrar se presenta el alcance real, incluidos los datos relacionados, y se solicita escribir `ELIMINAR`. Los trabajos en curso deben finalizar o cancelarse desde el mismo cuadro; si la información cambia antes de confirmar, hay que volver a revisar el alcance.

Eliminar un análisis elimina sus resultados, huellas, máscaras, revisiones, observaciones y adjuntos. Eliminar un caso de revisión también elimina su resultado de IA asociado. El padrón afectado vuelve a figurar sin análisis si ese era su resultado actual. Los padrones, el catastro, los modelos, las imágenes de origen y las declaraciones importadas siguen disponibles. Los resultados viejos no se restauran automáticamente; se puede ejecutar un análisis nuevo, incluso con los mismos parámetros anteriores.

Las comparaciones que dependían de los resultados eliminados también se borran. Las exportaciones anteriores se invalidan y eliminan porque podrían contener resultados borrados; el cuadro de confirmación indica cuántas hay. Se elimina la actividad vinculada, incluidas observaciones de solicitudes de reanálisis, y se conserva únicamente un registro general de la operación de eliminación, sin observaciones ni resultados borrados.

El borrado de registros se confirma en la base de datos y la eliminación de máscaras, adjuntos, exportaciones y trabajos de la cola continúa de forma segura en segundo plano. Si el almacenamiento falla, los elementos pendientes se reintentan y se muestra su número en la interfaz. Las imágenes aéreas de origen en caché son compartidas por otros análisis y se conservan.

La eliminación requiere permisos de administrador o superadministrador. Una consulta o revisión no otorga permiso para borrar resultados. Los trabajos activos no se eliminan mientras el worker puede seguir escribiendo, y las listas se vuelven a comprobar al confirmar para evitar borrar datos que aparecieron después de la previsualización.
