pip install coverage
export COVERAGE_RCFILE=/neural-compressor/.azure-pipelines/scripts/ut/coverage.file
coverage_log="/neural-compressor/log_dir/coverage_log"
coverage_log_base="/neural-compressor/log_dir/coverage_log_base"
coverage_compare="/neural-compressor/log_dir/coverate_compare.html"
cd /neural-compressor/log_dir
echo "collect coverage for PR branch"
mkdir -p coverage_PR
cp ut-coverage-adaptor/.coverage.adaptor ./coverage_PR/
cp ut-coverage-tfnewapi/.coverage.tfnewapi ./coverage_PR/
cp ut-coverage-others/.coverage.others ./coverage_PR/
cp ut-coverage-ipex/.coverage.ipex ./coverage_PR/
cd coverage_PR
coverage combine --keep --rcfile=${COVERAGE_RCFILE}
cp .coverage /neural-compressor/.coverage
cd /neural-compressor
coverage report -m --rcfile=${COVERAGE_RCFILE} | tee ${coverage_log}
coverage html -d log_dir/coverage_PR/htmlcov --rcfile=${COVERAGE_RCFILE}
coverage xml -o log_dir/coverage_PR/coverage.xml --rcfile=${COVERAGE_RCFILE}
ls -l log_dir/coverage_PR/htmlcov
echo "collect coverage for baseline"
coverage erase
cd /neural-compressor/log_dir
mkdir -p coverage_base
cp ut-coverage-adaptor-base/.coverage.adaptor ./coverage_base/
cp ut-coverage-tfnewapi-base/.coverage.tfnewapi ./coverage_base/
cp ut-coverage-others-base/.coverage.others ./coverage_base/
cp ut-coverage-ipex-base/.coverage.ipex ./coverage_base/
cd coverage_base
coverage combine --keep --rcfile=${COVERAGE_RCFILE}
cp .coverage /neural-compressor/.coverage
cd /neural-compressor
coverage report -m --rcfile=${COVERAGE_RCFILE} | tee ${coverage_log_base}
coverage html -d log_dir/coverage_base/htmlcov --rcfile=${COVERAGE_RCFILE}
coverage xml -o log_dir/coverage_base/coverage.xml --rcfile=${COVERAGE_RCFILE}
ls -l log_dir/coverage_base/htmlcov
echo "compare coverage"
coverage_PR_total=$(cat ${coverage_log} | grep TOTAL | awk '{print $NF}' | sed "s|%||g")
coverage_base_total=$(cat ${coverage_log_base} | grep TOTAL | awk '{print $NF}' | sed "s|%||g")
echo "clear upload path"
rm -fr log_dir/coverage_PR/.coverage*
rm -fr log_dir/coverage_base/.coverage*
rm -fr log_dir/ut-coverage-*
if [[ ${coverage_PR_total} -lt ${coverage_base_total} ]]; then
    decreate=$(($coverage_PR_total - $coverage_base_total))
    rate=$(awk 'BEGIN{printf "%.2f%\n",'$decreate/100'}')
    echo "Unit Test failed with covereage decrese ${rate}%"
    echo "compare coverage to give detail info"
    bash -x /neural-compressor/.azure-pipelines/scripts/ut/compare_coverage.sh ${coverage_compare} ${coverage_log} ${coverage_log_base} "FAILED"
    exit 1
else
    echo "Unit Test success with coverage ${coverage_PR_total}%"
    echo "compare coverage to give detail info"
    bash -x /neural-compressor/.azure-pipelines/scripts/ut/compare_coverage.sh ${coverage_compare} ${coverage_log} ${coverage_log_base} "SUCCESS"
    #sed "1i\Unit Test success with coverage ${coverage_PR_total}\n" ${coverage_log}
fi


#rm -r ${coverage_log}
#rm -r ${coverage_log_base}

