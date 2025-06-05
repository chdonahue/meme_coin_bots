"""
This script will create a brand new mnemonic phrase every time it is run
It can be used to seed new families of wallets
"""

from src.wallet.wallet import create_mnemonic_phrase


def main():
    print(create_mnemonic_phrase())


if __name__ == "__main__":
    main()
