#!/usr/bin/env bash

# Install system-level dependencies
apt-get update && apt-get install -y build-essential

# Pre-install setuptools so metadata errors don’t happen
pip install setuptools==67.6.0 wheel --upgrade

# Install the rest
pip install -r requirements.txt
