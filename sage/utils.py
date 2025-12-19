import os
import yaml

from pathlib import Path
from yaml import YAMLError
from typing import Optional, Any
from discord import Intents

from .config import config
from .helpers import get_path
from .log import loggers, log_exception

logger = loggers.UTILS


def yaml_read(p: str | Path, supress_logs: bool = False) -> Optional[list | dict]:
    path = p if isinstance(p, Path) else get_path(p)

    if path.is_dir():
        logger.error(f"{str(path)} is a directory")
        return None

    if not os.access(path, os.R_OK):
        logger.error(f"Failed to read {str(path)}; permission denied")
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            file = yaml.safe_load(f)
            if not supress_logs:
                logger.info(f"Read {str(path)}")
            return file

    except YAMLError as e:
        e_str = log_exception(e, logger)
        logger.error(f"Failed to parse {str(path)}: {e_str}")

    except FileNotFoundError:
        logger.error(f"Failed to read {str(path)}; file doesn't exist")

    except Exception as e:
        e_str = log_exception(e, logger)
        logger.error(f"Unexpected error occurred while reading {str(path)}: {e_str}")

    return None


def yaml_write(p: str | Path, data: Any, supress_logs: bool = False, *args, **kwargs) -> bool:
    path = p if isinstance(p, Path) else get_path(p)

    if path.is_dir():
        logger.error(f"{str(path)} is a directory")
        return False

    if not os.access(path.parent, os.W_OK):
        logger.error(f"Failed to write {str(path)}; permission denied")
        return False

    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, *args, **kwargs)

        file_data = yaml_read(path, supress_logs=supress_logs)

        if file_data != data:
            logger.error(f"Failed to write {str(path)}; data missmatch")
            return False

        if not supress_logs:
            logger.info(f"Wrote {str(path)}")

        return True

    except YAMLError as e:
        e_str = log_exception(e, logger)
        logger.error(f"Failed to parse data for {str(path)}: {e_str}")

    except Exception as e:
        e_str = log_exception(e, logger)
        logger.error(f"Unexpected error occurred while writing {str(path)}: {e_str}")

    return False


def generate_intents() -> Intents:
    intents = Intents.default()

    for intent, enabled in config.intents.items():
        setattr(intents, intent, enabled)

    return intents