import requests
import os

# Constante para el estado "Abierto" en Freshdesk es 2

# Constante para el estado "Pendiente" en Freshdesk (para la búsqueda) es 3



def _obtener_tickets_pendientes_fd(domain, api_key):
    url = f"https://{domain}.freshdesk.com/api/v2/search/tickets"
    # Buscar tickets que están en estado Pendiente (3) y no tienen agente asignado
    query_string = f'status:3 AND agent_id:null' 
    params = {'query': f'"{query_string}"'}
    response_obj = None
    try:
        response_obj = requests.get(url, auth=(api_key, 'x'), params=params)
        response_obj.raise_for_status()
        data = response_obj.json()
        return data.get('results', [])
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"Error HTTP (obtener pendientes): {http_err}"
        if response_obj and hasattr(response_obj, 'text'): error_msg += f"\nServer: {response_obj.text}"
        print(error_msg)
    except Exception as e: print(f"Error (obtener pendientes): {e}")
    return []

def _asignar_y_abrir_ticket_fd(domain, api_key, ticket_id, agente_id):
    """
    Asigna un agente al ticket y cambia su estado a Abierto (2).
    """
    url = f"https://{domain}.freshdesk.com/api/v2/tickets/{ticket_id}"
    # Payload para actualizar el ticket: asignar agente y cambiar estado a Abierto
    data = {
        "responder_id": agente_id,
        "status": 2
    }
    response_obj = None
    try:
        response_obj = requests.put(url, auth=(api_key, 'x'), json=data)
        response_obj.raise_for_status()
        print(f"Ticket #{ticket_id} asignado a agente ID {agente_id} y estado cambiado a Abierto.")
        return True
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"Error HTTP asignando/abriendo ticket #{ticket_id}: {http_err}"
        if response_obj and hasattr(response_obj, 'text'): error_msg += f"\nServer: {response_obj.text}"
        print(error_msg)
    except Exception as e: print(f"Error asignando/abriendo ticket #{ticket_id}: {e}")
    return False

def _enviar_respuesta_fd(domain, api_key, ticket_id, mensaje_body): 
    url = f"https://{domain}.freshdesk.com/api/v2/tickets/{ticket_id}/reply"
    headers = {"Content-Type": "application/json"}
    data = {"body": mensaje_body}
    response_obj = None
    try:
        response_obj = requests.post(url, auth=(api_key, 'x'), headers=headers, json=data)
        response_obj.raise_for_status()
        print(f"✅ Respuesta de apertura enviada al ticket #{ticket_id}.")
        return True
    except requests.exceptions.HTTPError as http_err:
        error_msg = f"❌ Error HTTP enviando respuesta apertura {ticket_id}: {http_err}"
        if response_obj and hasattr(response_obj, 'text'): error_msg += f"\nServer: {response_obj.text}"
        print(error_msg)
    except Exception as e: print(f"❌ Error enviando respuesta apertura {ticket_id}: {e}")
    return False

def _obtener_siguiente_agente_id_rotacion(agentes_operativos_ids_list, archivo_ultimo_agente_path):
    if not agentes_operativos_ids_list: return None 
    ultimo_id_guardado = None # Iniciar como None
    try:
        if os.path.exists(archivo_ultimo_agente_path):
            with open(archivo_ultimo_agente_path, "r", encoding='utf-8') as f:
                contenido = f.read().strip()
                if contenido: ultimo_id_guardado = str(contenido) 
    except Exception as e_read: print(f"Advertencia: No se pudo leer {archivo_ultimo_agente_path}. Error: {e_read}")
    
    siguiente_index = 0
    agentes_operativos_str_ids = [str(ag_id) for ag_id in agentes_operativos_ids_list]

    if ultimo_id_guardado and ultimo_id_guardado in agentes_operativos_str_ids: # Verificar que no sea None
        try:
            siguiente_index = (agentes_operativos_str_ids.index(ultimo_id_guardado) + 1) % len(agentes_operativos_str_ids)
        except ValueError: pass 
    
    if not agentes_operativos_str_ids: return None 
    
    siguiente_agente_id = agentes_operativos_str_ids[siguiente_index]
    try:
        with open(archivo_ultimo_agente_path, "w", encoding='utf-8') as f: f.write(str(siguiente_agente_id))
    except IOError as e_write: print(f"Advertencia: No se pudo escribir en {archivo_ultimo_agente_path}. Error: {e_write}")
    
    return siguiente_agente_id 


