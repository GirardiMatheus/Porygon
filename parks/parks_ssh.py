import logging
from dotenv import load_dotenv
import pexpect
import os

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

ip_oltp = os.getenv('LAB_IP_PARKS')
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
        return None

