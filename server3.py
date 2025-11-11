import socket
import threading
import sys
import time
from datetime import datetime

# --- CONFIGURAÇÕES ---
HOST = '0.0.0.0'
PORT = 55555
ENCODING = 'utf-8'
# Tempo máximo de inatividade (em segundos)
HEARTBEAT_TIMEOUT = 300 
BUFFER_SIZE = 1024

# --- ESTRUTURA DE DADOS GLOBAL ---
clients = [] # Lista de sockets
# Mapeia socket -> nickname
nicknames = {}
# Mapeia nickname -> socket
nickname_to_socket = {}
# Mapeia socket -> sala atual do usuário (padrão: '#geral')
client_rooms = {} 
# Mapeia socket -> último momento de atividade
last_activity = {} 
# Mapeia nome da sala -> lista de sockets
rooms = {'#geral': []}

# --- FUNÇÕES AUXILIARES ---

def get_formatted_time():
    """Retorna a hora atual formatada."""
    return datetime.now().strftime('%H:%M:%S')

def send_message(client_socket, message):
    """Função robusta para enviar mensagens longas."""
    try:
        # Codifica a mensagem
        encoded_message = message.encode(ENCODING)
        data_length = len(encoded_message)
        
        # 1. Envia o tamanho da mensagem (4 bytes fixos, little-endian)
        client_socket.sendall(data_length.to_bytes(4, byteorder='little'))
        
        # 2. Envia os dados
        client_socket.sendall(encoded_message)
        return True
    except:
        return False

def receive_message(client_socket):
    """Função robusta para receber mensagens longas."""
    try:
        # 1. Recebe o tamanho da mensagem (4 bytes)
        length_bytes = client_socket.recv(4)
        if not length_bytes: return None
        
        data_length = int.from_bytes(length_bytes, byteorder='little')
        
        # 2. Recebe os dados em pedaços
        data = b''
        while len(data) < data_length:
            chunk = client_socket.recv(min(data_length - len(data), BUFFER_SIZE))
            if not chunk: break 
            data += chunk
            
        if len(data) < data_length:
            return None # Conexão perdida durante a transferência
            
        return data.decode(ENCODING)
    except:
        return None

def broadcast_room(room_name, message, sender_client=None):
    """Envia uma mensagem para todos os clientes em uma sala."""
    if room_name in rooms:
        for client in rooms[room_name]:
            if client != sender_client:
                send_message(client, message)

def send_private_message(sender_socket, recipient_nickname, message):
    """Envia uma mensagem para um único destinatário (DM)."""
    recipient_socket = nickname_to_socket.get(recipient_nickname)
    sender_nickname = nicknames.get(sender_socket)
    
    if recipient_socket and recipient_socket in clients:
        # Mensagem para o destinatário
        full_message_rec = f"[{get_formatted_time()}] [DM de {sender_nickname}]: {message}"
        send_message(recipient_socket, full_message_rec)
        
        # Confirmação para o remetente
        confirmation = f"[{get_formatted_time()}] [DM para {recipient_nickname}]: {message}"
        send_message(sender_socket, confirmation)

        print(f"[{get_formatted_time()}] DM enviada: {sender_nickname} -> {recipient_nickname}")
        return True
    else:
        error_msg = f"[{get_formatted_time()}] [ERRO] Usuário '{recipient_nickname}' não encontrado ou desconectado."
        send_message(sender_socket, error_msg)
        return False

def handle_disconnection(client):
    """Remove o cliente de todas as estruturas de dados e notifica os demais."""
    if client in clients:
        clients.remove(client)
        nickname = nicknames.get(client)
        room_name = client_rooms.get(client)
        
        if nickname:
            # 1. Limpa todas as estruturas
            if nickname in nickname_to_socket: del nickname_to_socket[nickname]
            if client in nicknames: del nicknames[client]
            if client in client_rooms: del client_rooms[client]
            if client in last_activity: del last_activity[client]
            
            # 2. Remove da sala
            if room_name and client in rooms.get(room_name, []):
                rooms[room_name].remove(client)
                
            print(f"[{get_formatted_time()}] DISCONNECT: {nickname}")
            
            # 3. Notifica a sala
            sys_message = f"[{get_formatted_time()}] [SISTEMA] {nickname} saiu do chat."
            broadcast_room(room_name, sys_message, None)
            
        client.close()

