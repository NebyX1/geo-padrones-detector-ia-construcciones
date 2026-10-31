# ADR-003: separar bootstrap PostgreSQL del acceso de aplicación

El rol POSTGRES_USER del contenedor es administrador de bootstrap y puede instalar extensiones. No es un usuario de la plataforma web. En producción la API y el worker rechazan arrancar si su rol de conexión tiene SUPERUSER, CREATEROLE o CREATEDB.

Configurar DATABASE_APP_USER y DATABASE_APP_PASSWORD con un rol dedicado y contraseña aleatoria. En una instalación nueva, el script 90-app-role.sh crea un LOGIN sin esos privilegios y le otorga CONNECT y USAGE/CREATE sobre public. Las migraciones crean tablas bajo ese rol. PostGIS se inicializa mediante el bootstrap del contenedor antes del script. Los secretos se leen del entorno con psql \getenv y nunca se pasan como argumentos de proceso.

Para un volumen existente, el init de PostgreSQL no se repite. Un DBA debe ejecutar el script y transferir explícitamente la propiedad/permisos de las tablas de aplicación, preservando extensiones y esquemas internos. No se ejecuta REASSIGN OWNED global, porque podría transferir objetos fuera del dominio de la aplicación. El cambio requiere backup y revisión en ese entorno.

El entorno local de desarrollo puede usar el propietario del contenedor para facilitar pruebas que crean bases efímeras; esta excepción no se admite con FLASK_CONFIG=production. El administrador web se crea mediante un comando separado con contraseña oculta y no tiene relación con los privilegios PostgreSQL.
