# Robot UiPath — NovaBank_Robot_Retencion

Automatización del MVP: **disparador → obtener predicciones → regla de decisión → acción**.

- Proyecto **Windows**, lenguaje **VB.NET**, Studio 2025.10 / 2026.0
- Única dependencia: `UiPath.System.Activities [25.10.5]`
- Las llamadas a la API y el correo SMTP se hacen con **Invoke Code** usando librerías de .NET
  (`System.Net.Http`, `System.Net.Mail`), así no se necesitan paquetes adicionales.

## Flujo (`Main.xaml`)

| Paso | Qué hace | Actividades |
|---|---|---|
| Disparador | Orchestrator (Time Trigger) o ejecución manual desde Studio/Assistant | — |
| 1. Verificar API | `GET /health`; si no responde 200 → excepción con instrucción para levantar la API | Invoke Code, If, Throw |
| 2. Obtener predicciones | `GET /clientes/alto-riesgo?umbral=0.45&limite=20&solo_pendientes=true` → lista JSON | Invoke Code, Assign (JArray) |
| 3. Regla de decisión | Para cada cliente: si `prob_abandono >= 0.70` → **Urgente** (asignar al equipo de retención); si no → **Campaña** automática | For Each, Switch, Try Catch |
| 3. Acción (registro) | `POST /acciones` → se guarda en la tabla `gold_acciones_log` de la capa Gold | Invoke Code, If |
| 4. Indicadores | `GET /resumen` → clientes y saldo en riesgo alto, acciones acumuladas | Invoke Code |
| 5. Acción (correo) | Correo HTML por SMTP Gmail con el resumen y la tabla de casos urgentes | Get Credential, Invoke Code |

Como la API excluye a los clientes que ya tienen una acción ejecutada, cada corrida del robot
procesa los siguientes clientes pendientes y nunca contacta dos veces al mismo cliente.

## Argumentos (se pueden cambiar en Studio o en Orchestrator)

| Argumento | Valor por defecto | Descripción |
|---|---|---|
| `in_ApiUrl` | `http://127.0.0.1:8000` | URL de la API FastAPI |
| `in_Umbral` | `0.45` | Probabilidad mínima para considerar al cliente (riesgo Alto) |
| `in_UmbralUrgente` | `0.7` | A partir de esta probabilidad el caso es **Urgente** |
| `in_Limite` | `20` | Máximo de clientes por corrida |
| `in_Destinatario` | *(vacío)* | Correo destino; si está vacío se envía a la misma cuenta de Gmail |
| `in_AssetGmail` | `NovaBank_Gmail` | Nombre del asset de tipo *Credential* en Orchestrator |
| `in_SmtpServidor` / `in_SmtpPuerto` | `smtp.gmail.com` / `587` | Servidor SMTP (TLS) |

## Configuración

### 1. Contraseña de aplicación de Gmail
1. Activar la verificación en 2 pasos en la cuenta de Google.
2. Ir a <https://myaccount.google.com/apppasswords>, crear una contraseña de aplicación
   (por ejemplo "UiPath NovaBank") y copiar los 16 caracteres.

### 2. Credencial para el robot (elegir una opción)
- **Opción A — Orchestrator (recomendada):** en la carpeta donde corre el robot, crear un asset
  tipo **Credential** llamado `NovaBank_Gmail` con usuario = correo de Gmail y contraseña = la
  contraseña de aplicación.
- **Opción B — Variables de entorno (respaldo, sin Orchestrator):** en una terminal ejecutar
  ```
  setx NOVABANK_GMAIL_USER "tu_correo@gmail.com"
  setx NOVABANK_GMAIL_APP_PASSWORD "xxxxxxxxxxxxxxxx"
  ```
  y reiniciar Studio / Assistant.

Si no hay credenciales, el robot igual registra las acciones en la tabla y solo omite el correo.

### 3. Ejecutar
1. Levantar la API desde la raíz del repositorio: `python -m src.api`
2. (Opcional, para empezar la demo desde cero) `python -m src.reiniciar_acciones`
3. Abrir `uipath/NovaBank_Robot_Retencion/project.json` en UiPath Studio y ejecutar **Run**.
4. Revisar el panel *Output*, el correo recibido y `GET http://127.0.0.1:8000/acciones`.

### 4. Disparador en Orchestrator
1. **Publish** del proyecto a Orchestrator y crear el **Process** en la carpeta.
2. Crear un **Time Trigger** (por ejemplo, todos los días a las 8:00).
3. El robot debe ejecutarse en la misma máquina donde corre la API (usa `127.0.0.1`).
   Si el robot corre en otra máquina, exponer la API (por ejemplo con ngrok) y cambiar `in_ApiUrl`.
