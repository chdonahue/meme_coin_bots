# MEME COIN TRADING BOTS:

### 🛠️ Setting Up the Environment (macOS)

1. **Activate the virtual environment**  
    ```bash
    source venv/bin/activate
    ```
2. **Install the package in editable mode**
    ```bash
    pip install -e .
    ```


### 🛡️ Pre-commit Formatting

This repo uses [`black`](https://black.readthedocs.io/) with [pre-commit](https://pre-commit.com/) to format code automatically on commits.

To set it up:

```bash
pip install black pre-commit
pre-commit install