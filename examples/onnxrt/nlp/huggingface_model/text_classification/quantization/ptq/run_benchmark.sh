#!/bin/bash
set -x

function main {

  init_params "$@"
  run_benchmark

}

# init params
function init_params {
  for var in "$@"
  do
    case $var in
      --config=*)
          config=$(echo $var |cut -f2 -d=)
      ;;
      --input_model=*)
          input_model=$(echo $var |cut -f2 -d=)
      ;;
      --mode=*)
          mode=$(echo $var |cut -f2 -d=)
      ;;
      --data_path=*)
          data_path=$(echo $var |cut -f2 -d=)
      ;;
    esac
  done

}

# run_benchmark
function run_benchmark {
    
    if [[ "${input_model}" =~ "bert-base" ]]; then
        model_name_or_path="Intel/bert-base-uncased-mrpc"
        TASK_NAME='mrpc'
    fi
    if [[ "${input_model}" =~ "roberta-base" ]]; then
        model_name_or_path="Intel/roberta-base-mrpc"
        TASK_NAME='mrpc'
    fi
    if [[ "${input_model}" =~ "xlm-roberta-base" ]]; then
        model_name_or_path="Intel/xlm-roberta-base-mrpc"
        TASK_NAME='mrpc'
    fi
    if [[ "${input_model}" =~ "camembert-base" ]]; then
        model_name_or_path="Intel/camembert-base-mrpc"
        TASK_NAME='mrpc'
    fi
    if [[ "${input_model}" =~ "distilbert-base" ]]; then
        model_name_or_path="distilbert-base-uncased-finetuned-sst-2-english"
        TASK_NAME='sst-2'
    fi
    if [[ "${input_model}" =~ "albert-base" ]]; then
        model_name_or_path="Alireza1044/albert-base-v2-sst2"
        TASK_NAME='sst-2'
    fi
    if [[ "${input_model}" =~ "MiniLM-L6" ]]; then
        model_name_or_path="philschmid/MiniLM-L6-H384-uncased-sst2"
        TASK_NAME='sst-2'
    fi
    if [[ "${input_model}" =~ "MiniLM-L12" ]]; then
        model_name_or_path="Intel/MiniLM-L12-H384-uncased-mrpc"
        TASK_NAME='mrpc'
    fi

    python main.py \
            --model_name_or_path ${model_name_or_path} \
            --model_path ${input_model} \
            --config ${config} \
            --data_path ${data_path} \
            --task ${TASK_NAME} \
            --mode=${mode} \
            --benchmark
            
}

main "$@"

