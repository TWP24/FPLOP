#!/bin/sh
# Vendor the Dastan model so `--model dastan` can run. 78MB, not committed.
set -e
cd "$(dirname "$0")"
mkdir -p vendor
[ -d vendor/dastan ] || git clone --depth 1 https://github.com/qazybekb/smartplayfpl-dastan.git vendor/dastan
rm -rf vendor/dastan/.git
./.venv/bin/pip install --quiet xgboost scikit-learn pyarrow pandas
echo "vendored. check with: ./fplm.sh plan --model dastan"
