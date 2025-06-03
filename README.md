# freshdesk-ticket-automation
Descripción General del Proyecto
Este proyecto automatiza diversas tareas de gestión de tickets dentro de la plataforma Freshdesk. Se integra con Google Sheets para obtener dinámicamente los horarios de los agentes, su estado operativo y configuraciones globales como plantillas de mensajes y horarios de atención. El sistema está diseñado para:

Asignar automáticamente nuevos tickets a los agentes que se encuentren disponibles y en turno.
Enviar encuestas de satisfacción a los clientes una vez que sus tickets han sido cerrados.
Gestionar los tickets que se reciben fuera del horario de atención establecido, enviando una respuesta automática.
Mantener la eficiencia mediante el uso de cachés locales de la información obtenida de Google Sheets, reduciendo la necesidad de consultas constantes.

Componentes Principales
Scripts de Python (.py)

app.py: Es el orquestador principal de la aplicación. Se encarga de cargar la configuración inicial desde config.json y los datos de los cachés locales. Luego, ejecuta secuencialmente los diferentes módulos de automatización, como la actualización de cachés desde Google Sheets, el procesamiento de tickets fuera de horario, la asignación de tickets pendientes y el envío de encuestas de satisfacción.

google_sheets_handler.py: Este módulo interactúa con la API de Google Sheets para leer la configuración global de la aplicación (horarios generales de atención, plantillas de mensajes, zona horaria) y los detalles de los agentes (horarios, descansos, estado activo/inactivo). Con esta información, actualiza archivos de caché locales en formato JSON (cache_mapa_agentes.json, cache_agentes_operativos.json, cache_configuracion_global.json). Esto permite que los otros módulos accedan rápidamente a esta información sin necesidad de consultar Google Sheets en cada ejecución.

ticket_assigner.py: Se encarga de la lógica de asignación de tickets. Busca en Freshdesk los tickets que están en estado "Pendiente" y no tienen un agente asignado. Luego, selecciona un agente operativo de la lista obtenida del caché (cache_agentes_operativos.json) mediante un sistema de rotación (round-robin) y le asigna el ticket, cambiando su estado a "Abierto". También envía un mensaje de apertura al cliente informando sobre la asignación. Guarda el ID del último agente asignado en un archivo (ultimo_agente.txt) para continuar la rotación en la siguiente ejecución.

survey_sender.py: Este script gestiona el envío de encuestas de satisfacción para tickets que han sido recientemente cerrados (estados 5, 6 o 7 en Freshdesk). Para evitar envíos duplicados, verifica si el ticket ya tiene un tag específico ("Encuesta enviada") antes de proceder. Si no tiene el tag, envía un mensaje (cuya plantilla se obtiene de cache_configuracion_global.json) y luego actualiza el ticket en Freshdesk para restaurar su estado y agente original (ya que el envío de una respuesta puede reabrirlo) y añadir el tag de "Encuesta enviada".

fuera_horario.py: Este módulo maneja los tickets que llegan fuera del horario de atención general (definido en cache_configuracion_global.json). Si detecta que se está fuera de horario, busca tickets recientes sin agente asignado y que no hayan sido procesados previamente por este módulo (controlado mediante un archivo fuera_horario_procesados_ids.txt). A estos tickets les envía un mensaje informando sobre el horario de atención y procede a cerrarlos en Freshdesk.
Archivos de Configuración y Caché

config.json: Es el archivo de configuración principal y estático del proyecto. Contiene información sensible como la API key de Freshdesk, el dominio de Freshdesk, los nombres específicos de la planilla de Google Sheets y las hojas que utiliza google_sheets_handler.py. También define algunas plantillas de mensajes base (aunque las principales se cargan desde Google Sheets a través del caché) y los nombres de los archivos utilizados para guardar estados y cachés locales.

cache_mapa_agentes.json: Un archivo JSON que actúa como caché local del mapeo completo de IDs de agentes a sus nombres. Esta información es obtenida y actualizada por google_sheets_handler.py desde la hoja de horarios de agentes en Google Sheets.

cache_agentes_operativos.json: Archivo JSON que guarda la lista de los IDs de los agentes que se consideran operativos en el momento de la última actualización por google_sheets_handler.py. Un agente se considera operativo si está activo, en su turno según los horarios de Google Sheets, y no en un periodo de descanso.

cache_configuracion_global.json: Contiene un caché de la configuración global de la aplicación, como los horarios de atención generales (inicio y fin), las plantillas de mensajes para apertura, cierre con encuesta, y fuera de horario, y la zona horaria de la aplicación. Esta información es leída desde una hoja específica en Google Sheets por google_sheets_handler.py.


Blibliotecas a instalar
 Flask gspread google-auth requests pytz


Como es la configuracion de google sheet 

Agent_ID	    Agent_name	Status	 Descanso_Inicio_Hora  Lunes_1	      Lunes_2         Martes_1	    Martes_2   Miercoles_1   Miercoles_2   Jueves_1	      Jueves_2 . . . 		
0000000000000	Juan     	Activo	   17:00               09:00 a 14:00  15:00 a 17:00   09:00 a 17:00		       09:00 a 17:00	            09:00 a 17:00 . . . 		
0000000000000	Juan     	Inactivo                       09:00 a 14:00                  09:00 a 17:00		       09:00 a 17:00	            09:00 a 17:00 . . . 		


ClaveConfig               ValorConfig1	Comentarios_Opcionales
HORARIO_ATENCION_INICIO   07:00	
HORARIO_ATENCION_FIN	  01:00	
MENSAJE_APERTURA	      Hola! Gracias por contactarnos.<br><br>Tu número de ticket es {ticket_id} y ha sido asignado a nuestro agente {agent_name}.
MENSAJE_CIERRE_ENCUESTA	  Muchas gracias por haberte contactado con nosotros!. Te invitamos a completar una breve encuesta para valorar la atención recibida . . .  
MENSAJE_FUERA_HORARIO	  Actualmente estamos fuera de horario. <br> Nuestro horario de atencion es de. . . 
TIMEZONE_APP              America/Argentina/Buenos_Aires

