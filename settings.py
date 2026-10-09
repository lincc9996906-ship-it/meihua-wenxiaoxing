"""DeepSeek configuration, read only on the server."""
import os
from pathlib import Path
import tomllib

from core import ModelConfig

CONFIG_PATH = Path(__file__).resolve().parent / '.streamlit' / 'secrets.toml'


class SettingsError(RuntimeError):
    pass


def load_model_config(config_path=None, environ=None):
    config_path = Path(config_path) if config_path is not None else CONFIG_PATH
    environ = os.environ if environ is None else environ
    try:
        data = tomllib.loads(config_path.read_text(encoding='utf-8-sig')) if config_path.exists() else {}
    except (OSError, UnicodeError, tomllib.TOMLDecodeError):
        # Do not include TOML source lines: they may contain a credential.
        raise SettingsError('DeepSeek配置文件无法读取，请检查文件格式。') from None
    section = data.get('deepseek', {})
    if not isinstance(section, dict):
        raise SettingsError('DeepSeek配置需要使用[deepseek]分组。')
    key = section.get('api_key', '')
    model = section.get('model', 'deepseek-chat')
    if not isinstance(key, str) or not isinstance(model, str):
        raise SettingsError('DeepSeek密钥和模型名称需要使用字符串。')
    key = key.strip() or environ.get('DEEPSEEK_API_KEY', '').strip()
    model = model.strip()
    if not model or len(model) > 200 or any(c in key + model for c in '\r\n'):
        raise SettingsError('DeepSeek配置格式不正确，请检查密钥和模型名称。')
    return ModelConfig(key, model) if key else None
