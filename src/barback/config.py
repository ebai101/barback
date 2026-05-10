import shutil
import tomllib
from pathlib import Path
from typing import Literal

import platformdirs
from pydantic import BaseModel, Field, ValidationError
from textual.binding import Binding

from barback.util.logger import get_logger

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class AppConfig(BaseModel):
    """Configuration for an external application."""

    display_name: str
    application_name: str
    max_files: int | None = None


class SRBDConfig(BaseModel):
    enabled: bool = Field(default=True)
    good_dither_path: str | None = Field(default=None)


class SilenceConfig(BaseModel):
    enabled: bool = Field(default=True)


class MicrofadesConfig(BaseModel):
    enabled: bool = Field(default=True)
    fade_in_duration: int = 35
    fade_out_duration: int = 90


class LoopConfig(BaseModel):
    enabled: bool = Field(default=True)


class KeysigConfig(BaseModel):
    enabled: bool = Field(default=True)


class RepairsConfig(BaseModel):
    sr_bd: SRBDConfig = Field(default_factory=SRBDConfig)
    silence: SilenceConfig = Field(default_factory=SilenceConfig)
    microfades: MicrofadesConfig = Field(default_factory=MicrofadesConfig)
    loop: LoopConfig = Field(default_factory=LoopConfig)
    keysig: KeysigConfig = Field(default_factory=KeysigConfig)


class BarbackConfig(BaseModel):
    """Main configuration for Barback."""

    theme: str = "tokyonight"
    log_level: LogLevel = "INFO"
    repairs: RepairsConfig = Field(default_factory=RepairsConfig)
    apps: list[AppConfig] = Field(default_factory=list)

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the path to the config file."""
        config_dir = Path(platformdirs.user_config_dir("barback"))
        return config_dir / "config.toml"

    @classmethod
    def get_default_config_path(cls) -> Path:
        """Get the default configuration as a TOML string."""
        current_file = Path(__file__)
        repo_root = current_file.parent.parent.parent
        repo_default = repo_root / "config.default.toml"

        if repo_default.exists():
            return repo_default

        package_default = current_file.parent.parent / "config.default.toml"
        if package_default.exists():
            return package_default

        local_default = Path("config.default.toml")
        if local_default.exists():
            return local_default

        raise FileNotFoundError(
            "config.default.toml not found. Please ensure it exists in the repository root, or create a config file at ~/.barback/config.toml"
        )

    @classmethod
    def load(cls) -> "BarbackConfig":
        """
        Load configuration from file or create default if not found.

        Returns:
            BarbackConfig: The loaded or default configuration
        """
        logger = get_logger()
        config_path = cls.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        if not config_path.exists():
            # Copy default config file
            try:
                default_config_path = cls.get_default_config_path()
                shutil.copy2(default_config_path, config_path)
                logger.info(f"Created default config at {config_path}")
            except FileNotFoundError as e:
                logger.error(f"Could not find config.default.toml: {e}")

        # Load and parse config
        try:
            with open(config_path, "rb") as f:
                data = tomllib.load(f)

            config = cls(**data)

            logger.info(f"Loaded config from {config_path}")
            return config

        except ValidationError as e:
            logger.error(
                f"Failed to load config from {config_path}: {e}", exc_info=True
            )
            logger.info("Using default configuration")
            return cls()
        except Exception as e:
            logger.error(
                f"Failed to load config from {config_path}: {e}", exc_info=True
            )
            return cls()

    def generate_app_bindings(self) -> list[Binding]:
        """
        Generate Textual bindings for all configured apps.

        Returns:
            List of Bindings
        """
        bindings = []
        shift_key_names = [
            "exclamation_mark",  # 1
            "at",  # 2
            "hash",  # 3
            "dollar",  # 4
            "percent",  # 5
            "circumflex",  # 6
            "ampersand",  # 7
            "asterisk",  # 8
            "left_parenthesis",  # 9
            "right_parenthesis",  # 0
        ]

        for idx, app in enumerate(self.apps, start=1):
            if idx > 10:
                break

            key = str(idx % 10)
            shift_key = shift_key_names[idx - 1]

            # Regular binding: open selected file
            bindings.append(
                Binding(
                    key,
                    f"open_in_{app.display_name.lower().replace(' ', '_')}",
                    app.display_name,
                    show=True,
                    tooltip=f"Open selected file in {app.application_name}",
                )
            )

            # Shift binding: open all files with issue type
            bindings.append(
                Binding(
                    shift_key,
                    f"open_all_in_{app.display_name.lower().replace(' ', '_')}",
                    f"{app.display_name} (All)",
                    show=False,
                    tooltip=f"Open all files with a specific issue in {app.application_name}",
                )
            )

        return bindings


_config_instance = None


def get_config() -> BarbackConfig:
    """Get the Barback logger instance."""
    global _config_instance
    if _config_instance is None:
        _config_instance = BarbackConfig.load()
    return _config_instance
