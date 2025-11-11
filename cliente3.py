import socket
import threading
import sys
from colorama import init, Fore, Style

# Inicializa colorama
init(autoreset=True)

# --- CONFIGURAÇÕES ---
# **IMPORTANTE: Mude 'SERVER_IP' para o IP local do seu Servidor LAN!**
SERVER_IP = '198.27.12.215' 
PORT = 55555
ENCODING = 'utf-8'
BUFFER_SIZE = 1024

# Variáveis globais
nickname = ""
chat_active = True

# --- FUNÇÕES ROBUSTAS DE REDE ---

def send_message(client_socket, message):
    """Função robusta para enviar mensagens longas."""
    try:
        encoded_message = message.encode(ENCODING)
        data_length = len(encoded_message)
        
        # 1. Envia o tamanho
        client_socket.sendall(data_length.to_bytes(4, byteorder='little'))
        
        # 2. Envia os dados
        client_socket.sendall(encoded_message)
        return True
    except:
        return False

def receive_message(client_socket):
    """Função robusta para receber mensagens longas."""
    try:
        # 1. Recebe o tamanho
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
            return None 
            
        return data.decode(ENCODING)
    except:
        return None

# --- FUNÇÕES DE INTERFACE ---

def print_message(message, color=Fore.GREEN):
    """Imprime uma mensagem colorida de forma segura."""
    sys.stdout.write(f"\n{color}{message}{Style.RESET_ALL}\n")
    sys.stdout.flush()

def receive(client):
    """Thread para receber e exibir mensagens do servidor."""
    global chat_active
    while chat_active:
        message = receive_message(client)
        
        if message is None:
            if chat_active:
                print_message("Conexão perdida com o servidor (ou servidor desligado).", Fore.RED)
            chat_active = False
            break

        # --- Tratamento do Protocolo/Mensagens ---
        if message == 'NICK':
            send_message(client, nickname)
        
        elif message.startswith('[DM de '):
            print_message(message, Fore.YELLOW)
        
        elif message.startswith('[DM para '):
            print_message(message, Fore.LIGHTMAGENTA_EX)

        elif message.startswith('[SISTEMA]'):
            print_message(message, Fore.CYAN)
        
        elif message.startswith('[ERRO]'):
            print_message(message, Fore.RED)
        
        elif message.startswith('--- Lista de Usuários e Salas'):
            # Imprime a lista de usuários formatada
            print_message(message, Fore.BLUE)
        
        elif message.startswith('O servidor foi desligado.'):
            print_message(message, Fore.RED)
            chat_active = False
            break
            
        else:
            # Mensagens públicas (com tag de sala)
            print_message(message)

def write(client):
    """Thread para ler o input do usuário e enviar comandos/mensagens."""
    global chat_active
    while chat_active:
        try:
            # O prompt colorido usa o apelido do usuário
            user_input = input(f"{Fore.MAGENTA}{nickname}> {Style.RESET_ALL}")
            
            if not chat_active: break # Evita enviar após digitar /quit
            
            # O servidor gerencia todos os comandos, apenas enviamos o input
            if user_input.lower() == '/quit':
                print_message("Saindo do chat...", Fore.YELLOW)
                send_message(client, '/quit')
                chat_active = False
                client.close()
                break

            send_message(client, user_input)
            
        except EOFError: 
            print_message("Saindo por EOF...", Fore.YELLOW)
            send_message(client, '/quit')
            chat_active = False
            client.close()
            break
        except Exception as e:
            if chat_active:
                print_message(f"Erro no envio: {e}", Fore.RED)
            chat_active = False
            client.close()
            break

# --- INICIALIZAÇÃO DO CLIENTE ---

def start_client():
    """Função principal para iniciar o cliente."""
    global nickname
    
    while not nickname:
        nickname = input("Escolha seu apelido: ").strip()
        if not nickname:
            print("Apelido não pode ser vazio.")
            
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"Tentando conectar a {SERVER_IP}:{PORT}...")
        client.connect((SERVER_IP, PORT))
        print_message("Conectado! Digite /help para ver os comandos.", Fore.GREEN)
        
    except ConnectionRefusedError:
        print_message(f"Erro: Conexão recusada. Verifique o IP e se o servidor está ativo em {SERVER_IP}:{PORT}.", Fore.RED)
        sys.exit()
    except Exception as e:
        print_message(f"Ocorreu um erro ao conectar: {e}", Fore.RED)
        sys.exit()

    receive_thread = threading.Thread(target=receive, args=(client,))
    receive_thread.daemon = True
    receive_thread.start()

    write_thread = threading.Thread(target=write, args=(client,))
    write_thread.start()
    
    write_thread.join()
    if chat_active:
        client.close()
    
    print("Programa cliente encerrado.")

if __name__ == '__main__':
    start_client()