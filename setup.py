from setuptools import setup, find_packages

# Read requirements from requirements.txt
with open("requirements.txt") as f:
    requirements = f.read().splitlines()

setup(
    name="Meme-Coin-Bots",
    packages=find_packages(),
    version="0.1",
    install_requires=requirements,
)
