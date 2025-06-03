# MEME COIN TRADING BOTS:

### First time setup


### 🛠️ Setting Up the Environment (macOS)

1. **Activate the virtual environment**  
    ```bash
    source venv/bin/activate
    ```
2. **Install the package in editable mode**
    ```bash
    pip install -e .
    ```

### 🛠️ Setting Up the Environment (Windows)

1. **Activate the virtual environment**  
    ```bash
    venv\Scripts\activate
    ```
2. **Install the package in editable mode**
    ```bash
    pip install -e .
    ```
3. If there are failures, you may need to install vscpp build tools: https://visualstudio.microsoft.com/visual-cpp-build-tools/


### 🛡️ Pre-commit Formatting

This repo uses [`black`](https://black.readthedocs.io/) with [pre-commit](https://pre-commit.com/) to format code automatically on commits.

To set it up:

```bash
pip install black pre-commit
pre-commit install
```

### Setup Telegram listener:
1. Go to the telegram site and get an API key and api hash
2. Create the following environment variables in your .env:
    - TELEGRAM_API_KEY = <YOUR API KEY\>
    - TELEGRAM_API_HASH = <YOUR API HASH\>>
3. Run scripts/telegram.setup.py and follow the instructions
This should create a .session file in the root directory that contains all the authentication info so that you do not have to reauthenticate! 

