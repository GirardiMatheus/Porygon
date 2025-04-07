import logging
from dotenv import load_dotenv
import pexpect
import os
import time

def setup_logging():
    """Configura o sistema de logging com rotação de arquivos"""
    logging.basicConfig(
        filename=f"OLT_LOG.log",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    logging.info("="*50)
    logging.info("Iniciando nova sessão de conexão OLT")
    logging.info("="*50)

def log_interaction(action, details="", level="info"):
    """Função padronizada para registro de logs"""
    message = f"{action.upper()} | {details}"
    if level.lower() == "debug":
        logging.debug(message)
    elif level.lower() == "warning":
        logging.warning(message)
    elif level.lower() == "error":
        logging.error(message)
    else:
        logging.info(message)



# Carrega variáveis do arquivo .env
load_dotenv()
setup_logging()

ip_oltp = os.getenv('BACAXA_IP_02')
ssh_userp = os.getenv('SSH_USER_PARKS')
ssh_passwdp = os.getenv('SSH_PASSWORD_PARKS')

def login_ssh():
    try:
        child = pexpect.spawn(f"ssh {ssh_userp}@{ip_oltp}", encoding='utf-8', timeout=30)
        index = child.expect(["password:", "Are you sure you want to continue connecting", pexpect.TIMEOUT], timeout=10)
        if index == 1:
            child.sendline("yes")
            child.expect("password:")
        child.sendline(ssh_passwdp)
        login_success = child.expect([r"#", pexpect.TIMEOUT, pexpect.EOF], timeout=10)

        if login_success == 0:
            log_interaction("Conexão estabelecida", f"Conectado à OLT {ip_oltp}")
            print(f"✅ Conectado com sucesso à OLT {ip_oltp}")

        else:
            log_interaction("Erro SSH", "Não foi possível autenticar na OLT", "error")
            print("❌ Falha na autenticação")
    
        return child
    
    except pexpect.EOF:
        log_interaction("Erro SSH", "Conexão fechada inesperadamente", "error")
        print("❌ Erro: Conexão foi fechada antes do login.")
        
    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Falha na conexão SSH: {str(e)}"
        log_interaction("Erro SSH", error_msg, "error")
        print(error_msg)
        return None
        
    except Exception as e:
        error_msg = f"Erro inesperado: {str(e)}"
        log_interaction("Erro geral", error_msg, "error")
        print(error_msg)

def list_unauthorized(child):
    try:
        # Envia o comando e captura a saída
        child.sendline('show gpon blacklist')
        child.expect('#')  # Captura até o prompt
        output = child.before.strip()  # Remove espaços extras

        # Processa as linhas
        lines = output.splitlines()
        valid_entries = []
        
        for line in lines:
            line = line.strip()
            
            # Pula linhas que não contêm dados de ONU
            if not line.startswith(('0 |', '1 |', '2 |', '3 |', '4 |', '5 |', '6 |', '7 |', '8 |', '9 |')):
                continue
            
            parts = [part.strip() for part in line.split('|')]
            
            # Verifica se tem Slot, Port e Serial
            if len(parts) < 3:
                continue
            
            slot, port, serial = parts[0], parts[1], parts[2]
            
            # Filtra slots, ports e serials inválidos
            if (not slot.isdigit() or int(slot) > 64 or
                not port.isdigit() or int(port) > 128 or
                not serial or len(serial) < 6 or ' ' in serial):
                continue
            
            valid_entries.append(f"Slot: {slot} PON: {port} Serial: {serial}")

        # Retorna resultados formatados
        if valid_entries:
            return "\n".join(valid_entries)
        else:
            return "Nenhuma ONU na blacklist."

    except Exception as e:
        logging.error(f"Erro ao listar ONUs não autorizadas: {e}")
        return f"Erro: {e}"

    finally:
        child.sendline('exit')
        child.terminate()

def consult_information(child, serial):
    try:
        log_interaction(serial)
        # Pré-processamento do serial
        serial = serial.strip().lower()  # Remove espaços e converte para minúsculas

        # Validação básica (ex: serial deve ter 12 caracteres)
        if len(serial) != 12:  # Ajuste conforme o padrão da sua OLT
            logging.error(f"Serial inválido: deve ter 12 caracteres (recebido: {serial})")
            return None
        log_interaction(f"Serial ajustado para o padrão da OLT: {serial}")
        # Envia o comando para consultar a ONU pelo serial
        comando = f"show gpon onu {serial} summary"
        child.sendline(comando)
        log_interaction(comando)
        child.expect("#")  # Aguarda o prompt de comando
        output = child.before.strip()
        log_interaction(child.before)

        # Extrai os dados relevantes
        data = {
            "serial": None,
            "alias": None,
            "model": None,
            "power_level": None,
            "distance_km": None,
            "status": None
        }

        for line in output.splitlines():
            line = line.strip()
            
            # Extrai Serial
            if line.startswith("Serial"):
                data["serial"] = line.split(":")[1].strip()
            
            elif line.startswith("Alias"):
                data["alias"] = line.split(":")[1].strip()
            
            # Extrai Modelo
            elif line.startswith("Model"):
                data["model"] = line.split(":")[1].strip()
            
            # Extrai Power Level (formato "-XX.XXdBm")
            elif line.startswith("Power Level"):
                power_str = line.split(":")[1].strip()
                # Pega apenas o valor principal (ex: "-21.74dBm")
                data["power_level"] = power_str.split(" ")[0].strip()
            
            # Extrai Distance (converte de metros para KM)
            elif line.startswith("Distance"):
                distance_str = line.split(":")[1].strip()
                distance_m = int(distance_str.split(" ")[0])  # Pega o valor em metros
                data["distance_km"] = round(distance_m / 1000, 2)  # Converte para KM
            
            # Extrai Status (ACTIVE ou INACTIVE)
            elif line.startswith("Status"):
                status_str = line.split(":")[1].strip()
                # Pega apenas "ACTIVE" ou "INACTIVE" (ignora "(PROVISIONED)")
                data["status"] = status_str.split(" ")[0].strip()

        # Retorna os dados em formato dicionário
        return data

    except Exception as e:
        logging.error(f"Erro ao consultar ONU {serial}: {e}")
        return None

    finally:
        child.sendline("exit")
        child.terminate()



