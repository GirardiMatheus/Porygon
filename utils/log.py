import logging
import os
from datetime import datetime

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        logs_dir = "logs"
        os.makedirs(logs_dir, exist_ok=True)

        log_filename = name.replace(".", "_") + "_log.log"
        full_path = os.path.join(logs_dir, log_filename)

        # Escreve a linha separadora diretamente no arquivo
        with open(full_path, "a") as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"Novo início de execução: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n")

        file_handler = logging.FileHandler(full_path, mode='a')
        file_handler.setLevel(logging.DEBUG)

        formatter = logging.Formatter(
            fmt='%(asctime)s - [%(levelname)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger