"""Load environment variables from .env file."""
from __future__ import annotations

import os
from pathlib import Path


def load_env(env_path: str | Path | None = None) -> None:
    """Load environment variables from .env file.
    
    Args:
        env_path: Path to .env file. If None, searches for .env in:
                  1. Current directory
                  2. Parent directory
                  3. Project root (where trading_stack package is)
    """
    if env_path and Path(env_path).exists():
        _load_env_file(Path(env_path))
        return
    
    # Search for .env in standard locations
    search_paths = [
        Path.cwd() / ".env",  # Current directory
        Path.cwd().parent / ".env",  # Parent directory
        Path(__file__).parent.parent.parent / ".env",  # Project root
    ]
    
    for path in search_paths:
        if path.exists():
            _load_env_file(path)
            print(f"Loaded environment from: {path}")
            return
    
    print("Warning: No .env file found. Using system environment variables.")


def _load_env_file(env_path: Path) -> None:
    """Load environment variables from a specific file."""
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            
            # Parse KEY=VALUE
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                
                # Set environment variable
                os.environ[key] = value