def ejecutar_proceso_asignaciones(
    fd_config, 
    plantilla_saludo_apertura, 
    archivos_estado_config, 
    script_dir, 
    mapa_agentes_cache, 
    agentes_operativos_cache 
):
    print("--- Iniciando Proceso de Asignación y Saludo de Apertura ---")
    
    api_key = fd_config.get('api_key')
    domain = fd_config.get('domain')
    ruta_ultimo_agente = os.path.join(script_dir, archivos_estado_config.get('ultimo_agente_asignado'))

    if not all([api_key, domain, plantilla_saludo_apertura, ruta_ultimo_agente]):
        print("Error (Asignación): Faltan configuraciones esenciales.")
        return

    if not agentes_operativos_cache:
        print("No hay agentes operativos disponibles. No se asignarán tickets.")
        print("--- Proceso de Asignación y Saludo de Apertura Finalizado ---")
        return

    tickets_para_procesar = _obtener_tickets_pendientes_fd(domain, api_key)
    if not tickets_para_procesar:
        print("No hay tickets pendientes (status 3) para asignar.")
        print("--- Proceso de Asignación y Saludo de Apertura Finalizado ---")
        return

    procesados_en_esta_ejecucion = 0
    for ticket in tickets_para_procesar:
        ticket_id_actual = ticket['id'] 
        
        if ticket.get('responder_id'): 
            continue

        agente_id_seleccionado_str = _obtener_siguiente_agente_id_rotacion(agentes_operativos_cache, ruta_ultimo_agente)
        
        if agente_id_seleccionado_str is None:
            print(f"No se pudo seleccionar un agente para ticket #{ticket_id_actual}. Omitiendo.")
            continue
        
        nombre_del_agente_para_mensaje = mapa_agentes_cache.get(agente_id_seleccionado_str, "nuestro equipo")

        respuesta_formateada = plantilla_saludo_apertura.format(
            ticket_id=ticket_id_actual,
            agent_name=nombre_del_agente_para_mensaje
        )
        
        try:
            agente_id_para_fd = int(agente_id_seleccionado_str)
        except ValueError:
            print(f"Error: ID de agente '{agente_id_seleccionado_str}' no es un entero. Omitiendo ticket #{ticket_id_actual}.")
            continue

        # Primero enviar respuesta, luego asignar y abrir.
        if _enviar_respuesta_fd(domain, api_key, ticket_id_actual, respuesta_formateada):
            if _asignar_y_abrir_ticket_fd(domain, api_key, ticket_id_actual, agente_id_para_fd): 
                print(f"Ticket #{ticket_id_actual} PROCESADO: Respuesta enviada, asignado a {nombre_del_agente_para_mensaje} (ID: {agente_id_para_fd}) y ABIERTO.")
                procesados_en_esta_ejecucion += 1
            else:
                print(f"Ticket #{ticket_id_actual}: Respuesta enviada, PERO FALLÓ asignación/apertura a {nombre_del_agente_para_mensaje}.")
        else:
            print(f"Ticket #{ticket_id_actual}: FALLÓ envío de respuesta apertura. No se asignará ni abrirá.")

    if procesados_en_esta_ejecucion > 0:
        print(f"Se procesaron {procesados_en_esta_ejecucion} asignaciones de tickets.")
    print("--- Proceso de Asignación y Saludo de Apertura Finalizado ---")