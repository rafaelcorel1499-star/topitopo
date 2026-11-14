# MotoScript AI

Generador de guiones virales de humor sobre motos con Gemini (app de escritorio para Windows).

## Compilar el .exe con GitHub Actions
1. Crea un repositorio en GitHub y sube **todo el contenido** de esta carpeta (incluida `.github/`).
2. Ve a la pestaña **Actions** > "Compilar MotoScript AI (.exe)" > **Run workflow**
   (también se ejecuta solo en cada push).
3. Al terminar (~3 min) descarga el artefacto **MotoScriptAI-windows** (contiene `MotoScriptAI.exe`).
4. Opcional: crea un tag `v1.0.0` y el .exe se publica en *Releases*.

## Conexión con Gemini
### Opción A: API Key (la más fácil)
1. Crea una clave gratis en https://aistudio.google.com/app/apikey
2. Pégala en Configuración > "API Key de Gemini" > Validar > Guardar.

### Opción B: Cuenta de Google (OAuth)
Google exige que el programa tenga un "cliente OAuth" propio:
1. En https://console.cloud.google.com crea un proyecto y habilita **Generative Language API**.
2. APIs y servicios > Pantalla de consentimiento OAuth (tipo Externo, añade tu correo como usuario de prueba).
3. Credenciales > Crear credenciales > **ID de cliente OAuth** > tipo **App de escritorio**. Descarga el JSON.
4. En la app: Configuración > "Seleccionar client_secret.json" > "Iniciar sesión con Google".
5. Si Google responde con error de cuota/proyecto, escribe tu ID de proyecto en el campo opcional.

Los datos (config, token, historial) se guardan en `%APPDATA%\MotoScriptAI`.
La API Key se guarda en texto plano en ese archivo: no compartas esa carpeta.

## Ejecutar sin compilar
```
pip install -r requirements.txt
python main.py
```
