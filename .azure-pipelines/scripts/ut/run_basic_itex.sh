#!/bin/bash
set -x
python -c "import neural_compressor as nc;print(nc.version.__version__)"
echo "run basic itex"

echo "specify fwk version..."
export itex_version='1.0.0'
export tensorflow_version='2.10.0-official'

echo "set up UT env..."
bash /neural-compressor/.azure-pipelines/scripts/ut/env_setup.sh
lpot_path=$(python -c 'import neural_compressor; import os; print(os.path.dirname(neural_compressor.__file__))')
cd /neural-compressor/test || exit 1
find ./itex -name "test*.py" | sed 's,\.\/,coverage run --source='"${lpot_path}"' --append ,g' | sed 's/$/ --verbose/'> run.sh

LOG_DIR=/neural-compressor/log_dir
mkdir -p ${LOG_DIR}
ut_log_name=${LOG_DIR}/ut_itex.log

echo "cat run.sh..."
cat run.sh | tee ${ut_log_name}
echo "-------------"
bash run.sh 2>&1 | tee -a ${ut_log_name}
cp .coverage ${LOG_DIR}/.coverage.itex
echo "list all in ${LOG_DIR}"
ls -a ${LOG_DIR}
if [ $(grep -c "FAILED" ${ut_log_name}) != 0 ] || [ $(grep -c "OK" ${ut_log_name}) == 0 ];then
    exit 1
fi