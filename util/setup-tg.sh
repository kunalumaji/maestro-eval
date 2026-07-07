#!/bin/bash
SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

MAESTRO_EVAL_DIR=$SCRIPT_DIR/..

source $MAESTRO_EVAL_DIR/bench/vars.sh

sudo modprobe uio
sudo insmod $MAESTRO_EVAL_DIR/build/dpdk-kmods/linux/igb_uio/igb_uio.ko

sudo $MAESTRO_EVAL_DIR/build/dpdk/usertools/dpdk-hugepages.py --node 0 --reserve 42G --pagesize 1G

sudo -E $MAESTRO_EVAL_DIR/util/bind-igb-uio.sh $TG_TX_DEV
sudo -E $MAESTRO_EVAL_DIR/util/bind-igb-uio.sh $TG_RX_DEV