# --- COMANDOS DO CHAT ---

def command_join(client_socket, new_room):
    """Move o cliente para uma nova sala."""
    nickname = nicknames.get(client_socket)
    current_room = client_rooms.get(client_socket)
    
    if new_room.startswith('#'):
        # 1. Remove da sala atual (se houver)
        if current_room and client_socket in rooms.get(current_room, []):
            rooms[current_room].remove(client_socket)
            leave_msg = f"[{get_formatted_time()}] [SISTEMA] {nickname} saiu da sala."
            broadcast_room(current_room, leave_msg, client_socket)
            
        # 2. Cria a nova sala se não existir
        if new_room not in rooms:
            rooms[new_room] = []

        # 3. Adiciona e atualiza estruturas
        rooms[new_room].append(client_socket)
        client_rooms[client_socket] = new_room
        
        # 4. Notifica
        join_msg = f"[{get_formatted_time()}] [SISTEMA] {nickname} entrou na sala."
        broadcast_room(new_room, join_msg, client_socket)
        send_message(client_socket, f"[{get_formatted_time()}] [SISTEMA] Você entrou em {new_room}.")
        print(f"[{get_formatted_time()}] {nickname} moveu-se para {new_room}.")
    else:
        send_message(client_socket, f"[{get_formatted_time()}] [ERRO] O nome da sala deve começar com '#'.")


def command_list_users(client_socket):
    """Lista usuários na sala atual e salas disponíveis."""
    current_room = client_rooms.get(client_socket, '#geral')
    nickname = nicknames.get(client_socket)
    
    # 1. Usuários na sala atual
    room_members = [nicknames.get(c) for c in rooms.get(current_room, []) if nicknames.get(c)]
    user_list = ", ".join(sorted(room_members))
    
    # 2. Salas disponíveis
    available_rooms = ", ".join(sorted(rooms.keys()))
    
    response = f"--- Lista de Usuários e Salas ({get_formatted_time()}) ---\n"
    response += f"Você está em: {current_room}\n"
    response += f"Usuários em {current_room}: {user_list}\n"
    response += f"Salas disponíveis: {available_rooms}\n"
    response += "--------------------------------------------------------"
    
    send_message(client_socket, response)

def command_help(client_socket):
    """Envia a lista de comandos disponíveis."""
    help_message = (
        "--- Comandos Disponíveis ---\n"
        "/quit - Desconecta do chat.\n"
        "/list - Lista usuários na sua sala e salas disponíveis.\n"
        "/dm <nickname> <mensagem> - Envia uma mensagem privada.\n"
        "/join <#sala> - Entra em um canal (ex: /join #dev).\n"
        "/help - Mostra esta ajuda.\n"
        "--------------------------"
    )
    send_message(client_socket, help_message)


# --- LOOP PRINCIPAL DO CLIENTE ---

def handle_client(client):
    """Gerencia a comunicação de um único cliente em uma thread separada."""
    nickname = nicknames.get(client, 'Desconhecido')
    
    # Define a sala padrão ao conectar
    client_rooms[client] = '#geral'
    rooms['#geral'].append(client)
    last_activity[client] = time.time()
    
    while True:
        try:
            message = receive_message(client)
            
            if message is None: # Conexão fechada, reinicializada ou inatividade
                handle_disconnection(client)
                break
            
            # Atualiza a atividade
            last_activity[client] = time.time()

            current_room = client_rooms.get(client, '#geral')

            # --- Tratamento de Comandos ---
            if message.startswith('/quit'):
                handle_disconnection(client)
                break
                
            elif message.startswith('/dm '):
                parts = message.split(' ', 2)
                if len(parts) >= 3:
                    send_private_message(client, parts[1], parts[2])
                else:
                    send_message(client, f"[{get_formatted_time()}] [ERRO] Comando /dm inválido. Use: /dm <nickname> <mensagem>")

            elif message.startswith('/join '):
                parts = message.split(' ', 1)
                if len(parts) == 2:
                    command_join(client, parts[1])
                else:
                    send_message(client, f"[{get_formatted_time()}] [ERRO] Comando /join inválido. Use: /join <#sala>")

            elif message.startswith('/list'):
                command_list_users(client)

            elif message.startswith('/help'):
                command_help(client)
            
            # --- Mensagem Pública ---
            else:
                full_message = f"[{get_formatted_time()}] [{current_room}] {nickname}: {message}"
                print(full_message)
                broadcast_room(current_room, full_message, client)

        except Exception as e:
            print(f"Erro inesperado com {nickname}: {e}")
            handle_disconnection(client)
            break

