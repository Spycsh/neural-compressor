#!/bin/bash

source /neural-compressor/.azure-pipelines/scripts/change_color.sh
RESET="echo -en \\E[0m \\n" # close color

log_dir="/neural-compressor/.azure-pipelines/scripts/codeScan/scanLog"
mkdir -p $log_dir

pydocstyle --convention=google /neural-compressor/neural_compressor/experimental > $log_dir/pydocstyle.log
exit_code=$?


$BOLD_YELLOW && echo " -----------------  Current pydocstyle cmd start --------------------------" && $RESET
echo "python pydocstyle --convention=google /neural-compressor/neural_compressor/experimental > $log_dir/pydocstyle.log"
$BOLD_YELLOW && echo " -----------------  Current pydocstyle cmd end --------------------------" && $RESET

$BOLD_YELLOW && echo " -----------------  Current log file output start --------------------------"
cat  $log_dir/pydocstyle.log
$BOLD_YELLOW && echo " -----------------  Current log file output end --------------------------" && $RESET


if [ ${exit_code} -ne 0 ] ; then
    $BOLD_RED && echo "Error!! Please Click on the artifact button to download and view DocStyle error details." && $RESET; exit 1
fi
$BOLD_PURPLE && echo "Congratulations, DocStyle check passed!" && $LIGHT_PURPLE && echo " You can click on the artifact button to see the log details." && $RESET; exit 0