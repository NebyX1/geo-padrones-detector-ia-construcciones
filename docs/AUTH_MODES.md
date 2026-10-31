# Login, captcha, doble factor y prueba local

El acceso protegido se conserva completo: correo + contraseña + suma numérica, seguido del código de doble factor por correo. El captcha sigue el ejemplo administrativo de sample: dos números de 1 a 10. Se valida en el servidor, vence en diez minutos, se vincula al navegador y no se reutiliza después de una respuesta incorrecta o contraseña inválida. La respuesta no se guarda en la cookie ni se devuelve por la API.

El checkpoint local `auth-captcha-2fa-preserved` (commit `22bfbd9`) guarda el flujo protegido antes de añadir la entrada temporal. El commit `bd3b789` conserva la implementación original anterior al captcha. No se eliminaron los componentes ni endpoints de login/2FA.

## Probar sin autenticación

Con Docker local activo:

```powershell
.\.venv\Scripts\python.exe scripts/set_local_preview.py on --restart
```

Abrir http://127.0.0.1:8787. Se muestra un aviso de modo de prueba y se entra directamente al explorador. http://127.0.0.1:8787/login permite ver el login con captcha conservado.

La opción privada es `DEV_AUTH_BYPASS=true` en el `.env` raíz. El valor de ejemplo y el predeterminado son false; la activación actual se hace por pedido expreso del usuario. Solo funciona con configuración development y nombres de host localhost/127.0.0.1/::1. Compose mantiene el acceso HTTP publicado en loopback. No se debe exponer este entorno de desarrollo a una red pública.

El modo permite probar las funciones con una identidad técnica local reservada, sin contraseña utilizable ni correo de recuperación. Los trabajos, importaciones, exportaciones y revisiones mantienen sus relaciones y auditoría; las acciones se marcan `local_preview=true`. Esa identidad no se cuenta como administrador humano, no aparece en la gestión de cuentas y no admite login por contraseña ni una sesión persistente fuera de este modo. Se conserva en la base para no romper las referencias del historial de pruebas.

CSRF y los límites de operación siguen habilitados. Las rutas reales de login, captcha, recuperación y doble factor mantienen sus verificaciones, aun cuando se habilite la entrada local. Las pruebas automatizadas no heredan este acceso temporal.

## Volver al acceso protegido

```powershell
.\.venv\Scripts\python.exe scripts/set_local_preview.py off --restart
```

Después recargar el navegador: se exige nuevamente login + captcha + doble factor. No hace falta borrar código ni revertir migraciones. Una cookie o identidad de prueba anterior no permite entrar con la opción apagada. Producción rechaza arrancar si se configura DEV_AUTH_BYPASS=true.

El administrador humano inicial puede crearse con `docker compose exec backend flask create-admin`, o desde Administración mientras se prueba localmente. Las pruebas locales no convierten sus resultados en evidencia validada ni modifican las credenciales de usuarios existentes.
