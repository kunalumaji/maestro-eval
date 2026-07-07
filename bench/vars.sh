#!/bin/bash

set -euo pipefail

SCRIPT_DIR=$(cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd)

DATA_DIR="$SCRIPT_DIR/data"
PCAPS_DIR="$SCRIPT_DIR/pcaps"

#SCR_PCAPS_DIR="$SCRIPT_DIR/scr-nfs/pcaps"
SCR_PCAPS_DIR="/proj/morpheus-PG0/scr-pcaps"

DUT_SCR_PCAPS_DIR="${SCR_PCAPS_DIR}"
TG_SCR_PCAPS_DIR="${SCR_PCAPS_DIR}"

# SSH entries. Make sure these are accessible!
DUT="smiano@sm110p-10s10620.wisc.cloudlab.us" # FIXME: DUT ssh entry
TG="smiano@sm110p-10s10619.wisc.cloudlab.us"  # FIXME: TG ssh entry

DUT_EVAL_DIR=~/maestro-eval # Path to this repo on the DUT
TG_EVAL_DIR=~/maestro-eval  # Path to this repo on the TG

DUT_CORES="1,2,3,4,5,6,7,8" # FIXME: comma separated list of cores to be used (e.g. "0,1,2,3")
# DUT_CORES="1,3"

DUT_SCR_DIR=${DUT_EVAL_DIR}/scr-nfs/nf-no-expire
DUT_MLNX_SYNT_DIR=${DUT_EVAL_DIR}/synthesized-mlnx/nf-no-expire-tx-queues
DUT_MLNX_OTHERS_SYNT_DIR=${DUT_EVAL_DIR}/synthesized-mlnx/original-nf-tx-queues

TG_TX_DEV="0000:03:00.1" # FIXME: TX PCIe device on the TG
TG_RX_DEV="0000:03:00.1" # FIXME: RX PCIe device on the TG

DUT_TX_DEV="0000:51:00.1" # FIXME: TX PCIe device on the DUT
DUT_RX_DEV="0000:51:00.0" # FIXME: RX PCIe device on the DUT

PCAP_SRC_MAC="9c:dc:71:5d:d5:b1"
PCAP_DST_MAC="9c:dc:71:5e:0f:91"

TG_TX_CORES=6
TG_RX_CORES=6

ITERATIONS=1
ITERATION_DURATION_SEC=3
