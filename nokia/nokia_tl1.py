import pexpect
import os
from dotenv import load_dotenv
import logging
# from collections import defaultdict
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

def login_olt_tl1(): 
    """Estabelece conexão TL1 com a OLT"""
    try:
        log_interaction("Iniciando conexão TL1", "Obtendo variáveis de ambiente")
        
        tl1_user = os.getenv('TL1_USER')
        tl1_passwd = os.getenv('TL1_PASSWORD')
        olt_ip = os.getenv('LAB_IP')
        tl1_port = os.getenv('TL1_PORT')
        
        if not all([tl1_user, tl1_passwd, olt_ip, tl1_port]):
            error_msg = "Variáveis TL1 não configuradas corretamente"
            log_interaction("Erro de configuração TL1", error_msg, "error")
            raise ValueError(error_msg)
        
        log_interaction("Conectando TL1", f"Usuário: {tl1_user} | OLT: {olt_ip}")
        
        # Conexão TL1
        child = pexpect.spawn(f'ssh {tl1_user}@{olt_ip} -p {tl1_port}', 
                              encoding='utf-8', 
                              timeout=30)

        # Verifica resposta do SSH
        index = child.expect([
            "password:", 
            "Are you sure you want to continue connecting", 
            "Permission denied",  
            pexpect.TIMEOUT
        ], timeout=10)

        if index == 1:
            log_interaction("TL1", "Primeira conexão - aceitando certificado", "debug")
            child.sendline("yes")
            child.expect("password:")

        elif index == 2:
            log_interaction("Erro TL1", "Falha na autenticação. Credenciais inválidas.", "error")
            print("❌ Erro: Usuário ou senha inválidos.")
            return None
        
        log_interaction("TL1", "Enviando credenciais de acesso", "debug")
        child.sendline(tl1_passwd)

        # Aguarda a resposta do login
        login_success = child.expect(["Welcome to ISAM", "Permission denied", pexpect.TIMEOUT, pexpect.EOF], timeout=10)

        if login_success == 1:  # Se a senha estiver errada
            log_interaction("Erro TL1", "Falha na autenticação. Credenciais inválidas.", "error")
            print("❌ Erro: Usuário ou senha inválidos.")
            return None  # Aqui garantimos que o código pare imediatamente!

        elif login_success != 0:  # Se não encontrou "Welcome to ISAM", algo deu errado
            log_interaction("Erro TL1", "Falha ao conectar à OLT via TL1.", "error")
            print("❌ Erro: Conexão não estabelecida.")
            return None

        log_interaction("TL1", "Login bem-sucedido, aguardando prompt TL1", "debug")

        # Manda ENTER algumas vezes para garantir que pegamos o prompt correto
        for _ in range(3):
            child.sendline("")
            child.expect([r"<.*>", pexpect.TIMEOUT], timeout=5)
            # print(f"DEBUG: Resposta da OLT após tentativa {_+1}:\n{child.before}")

            if "<" in child.before:
                success_msg = f"✅ Conexão TL1 estabelecida com sucesso para {olt_ip}"
                child.expect('<')
                child.sendline('INH-MSG-ALL::ALL:::;')
                child.expect("COMPLD")
                log_interaction("Conexão TL1 bem-sucedida", success_msg)
                print(success_msg)
                return child

        log_interaction("Erro TL1", "Falha ao acessar o prompt da OLT.", "error")
        print("❌ Erro: Conexão foi feita, mas não conseguimos acessar o shell TL1.")
        return None
    
    except pexpect.exceptions.ExceptionPexpect as e:
        error_msg = f"Falha na conexão TL1: {str(e)}"
        log_interaction("Erro TL1", error_msg, "error")
        print(error_msg)
        return None
        
    except Exception as e:
        error_msg = f"Erro inesperado TL1: {str(e)}"
        log_interaction("Erro geral TL1", error_msg, "error")
        print(error_msg)
        return None

