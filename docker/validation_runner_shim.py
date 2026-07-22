"""Compatibility shim: continuo's executor invokes ``python /validation_runner.py``."""
from continuo_validation_core.runner import main

if __name__ == "__main__":
    main()
