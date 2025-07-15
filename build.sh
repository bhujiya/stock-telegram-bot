#!/usr/bin/env bash

# Install system-level build tools
apt-get update && apt-get install -y build-essential

# Upgrade pip and install wheel + setuptools
pip install --upgrade pip setuptools wheel

# Install dependencies from requirements.txt
pip install -r requirements.txt