# --- THREAD DE HEARTBEAT ---

def heartbeat_checker():
    """Verifica a inatividade dos clientes periodicamente."""
    while True:
        time.sleep(30) # Verifica a cada 30 segundos
        
        clients_to_remove = []
        current_time = time.time()
        
        for client, last_time in last_activity.items():
            if current_time - last_time > HEARTBEAT_TIMEOUT:
                clients_to_remove.append(client)
                
        for client in clients_to_remove:
            nickname = nicknames.get(client, 'Desconhecido')
            print(f"[{get_formatted_time()}] KICK: {nickname} por inatividade.")
            try:
                send_message(client, f"[{get_formatted_time()}] [SISTEMA] Você foi desconectado por inatividade ({HEARTBEAT_TIMEOUT}s).")
            except:
                pass # Ignora se falhar ao enviar a mensagem final
            handle_disconnection(client)

# --- INICIALIZAÇÃO DO SERVIDOR ---

def start_server():
    """Configura e inicia o loop principal do servidor."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
    except Exception as e:
        print(f"Erro ao iniciar o servidor: {e}")
        sys.exit()

    server.listen(10)
    print("=" * 50)
    print(f"[{get_formatted_time()}] SERVIDOR ONLINE em {HOST}:{PORT}")
    print(f"Timeout por inatividade: {HEARTBEAT_TIMEOUT} segundos.")
    print("Aguardando conexões...")
    print("=" * 50)

    # Inicia a thread de heartbeat
    heartbeat_thread = threading.Thread(target=heartbeat_checker, daemon=True)
    heartbeat_thread.start()

    try:
        while True:
            client, address = server.accept()
            print(f"[{get_formatted_time()}] CONECTADO com {str(address)}")

            # Pede o apelido (protocolo 'NICK')
            send_message(client, 'NICK')
            nickname = receive_message(client)

            # 1. Verifica duplicidade de nickname
            if nickname in nickname_to_socket:
                send_message(client, f"[{get_formatted_time()}] [ERRO] Apelido '{nickname}' já em uso. Desconectando.")
                client.close()
                print(f"[{get_formatted_time()}] REJEITADO: {nickname} (duplicado)")
                continue
            
            # 2. Armazena e notifica
            nicknames[client] = nickname
            nickname_to_socket[nickname] = client
            clients.append(client)
            
            print(f"[{get_formatted_time()}] Apelido definido: {nickname}")
            
            sys_message = f"[{get_formatted_time()}] [SISTEMA] {nickname} entrou no chat (#geral). Digite /help para comandos."
            send_message(client, "Conexão estabelecida. Digite /help para comandos.")
            broadcast_room('#geral', sys_message, client)

            # 3. Inicia thread do cliente
            thread = threading.Thread(target=handle_client, args=(client,))
            thread.daemon = True
            thread.start()
            
    except KeyboardInterrupt:
        print("\nServidor encerrado por KeyboardInterrupt.")
    except Exception as e:
        print(f"\nErro fatal no servidor: {e}")
    finally:
        print("Fechando conexões...")
        for client in clients:
            try:
                send_message(client, "O servidor foi desligado.")
                client.close()
            except:
                pass
        server.close()
        print("Servidor desligado.")
        sys.exit()

if __name__ == '__main__':
    start_server()